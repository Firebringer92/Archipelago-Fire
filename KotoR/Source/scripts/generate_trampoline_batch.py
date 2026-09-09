"""
Regenerates area trampoline(s) with the CURRENT pending batch of apply IDs
inlined directly into main(), appended after the existing preserved-original
+ poll_shared logic. This is the new arming mechanism: instead of a single
overwrite slot reachable only from the (permanently unreachable, post-
prologue) Endar Spire module, ANY of the 78 covered areas can carry a batch
of pending grants, executed immediately and inline on the player's next
entry into that specific area -- no ExecuteScript hop to a changing target
(confirmed broken elsewhere), no wait for the heartbeat.

The apply-action bodies are the SAME ones used in generate_heartbeat.py's
APPLIES list (kept in sync by hand for now -- small, stable list).

Usage: python generate_trampoline_batch.py <arm_id> [<arm_id> ...] [--areas base1,base2,...|--all] [--game-dir=<path>]
  Tokens: a bare int is a fixed arm ID (APPLIES table); "set_xp:<N>",
  "set_credits:<N>", "give_item:<resref>:<count>", and "notify:<text>" are
  parameterized actions -- see build_batch_block(). "notify" is the odd
  one out: no KSE_Diag confirmation line, no delivery tracking, purely a
  one-shot AurPostString on-screen message (see build_notify_block()).
  With no --areas/--all, defaults to a small test target for manual proof.
  With no --game-dir=, defaults to the standard Steam install location --
  arm_orchestrator.py (the real, per-player caller, invoked by the compiled
  extender) always passes --game-dir= explicitly, since a player's own
  install may live anywhere.
"""
import json
import os
import subprocess
import sys
from collections import defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(REPO_ROOT, "extender", "area_trampolines")
OVERRIDE_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor\Override"
from nwnnsscomp_path import resolve_nwnnsscomp  # noqa: E402 -- see that module's docstring
NWNNSSCOMP = resolve_nwnnsscomp()

# Base (auto-granted, feat.2da's <code>_granted=1) feats per class -- confirmed
# 2026-09-06 via pykotor against the real game data, see GameMechanics.md /
# research/feats/class_feats.json for the full derivation. Used by
# build_class_feat_delta_lines() below to compute exactly which feats a
# class-change should strip/grant, instead of the raw KSE_SetCreatureField
# CLASS0_TYPE overwrite touching feats at all (which it never did on its
# own -- confirmed live 2026-08-31 that a class write alone leaves the old
# class's feats in place permanently, e.g. a Jedi-to-base switch keeping
# lightsaber proficiency).
CLASS_BASE_FEATS = {
    "CLASS_TYPE_SOLDIER":      [4, 5, 6, 28, 29, 39, 40, 42, 44],
    "CLASS_TYPE_SCOUT":        [5, 6, 11, 14, 30, 39, 40, 44],
    "CLASS_TYPE_SCOUNDREL":    [5, 8, 31, 39, 40, 44, 60, 104],
    "CLASS_TYPE_JEDIGUARDIAN": [39, 43, 44, 55, 101, 107, 116],
    "CLASS_TYPE_JEDICONSULAR": [39, 43, 44, 55, 88, 107, 116],
    "CLASS_TYPE_JEDISENTINEL": [39, 43, 44, 55, 98, 107, 116],
}
_ALL_CLASS_TYPE_CONSTS = list(CLASS_BASE_FEATS.keys())

# Armor Prof ordering, confirmed via feat.2da's prereqfeat1/2 columns
# (2026-09-06): Heavy(4) requires Medium(6)+Light(5); Medium(6) requires
# Light(5); no other base feat in the table above has any prerequisite at
# all. Removing must go highest-tier-first (so a lower tier a still-held
# higher tier depends on is never pulled out from under it, even
# transiently); granting must go lowest-tier-first (so a higher tier's
# prerequisites are already satisfied the instant it's granted).
_ARMOR_PROF_REMOVE_ORDER = {4: 0, 6: 1, 5: 2}
_ARMOR_PROF_GRANT_ORDER = {5: 0, 6: 1, 4: 2}


def build_class_feat_delta_lines(new_class_const, target_var, old_class_var="nOldClass", delay_grants=False, indent="    "):
    """Generates NWScript lines that branch on `old_class_var` (must already
    be read live via GetClassByPosition(1, ...) BEFORE the class-type field
    is overwritten) and, for every possible old class other than
    new_class_const, strip exactly the old class's base feats the new class
    doesn't share, then grant exactly the new class's base feats the old
    class didn't already have. Feats shared between old and new are never
    touched -- sidesteps the undocumented "grant an already-held feat"
    behavior entirely (see kse.nss's KSE_GrantFeatArrayA doc, no statement
    either way on duplicates).

    delay_grants=True wraps each grant in DelayCommand(1.0, ...) -- required
    when granting INTO a Jedi class via AddMultiClass, which has a
    confirmed settling race that silently drops immediate grants (see
    build_companion_class_block's 2026-09-03 fix note); base-class grants
    have no such race and stay immediate.

    Emits NO branch at all for an old class that would need zero removes
    and zero grants (nothing to do), and skips new_class_const itself
    (already-correct, a same-class "switch" is a no-op)."""
    new_kit = set(CLASS_BASE_FEATS[new_class_const])
    lines = []
    first = True
    for old_const in _ALL_CLASS_TYPE_CONSTS:
        if old_const == new_class_const:
            continue
        old_kit = set(CLASS_BASE_FEATS[old_const])
        to_remove = sorted(old_kit - new_kit, key=lambda f: _ARMOR_PROF_REMOVE_ORDER.get(f, 10))
        to_grant = sorted(new_kit - old_kit, key=lambda f: _ARMOR_PROF_GRANT_ORDER.get(f, -1))
        if not to_remove and not to_grant:
            continue
        cond = "if" if first else "else if"
        first = False
        lines.append(f"{indent}{cond} ({old_class_var} == {old_const})")
        lines.append(f"{indent}{{")
        for feat in to_remove:
            lines.append(f"{indent}    KSE_RemoveFeatArrayA({feat}, {target_var});")
        for feat in to_grant:
            if delay_grants:
                lines.append(f"{indent}    DelayCommand(1.0, KSE_GrantFeatArrayA({feat}, {target_var}));")
            else:
                lines.append(f"{indent}    KSE_GrantFeatArrayA({feat}, {target_var});")
        lines.append(f"{indent}}}")
    return lines


# Must match generate_arm_scripts.py / generate_heartbeat.py's ID scheme.
APPLIES = {
    1: ("computer_use", [
        'object oPC = GetFirstPC();',
        'int nBefore = GetSkillRank(SKILL_COMPUTER_USE, oPC);',
        'KSE_AdjustCreatureSkills(oPC, SKILL_COMPUTER_USE, 2);',
        'int nAfter = GetSkillRank(SKILL_COMPUTER_USE, oPC);',
        'KSE_Diag(2, "AP|APPLIED|computer_use|before=" + IntToString(nBefore) + "|after=" + IntToString(nAfter));',
    ]),
    2: ("demolitions", [
        'object oPC = GetFirstPC();',
        'int nBefore = GetSkillRank(SKILL_DEMOLITIONS, oPC);',
        'KSE_AdjustCreatureSkills(oPC, SKILL_DEMOLITIONS, 2);',
        'int nAfter = GetSkillRank(SKILL_DEMOLITIONS, oPC);',
        'KSE_Diag(2, "AP|APPLIED|demolitions|before=" + IntToString(nBefore) + "|after=" + IntToString(nAfter));',
    ]),
    3: ("stealth", [
        'object oPC = GetFirstPC();',
        'int nBefore = GetSkillRank(SKILL_STEALTH, oPC);',
        'KSE_AdjustCreatureSkills(oPC, SKILL_STEALTH, 2);',
        'int nAfter = GetSkillRank(SKILL_STEALTH, oPC);',
        'KSE_Diag(2, "AP|APPLIED|stealth|before=" + IntToString(nBefore) + "|after=" + IntToString(nAfter));',
    ]),
    4: ("awareness", [
        'object oPC = GetFirstPC();',
        'int nBefore = GetSkillRank(SKILL_AWARENESS, oPC);',
        'KSE_AdjustCreatureSkills(oPC, SKILL_AWARENESS, 2);',
        'int nAfter = GetSkillRank(SKILL_AWARENESS, oPC);',
        'KSE_Diag(2, "AP|APPLIED|awareness|before=" + IntToString(nBefore) + "|after=" + IntToString(nAfter));',
    ]),
    5: ("persuade", [
        'object oPC = GetFirstPC();',
        'int nBefore = GetSkillRank(SKILL_PERSUADE, oPC);',
        'KSE_AdjustCreatureSkills(oPC, SKILL_PERSUADE, 2);',
        'int nAfter = GetSkillRank(SKILL_PERSUADE, oPC);',
        'KSE_Diag(2, "AP|APPLIED|persuade|before=" + IntToString(nBefore) + "|after=" + IntToString(nAfter));',
    ]),
    6: ("repair", [
        'object oPC = GetFirstPC();',
        'int nBefore = GetSkillRank(SKILL_REPAIR, oPC);',
        'KSE_AdjustCreatureSkills(oPC, SKILL_REPAIR, 2);',
        'int nAfter = GetSkillRank(SKILL_REPAIR, oPC);',
        'KSE_Diag(2, "AP|APPLIED|repair|before=" + IntToString(nBefore) + "|after=" + IntToString(nAfter));',
    ]),
    7: ("security", [
        'object oPC = GetFirstPC();',
        'int nBefore = GetSkillRank(SKILL_SECURITY, oPC);',
        'KSE_AdjustCreatureSkills(oPC, SKILL_SECURITY, 2);',
        'int nAfter = GetSkillRank(SKILL_SECURITY, oPC);',
        'KSE_Diag(2, "AP|APPLIED|security|before=" + IntToString(nBefore) + "|after=" + IntToString(nAfter));',
    ]),
    8: ("treat_injury", [
        'object oPC = GetFirstPC();',
        'int nBefore = GetSkillRank(SKILL_TREAT_INJURY, oPC);',
        'KSE_AdjustCreatureSkills(oPC, SKILL_TREAT_INJURY, 2);',
        'int nAfter = GetSkillRank(SKILL_TREAT_INJURY, oPC);',
        'KSE_Diag(2, "AP|APPLIED|treat_injury|before=" + IntToString(nBefore) + "|after=" + IntToString(nAfter));',
    ]),
    # GUARD added 2026-09-08 (real bug found live: two Bastilas after her
    # grant arm re-fired on a later area transition -- the known
    # one-transition delivery-lag retry logic re-queues an arm whenever its
    # APPLIED confirmation isn't cleanly matched, and this arm previously
    # had no idempotency check at all, so a re-fire created a genuine
    # second CreateObject+AddPartyMember. `nWasAvailable` used to be purely
    # diagnostic (captured, never branched on) -- now it actually gates the
    # grant, same pattern generate_companion_suppressors.py's wrapper
    # already used correctly. Still ALWAYS emits the APPLIED diag either
    # way (skip or real grant) so the pending queue correctly dequeues it
    # regardless -- an ELSE branch that stayed silent would make this
    # worse, not better, by leaving the arm perpetually "pending".
    9: ("companion_bastila", [
        'int nNPC = NPC_BASTILA;',
        'string sTemplate = "p_bastilla";',
        'int nWasAvailable = IsAvailableCreature(nNPC);',
        'int nAdded = FALSE;',
        'if (!nWasAvailable)',
        '{',
        '    AddAvailableNPCByTemplate(nNPC, sTemplate);',
        '    object oPC = GetFirstPC();',
        '    object oNPC = CreateObject(OBJECT_TYPE_CREATURE, sTemplate, GetLocation(oPC));',
        '    nAdded = AddPartyMember(nNPC, oNPC);',
        '}',
        'KSE_Diag(4, "AP|APPLIED|companion_bastila|wasAvailable=" + IntToString(nWasAvailable) + "|added=" + IntToString(nAdded));',
    ]),
    10: ("companion_canderous", [
        'int nNPC = NPC_CANDEROUS;',
        'string sTemplate = "p_cand";',
        'int nWasAvailable = IsAvailableCreature(nNPC);',
        'int nAdded = FALSE;',
        'if (!nWasAvailable)',
        '{',
        '    AddAvailableNPCByTemplate(nNPC, sTemplate);',
        '    object oPC = GetFirstPC();',
        '    object oNPC = CreateObject(OBJECT_TYPE_CREATURE, sTemplate, GetLocation(oPC));',
        '    nAdded = AddPartyMember(nNPC, oNPC);',
        '}',
        'KSE_Diag(4, "AP|APPLIED|companion_canderous|wasAvailable=" + IntToString(nWasAvailable) + "|added=" + IntToString(nAdded));',
    ]),
    11: ("xp", [
        'object oPC = GetFirstPC();',
        'int nBefore = GetXP(oPC);',
        'SetXP(oPC, nBefore + 500);',
        'int nAfter = GetXP(oPC);',
        'KSE_Diag(5, "AP|APPLIED|xp|before=" + IntToString(nBefore) + "|after=" + IntToString(nAfter));',
    ]),
    # 12 (feat_toughness) RETIRED -- feats are left entirely to normal
    # in-game level-up choices now, never touched by AP. No longer in
    # item_table/KNOWN_ARM_NAMES, so this ID is permanently unreachable --
    # left as a gap here (not renumbered), same reasoning as the 15/16 gap
    # below.
    13: ("class_guardian", [
        'object oPC = GetFirstPC();',
        'int nBefore = GetLevelByClass(CLASS_TYPE_JEDIGUARDIAN, oPC);',
        'AddMultiClass(CLASS_TYPE_JEDIGUARDIAN, oPC);',
        'ShowLevelUpGUI();',
        'int nAfter = GetLevelByClass(CLASS_TYPE_JEDIGUARDIAN, oPC);',
        'KSE_Diag(9, "AP|APPLIED|class_guardian|before=" + IntToString(nBefore) + "|after=" + IntToString(nAfter));',
    ]),
    14: ("class_consular", [
        'object oPC = GetFirstPC();',
        'int nBefore = GetLevelByClass(CLASS_TYPE_JEDICONSULAR, oPC);',
        'AddMultiClass(CLASS_TYPE_JEDICONSULAR, oPC);',
        'ShowLevelUpGUI();',
        'int nAfter = GetLevelByClass(CLASS_TYPE_JEDICONSULAR, oPC);',
        'KSE_Diag(9, "AP|APPLIED|class_consular|before=" + IntToString(nBefore) + "|after=" + IntToString(nAfter));',
    ]),
    # 16 (companion_jedi_xp) stays RETIRED -- confirmed live that
    # GiveXPToCreature has zero effect on a non-PC party member. Not in
    # item_table/KNOWN_ARM_NAMES, permanently unreachable via real AP items.
    #
    # 15/16 (test_setfield/test_combined) RETIRED 2026-08-30 -- were the
    # throwaway live tests that confirmed KSE_SetCreatureField works on a
    # companion (Zaalbar -> Level 20 Jedi Guardian, 76 Force). The real
    # feature is now the "companion_class" parameterized action (see
    # build_companion_class_block() and the companion_class: token
    # handling below), wired into the real AP flow via Options.py's
    # CompanionClass. Not reusing these IDs -- same reasoning as the other
    # retired-gap comments in this table (12, old-16).
    # 33 (dump_statblock) RETIRED 2026-09-06 -- Force Powers offset research
    # concluded (see FutureDesign.md); the confirmed layout shipped as
    # KseForcePowerOp. Archived at extender/research_archive/
    # generate_trampoline_batch_temp_arms_2026-09-06.py.txt, same gap
    # convention as 12/15/16 above.
    17: ("credits", [
        'object oPC = GetFirstPC();',
        'int nBefore = GetGold(oPC);',
        'GiveGoldToCreature(oPC, 5000);',
        'int nAfter = GetGold(oPC);',
        'KSE_Diag(39, "AP|APPLIED|credits|before=" + IntToString(nBefore) + "|after=" + IntToString(nAfter));',
    ]),
    18: ("grant_test_ability", [
        # BUG FIXED: this diag used to report itself as "ability_charisma",
        # not "grant_test_ability" -- the actual registered arm name (see
        # AP_ARM_NAMES in dllmain.c). ap_arm_id_for_name() could never match
        # the mismatched name back to an ID, so this arm's confirmation
        # never cleared the pending queue -- confirmed live: it silently
        # re-fired on every single area transition indefinitely once
        # received, the whole session, until caught by chance.
        'object oPC = GetFirstPC();',
        'int nBefore = GetAbilityScore(oPC, ABILITY_CHARISMA);',
        'ApplyEffectToObject(DURATION_TYPE_PERMANENT, EffectAbilityIncrease(ABILITY_CHARISMA, 1), oPC);',
        'int nAfter = GetAbilityScore(oPC, ABILITY_CHARISMA);',
        'KSE_Diag(92, "AP|APPLIED|grant_test_ability|before=" + IntToString(nBefore) + "|after=" + IntToString(nAfter));',
    ]),
    # Companion re-grant arms 19-25 -- same shape as companion_bastila/
    # companion_canderous above (arm IDs 9/10), just the 7 remaining
    # companions. NPC index and template resref extracted directly from
    # each companion's preserved vanilla recruit script (see the
    # AddAvailableNPCByTemplate call each apo_<name>_orig.ncs makes) rather
    # than guessed, since a wrong template resref would silently fail to
    # spawn a working companion.
    19: ("companion_carth", [
        'int nNPC = NPC_CARTH;',
        'string sTemplate = "p_carth";',
        'int nWasAvailable = IsAvailableCreature(nNPC);',
        'int nAdded = FALSE;',
        'if (!nWasAvailable)',
        '{',
        '    AddAvailableNPCByTemplate(nNPC, sTemplate);',
        '    object oPC = GetFirstPC();',
        '    object oNPC = CreateObject(OBJECT_TYPE_CREATURE, sTemplate, GetLocation(oPC));',
        '    nAdded = AddPartyMember(nNPC, oNPC);',
        '}',
        'KSE_Diag(50, "AP|APPLIED|companion_carth|wasAvailable=" + IntToString(nWasAvailable) + "|added=" + IntToString(nAdded));',
    ]),
    20: ("companion_hk47", [
        'int nNPC = NPC_HK_47;',
        'string sTemplate = "p_hk47";',
        'int nWasAvailable = IsAvailableCreature(nNPC);',
        'int nAdded = FALSE;',
        'if (!nWasAvailable)',
        '{',
        '    AddAvailableNPCByTemplate(nNPC, sTemplate);',
        '    object oPC = GetFirstPC();',
        '    object oNPC = CreateObject(OBJECT_TYPE_CREATURE, sTemplate, GetLocation(oPC));',
        '    nAdded = AddPartyMember(nNPC, oNPC);',
        '}',
        'KSE_Diag(51, "AP|APPLIED|companion_hk47|wasAvailable=" + IntToString(nWasAvailable) + "|added=" + IntToString(nAdded));',
    ]),
    21: ("companion_jolee", [
        'int nNPC = NPC_JOLEE;',
        'string sTemplate = "p_jolee";',
        'int nWasAvailable = IsAvailableCreature(nNPC);',
        'int nAdded = FALSE;',
        'if (!nWasAvailable)',
        '{',
        '    AddAvailableNPCByTemplate(nNPC, sTemplate);',
        '    object oPC = GetFirstPC();',
        '    object oNPC = CreateObject(OBJECT_TYPE_CREATURE, sTemplate, GetLocation(oPC));',
        '    nAdded = AddPartyMember(nNPC, oNPC);',
        '}',
        'KSE_Diag(52, "AP|APPLIED|companion_jolee|wasAvailable=" + IntToString(nWasAvailable) + "|added=" + IntToString(nAdded));',
    ]),
    22: ("companion_juhani", [
        'int nNPC = NPC_JUHANI;',
        'string sTemplate = "p_juhani";',
        'int nWasAvailable = IsAvailableCreature(nNPC);',
        'int nAdded = FALSE;',
        'if (!nWasAvailable)',
        '{',
        '    AddAvailableNPCByTemplate(nNPC, sTemplate);',
        '    object oPC = GetFirstPC();',
        '    object oNPC = CreateObject(OBJECT_TYPE_CREATURE, sTemplate, GetLocation(oPC));',
        '    nAdded = AddPartyMember(nNPC, oNPC);',
        '}',
        'KSE_Diag(53, "AP|APPLIED|companion_juhani|wasAvailable=" + IntToString(nWasAvailable) + "|added=" + IntToString(nAdded));',
    ]),
    23: ("companion_mission", [
        'int nNPC = NPC_MISSION;',
        'string sTemplate = "p_mission";',
        'int nWasAvailable = IsAvailableCreature(nNPC);',
        'int nAdded = FALSE;',
        'if (!nWasAvailable)',
        '{',
        '    AddAvailableNPCByTemplate(nNPC, sTemplate);',
        '    object oPC = GetFirstPC();',
        '    object oNPC = CreateObject(OBJECT_TYPE_CREATURE, sTemplate, GetLocation(oPC));',
        '    nAdded = AddPartyMember(nNPC, oNPC);',
        '}',
        'KSE_Diag(54, "AP|APPLIED|companion_mission|wasAvailable=" + IntToString(nWasAvailable) + "|added=" + IntToString(nAdded));',
    ]),
    24: ("companion_t3m4", [
        'int nNPC = NPC_T3_M4;',
        'string sTemplate = "p_t3m4";',
        'int nWasAvailable = IsAvailableCreature(nNPC);',
        'int nAdded = FALSE;',
        'if (!nWasAvailable)',
        '{',
        '    AddAvailableNPCByTemplate(nNPC, sTemplate);',
        '    object oPC = GetFirstPC();',
        '    object oNPC = CreateObject(OBJECT_TYPE_CREATURE, sTemplate, GetLocation(oPC));',
        '    nAdded = AddPartyMember(nNPC, oNPC);',
        '}',
        'KSE_Diag(55, "AP|APPLIED|companion_t3m4|wasAvailable=" + IntToString(nWasAvailable) + "|added=" + IntToString(nAdded));',
    ]),
    25: ("companion_zaalbar", [
        'int nNPC = NPC_ZAALBAR;',
        'string sTemplate = "p_zaalbar";',
        'int nWasAvailable = IsAvailableCreature(nNPC);',
        'int nAdded = FALSE;',
        'if (!nWasAvailable)',
        '{',
        '    AddAvailableNPCByTemplate(nNPC, sTemplate);',
        '    object oPC = GetFirstPC();',
        '    object oNPC = CreateObject(OBJECT_TYPE_CREATURE, sTemplate, GetLocation(oPC));',
        '    nAdded = AddPartyMember(nNPC, oNPC);',
        '}',
        'KSE_Diag(56, "AP|APPLIED|companion_zaalbar|wasAvailable=" + IntToString(nWasAvailable) + "|added=" + IntToString(nAdded));',
    ]),
    # Third Jedi class -- class_guardian/class_consular (13/14) covered
    # Guardian/Consular already; Sentinel was the missing one.
    26: ("class_sentinel", [
        'object oPC = GetFirstPC();',
        'int nBefore = GetLevelByClass(CLASS_TYPE_JEDISENTINEL, oPC);',
        'AddMultiClass(CLASS_TYPE_JEDISENTINEL, oPC);',
        'ShowLevelUpGUI();',
        'int nAfter = GetLevelByClass(CLASS_TYPE_JEDISENTINEL, oPC);',
        'KSE_Diag(9, "AP|APPLIED|class_sentinel|before=" + IntToString(nBefore) + "|after=" + IntToString(nAfter));',
    ]),
    # Ability-score increases 27-31 -- same shape as grant_test_ability (18,
    # Charisma) above, covering the remaining 5 abilities for the starting-
    # abilities option. Deliberately increment-only (matching how
    # grant_test_ability already works) rather than an exact-value setter --
    # KOTOR has no native "set ability score" call, only relative Effect-based
    # increases, so starting-ability presets are built by firing N of these,
    # not by clamping to a target the way set_xp/set_credits do.
    27: ("ability_strength", [
        'object oPC = GetFirstPC();',
        'int nBefore = GetAbilityScore(oPC, ABILITY_STRENGTH);',
        'ApplyEffectToObject(DURATION_TYPE_PERMANENT, EffectAbilityIncrease(ABILITY_STRENGTH, 1), oPC);',
        'int nAfter = GetAbilityScore(oPC, ABILITY_STRENGTH);',
        'KSE_Diag(58, "AP|APPLIED|ability_strength|before=" + IntToString(nBefore) + "|after=" + IntToString(nAfter));',
    ]),
    28: ("ability_dexterity", [
        'object oPC = GetFirstPC();',
        'int nBefore = GetAbilityScore(oPC, ABILITY_DEXTERITY);',
        'ApplyEffectToObject(DURATION_TYPE_PERMANENT, EffectAbilityIncrease(ABILITY_DEXTERITY, 1), oPC);',
        'int nAfter = GetAbilityScore(oPC, ABILITY_DEXTERITY);',
        'KSE_Diag(59, "AP|APPLIED|ability_dexterity|before=" + IntToString(nBefore) + "|after=" + IntToString(nAfter));',
    ]),
    29: ("ability_constitution", [
        'object oPC = GetFirstPC();',
        'int nBefore = GetAbilityScore(oPC, ABILITY_CONSTITUTION);',
        'ApplyEffectToObject(DURATION_TYPE_PERMANENT, EffectAbilityIncrease(ABILITY_CONSTITUTION, 1), oPC);',
        'int nAfter = GetAbilityScore(oPC, ABILITY_CONSTITUTION);',
        'KSE_Diag(60, "AP|APPLIED|ability_constitution|before=" + IntToString(nBefore) + "|after=" + IntToString(nAfter));',
    ]),
    30: ("ability_intelligence", [
        'object oPC = GetFirstPC();',
        'int nBefore = GetAbilityScore(oPC, ABILITY_INTELLIGENCE);',
        'ApplyEffectToObject(DURATION_TYPE_PERMANENT, EffectAbilityIncrease(ABILITY_INTELLIGENCE, 1), oPC);',
        'int nAfter = GetAbilityScore(oPC, ABILITY_INTELLIGENCE);',
        'KSE_Diag(61, "AP|APPLIED|ability_intelligence|before=" + IntToString(nBefore) + "|after=" + IntToString(nAfter));',
    ]),
    31: ("ability_wisdom", [
        'object oPC = GetFirstPC();',
        'int nBefore = GetAbilityScore(oPC, ABILITY_WISDOM);',
        'ApplyEffectToObject(DURATION_TYPE_PERMANENT, EffectAbilityIncrease(ABILITY_WISDOM, 1), oPC);',
        'int nAfter = GetAbilityScore(oPC, ABILITY_WISDOM);',
        'KSE_Diag(62, "AP|APPLIED|ability_wisdom|before=" + IntToString(nBefore) + "|after=" + IntToString(nAfter));',
    ]),
    # DeathLink incoming half -- modeled as just another arm, same delivery
    # latency as everything else (next area transition), not instant. True
    # low-latency delivery would need the extender to poke KOTOR's live
    # global-variable memory directly so the already-ticking heartbeat (see
    # ap_heartbeat.nss, 5s cadence, independent of area) picks it up sooner
    # -- that's unproven reverse-engineering, deliberately not attempted
    # here. This is the cheap, safe v1.
    32: ("force_death", [
        'object oPC = GetFirstPC();',
        'int nWasDead = GetIsDead(oPC);',
        'ApplyEffectToObject(DURATION_TYPE_INSTANT, EffectDeath(), oPC);',
        'KSE_Diag(63, "AP|APPLIED|force_death|wasDead=" + IntToString(nWasDead));',
    ]),
    # StartingClass=random_class (2026-09-02), base-class roll only -- a Jedi
    # roll reuses class_guardian/class_consular/class_sentinel above
    # (AddMultiClass) unchanged. AddMultiClass can't REPLACE an existing
    # base class, so a base-class roll needs the same direct-write
    # mechanism CompanionClass already uses for companions
    # (KSE_SetCreatureField) instead, targeting the PC. No Force write
    # (base classes aren't Force-sensitive, and the companion recipe's
    # Force=10 is Jedi-specific), no ShowLevelUpGUI (untested for this
    # "replace an already-created character's class" scenario, and the
    # companion recipe this mirrors doesn't call it either), no
    # CLASS0_LEVEL write (this only ever fires via generate_early()
    # precollection, immediately on a freshly created level-1 character,
    # so it's already 1).
    #
    # 2026-09-07 fix: the raw field write above NEVER touched feats on its
    # own -- confirmed live 2026-08-31 for the companion equivalent (a
    # class change alone leaves the OLD class's feats in place forever,
    # e.g. keeping Heavy Weapons after rolling into Scout). Now reads the
    # PC's real starting class live (GetClassByPosition, 1-based) BEFORE
    # overwriting it, and uses build_class_feat_delta_lines() to strip
    # exactly the old class's base feats the new class doesn't share, then
    # grant exactly the new class's base feats the old class didn't
    # already have -- see that function's docstring and GameMechanics.md
    # for the full base-feat-per-class data this is computed from.
    34: ("pc_class_soldier", [
        'object oPC = GetFirstPC();',
        'int nOldClass = GetClassByPosition(1, oPC);',
        *build_class_feat_delta_lines("CLASS_TYPE_SOLDIER", "oPC"),
        'KSE_SetCreatureField(oPC, KSE_FIELD_CLASS0_TYPE(), CLASS_TYPE_SOLDIER);',
        'KSE_Diag(9, "AP|APPLIED|pc_class_soldier");',
    ]),
    35: ("pc_class_scout", [
        'object oPC = GetFirstPC();',
        'int nOldClass = GetClassByPosition(1, oPC);',
        *build_class_feat_delta_lines("CLASS_TYPE_SCOUT", "oPC"),
        'KSE_SetCreatureField(oPC, KSE_FIELD_CLASS0_TYPE(), CLASS_TYPE_SCOUT);',
        'KSE_Diag(9, "AP|APPLIED|pc_class_scout");',
    ]),
    36: ("pc_class_scoundrel", [
        'object oPC = GetFirstPC();',
        'int nOldClass = GetClassByPosition(1, oPC);',
        *build_class_feat_delta_lines("CLASS_TYPE_SCOUNDREL", "oPC"),
        'KSE_SetCreatureField(oPC, KSE_FIELD_CLASS0_TYPE(), CLASS_TYPE_SCOUNDREL);',
        'KSE_Diag(9, "AP|APPLIED|pc_class_scoundrel");',
    ]),
    # 37/38 (dump_statblock_carth/juhani), 39-41 (carth_addmulticlass_hybrid_test/
    # juhani_addmulticlass_scoundrel_test/juhani_grant_critical_strike_test),
    # 42 (test_credits_chain), 43 (grant_implant_3), 44 (test_set_max_hp),
    # 45/46 (test_con_boost_effect/test_con_decrease_effect) ALL RETIRED
    # 2026-09-06 -- every research question they existed to answer is now
    # confirmed (results noted in each archived entry) and shipped as real
    # offsets/natives (see offsets.h's KSE_OBJ_CURRENT_HP_OFF/
    # KSE_FIELD_ADD_FORCE_POWER/KSE_FIELD_REMOVE_FORCE_POWER, kse_hook.cpp's
    # KseGetCurrentHP/KseForcePowerOp). Archived verbatim at
    # extender/research_archive/generate_trampoline_batch_temp_arms_2026-09-06.py.txt,
    # same gap convention as 12/15/16/33 above -- IDs never reused.
    # 47 (test_hp_fp_natives) and 48 (test_alignment_shift) RETIRED
    # 2026-09-06 -- both LIVE-CONFIRMED working (see kse.log results
    # archived below) the same night they were added. All four new
    # KseGetCurrentHP/KSE_FIELD_CURRENT_HP/ADD_FORCE_POWER/
    # REMOVE_FORCE_POWER capabilities, plus the standard AdjustAlignment()
    # action, are now confirmed shipped and working. Archived verbatim
    # (with the exact confirmed kse.log result lines) at
    # extender/research_archive/test_hp_fp_alignment_arms_2026-09-06.py.txt,
    # same gap-preserving convention as every other retired arm above --
    # IDs never reused.
    # 49 (test_add_100_hp) RETIRED 2026-09-06 -- confirmed the write
    # succeeds and reads back correctly at the instant of the write
    # (84->184), but current HP appears clamped back to Max HP once it
    # exceeds it (no visible change on the character sheet afterward) --
    # a sane engine invariant, not a bug, and not a real use case anyway.
    # Archived at extender/research_archive/test_hp_fp_alignment_arms_2026-09-06.py.txt.
    # 50 (test_lower_hp) RETIRED 2026-09-06 -- user-confirmed live: a
    # within-max current-HP write persisted correctly on the character
    # sheet past the instant of the write. Combined with arms 47/49, ALL
    # current-HP native behavior relevant to real features is now
    # confirmed. Archived at extender/research_archive/
    # test_hp_fp_alignment_arms_2026-09-06.py.txt.
    51: ("test_grant_active_feat", [
        # TEMPORARY (2026-09-06): live verification of whether granting an
        # ACTIVE/hotbar combat feat via KSE_GrantFeatArrayA (already
        # proven for PASSIVE feats only -- the 4 mandatory Jedi feats) also
        # makes it genuinely USABLE (hotbar-addable), not just present on
        # the character sheet. Blocks the planned Feats [Add/Remove]
        # equipment-access feature's "ability" pool, which includes real
        # active feats (Critical Strike, Flurry, Rapid Shot, Power Attack,
        # etc.) -- see GameMechanics.md. Grants Critical Strike (feat id
        # 8, a level-1 Scoundrel entitlement) to the PC regardless of
        # class, since the point is only whether the GRANT mechanism
        # works for an active feat, not whether the PC would normally
        # have it. User must check in-game (combat feats / hotbar screen)
        # whether it shows up as a usable ability, not just log output.
        'object oPC = GetFirstPC();',
        'int nHasBefore = GetHasFeat(8, oPC);',
        'KSE_GrantFeatArrayA(8, oPC);',
        'int nHasAfter = GetHasFeat(8, oPC);',
        'KSE_Diag(121, "AP|APPLIED|test_grant_active_feat|hadBefore=" + IntToString(nHasBefore) + "|hasAfter=" + IntToString(nHasAfter));',
    ]),
}


def build_set_xp_block(value):
    # Distinct diag name ("set_xp", not "xp") deliberately -- the extender's
    # delivery-confirmation logic maps AP|APPLIED|<name>|... back to a
    # pending queue entry, and set_xp is a different kind of queue entry
    # (a parameterized dict, replace-semantics) than the plain "xp" arm ID
    # (a discrete +500 grant, accumulate-semantics). Reusing the same name
    # would make the confirmation logic ambiguous about which one fired.
    #
    # A companion-XP-sync ("SetXP on party slots 1-2 too") was tried and
    # dropped -- confirmed live, three separate times, that SetXP (like
    # AddMultiClass and GiveXPToCreature before it) has zero effect on a
    # non-PC party member in this engine build. Nothing in NWScript can
    # modify a companion's core stats; only the game's own native
    # combat/leveling code can. Companions keep earning real, un-clamped
    # combat XP with no relation to the PC's granted-mode number -- an
    # accepted, permanent divergence, not a bug to keep chasing.
    return [
        "object oPC = GetFirstPC();",
        "int nBefore = GetXP(oPC);",
        f"SetXP(oPC, {value});",
        "int nAfter = GetXP(oPC);",
        'KSE_Diag(5, "AP|APPLIED|set_xp|before=" + IntToString(nBefore) + "|after=" + IntToString(nAfter));',
    ]


def build_set_credits_block(value):
    # Direct memory write via KSE_SetCredits (confirmed live 2026-09-03 --
    # see FutureDesign.md's credits-chain entries): resolves pRes fresh via
    # the confirmed native chain and writes the exact value to [pRes+0xFC].
    # Replaces the old GiveGoldToCreature/TakeGoldFromCreature delta dance
    # -- TakeGoldFromCreature was a confirmed no-op in this engine build,
    # so that old mechanism could only ever top credits up, never reduce
    # them (unlike set_xp's SetXP, a true absolute setter both directions).
    # KSE_SetCredits returns the value read back immediately after the
    # write, a genuine confirmation rather than an echo of the input --
    # nAfter should equal {value} exactly if the write landed.
    return [
        "object oPC = GetFirstPC();",
        "int nBefore = GetGold(oPC);",
        f"int nAfter = KSE_SetCredits(oPC, {value});",
        'KSE_Diag(39, "AP|APPLIED|set_credits|before=" + IntToString(nBefore) + "|after=" + IntToString(nAfter));',
    ]


def build_give_item_block(resref, count):
    # Generic gear-delivery action -- the resref and count are baked
    # directly into the freshly-regenerated source, same as set_xp/
    # set_credits's value. This is the ONE mechanism for every gear item
    # in gear_items.json: no per-item numbered arm ever needed, so adding
    # or changing gear items later is pure data (edit the JSON), never a
    # DLL rebuild. CreateItemOnObject alone (no AddMultiClass/
    # ShowLevelUpGUI/AddPartyMember) is not a HEAVY_ARMS-category
    # operation -- confirmed safe in large batches this session, same as
    # skills/abilities.
    #
    # granted_exempt_ marking (2026-08-29): CreateItemOnObject fires
    # Mod_OnAcquirItem the same as any real pickup (confirmed elsewhere in
    # this project -- it's why bonus-mode grants need their own debounce).
    # A real AP check reward delivered here is a completely separate code
    # path from patch_item_suppression.py's loot-pickup handler, but lands
    # in the SAME KSE_HasData("granted_exempt_"+sTag) check that handler
    # reads first, before its whitelist match -- so marking it here is
    # what stops a just-delivered check reward from being immediately
    # destroyed/replaced by that handler as if it were ordinary
    # unwhitelisted loot. Set BEFORE CreateItemOnObject, not after --
    # closes any theoretical ordering race between the mark and the
    # re-fire it's meant to guard against.
    return [
        "object oPC = GetFirstPC();",
        f'KSE_SetData("granted_exempt_{resref.lower()}", "1");',
        f'CreateItemOnObject("{resref}", oPC, {count});',
        f'KSE_Diag(81, "AP|APPLIED|give_item|resref={resref}|count={count}");',
    ]


# Companion key (matches KotorClient.py's COMPANION_IDX_TO_ARM suffix and
# Archipelago/worlds/kotor/__init__.py's COMPANION_KEYS) -> real in-game
# object tag, read directly from each companion's .utc via PyKotor rather
# than guessed -- Canderous's tag is "Cand", not "Canderous", which a
# guess would have gotten wrong silently (GetObjectByTag just never
# matches, no error, so this class of mistake never surfaces on its own).
_COMPANION_TAGS = {
    "bastila": "Bastila",
    "canderous": "Cand",
    "carth": "Carth",
    "jolee": "Jolee",
    "juhani": "Juhani",
    "mission": "Mission",
    "zaalbar": "Zaalbar",
}

_CLASS_NAME_TO_CONST = {
    "soldier": "CLASS_TYPE_SOLDIER",
    "scout": "CLASS_TYPE_SCOUT",
    "scoundrel": "CLASS_TYPE_SCOUNDREL",
    "guardian": "CLASS_TYPE_JEDIGUARDIAN",
    "consular": "CLASS_TYPE_JEDICONSULAR",
    "sentinel": "CLASS_TYPE_JEDISENTINEL",
}

# Companion key -> NPC_* constant, for the IsNPCPartyMember() guard in
# build_companion_class_block (see its docstring's 2026-08-31 fix note).
_COMPANION_NPC_CONST = {
    "bastila": "NPC_BASTILA",
    "canderous": "NPC_CANDEROUS",
    "carth": "NPC_CARTH",
    "jolee": "NPC_JOLEE",
    "juhani": "NPC_JUHANI",
    "mission": "NPC_MISSION",
    "zaalbar": "NPC_ZAALBAR",
}

# All 9 companions including the 2 droids -- _COMPANION_NPC_CONST above is
# deliberately non-droid-scoped (Randomize_class never targets HK-47/T3-M4),
# but the "Remove a Companion" trap has no such restriction (user's own
# spec: "a companion the player has access to", no exclusion), so it needs
# its own full map. NPC_HK_47/NPC_T3_M4 confirmed via
# generate_companion_suppressors.py's own suppression table.
_COMPANION_NPC_CONST_ALL = {**_COMPANION_NPC_CONST, "hk47": "NPC_HK_47", "t3m4": "NPC_T3_M4"}


def build_companion_class_block(name, class_name):
    """Companion-class-randomization action (Options.py's CompanionClass) --
    the one mechanism behind both no_jedi/randomize_all (queued by
    KotorClient.py right after a companion's recruit arm fires) and
    jedi_companion (queued as the arm_name of a real received AP item, see
    Items.py's "Jedi Training: <Name> (<Class>)" entries). Resolves the
    companion by their REAL object tag (see _COMPANION_TAGS) rather than
    GetPartyMemberByIndex -- unlike a freshly-CreateObject'd recruit, this
    action can fire independently of recruit timing (an item can arrive
    before OR after that companion joins), so it needs to find them
    wherever they currently are, not assume a party-slot index.

    Deliberately emits NO KSE_Diag("AP|APPLIED|...") when the companion
    isn't found (not yet recruited, e.g. CompanionMode=ap_gated and their
    own recruit item hasn't landed yet) -- the existing pending-queue
    retry (arm_orchestrator.py's --queue-companion-class=/--delivered=)
    re-fires this exact same action on the player's next area transition
    until it actually lands, same "one-transition delivery lag" every
    other arm already relies on. No new retry logic needed.

    2026-08-31 fix: the "found" check used to be plain
    GetIsObjectValid(oCompanion) on a GetObjectByTag() lookup. Confirmed
    live this session (Carth) that this is not sufficient -- a Carth-
    tagged object can exist and resolve as valid well before he's an
    actual party member (e.g. his own pre-recruit map/cutscene instance),
    so the class write landed, reported AP|APPLIED, and got marked
    delivered -- but then silently vanished once the real recruit arm's
    CreateObject(..., "p_carth", ...) later spawned the actual persistent
    companion instance from a fresh template, discarding the earlier
    write entirely. Now additionally gated on IsNPCPartyMember(<npc
    const>) -- the real "is this the companion that's actually going to
    stick" signal -- so a too-early grant correctly falls through to the
    no-Diag/retry path above instead of silently succeeding on the wrong
    object.

    Recipe (level 1 + 10 Force) is the exact one confirmed live this
    session on Zaalbar -> Level 20 Jedi Guardian, 76 Force -- KOTOR's own
    companion auto-level-sync catches them up to the party's real level
    over subsequent play, same as it did there.

    2026-08-31 addition: also grants/removes the feats a real Jedi
    level-up would automatically grant that KSE_SetCreatureField's class
    write alone does not -- Jedi Defense (feat 55), Lightsaber
    Proficiency (feat 43, WEAPON_PROF_LIGHTSABER), Force Sensitivity
    (feat 116, FORCE_SENSITIVE -- without this a non-Jedi-turned-Jedi
    companion couldn't use Force powers at all), and Jedi Sense (feat 107).
    All four confirmed JEDI-EXCLUSIVE via feat.2da's own
    per-class "granted at level" columns (jcn/jgd/jsn_granted=1, AND
    scd/sol/sct_granted=-1 for all three base classes) -- not guessed, and
    not assumed just because the name sounds Jedi-flavored. Two other
    candidates from the same level-1 auto-grant set (Weapon Prof: Blaster,
    Weapon Prof: Melee Weapons) were checked the same way and explicitly
    EXCLUDED -- both show granted=1 for ALL SIX classes, base classes
    included, confirmed universal baseline proficiencies, not something a
    class switch should ever touch (see FutureDesign.md's "Force Powers +
    Feats reference data" entry for the full table and reasoning). Found
    live: a companion switched AWAY from a Jedi class (Jolee -> Soldier)
    could still wield a lightsaber, because the class write never touches
    the feat list. Deliberately just these four (not the tiered
    Advanced/Master Jedi Defense, Weapon Focus/Specialization: Lightsaber,
    or the level-6/12 tiers like Knight/Master Sense) -- matches the exact
    scope the user asked for, not everything a real multi-level Jedi
    progression would eventually grant. Uses K1SE's own proven
    KSE_GrantFeatArrayA/KSE_RemoveFeatArrayA (routines 618/634) -- no new
    native needed.
    Removal of a feat the creature doesn't hold is a safe no-op
    (drain-and-rebuild finds nothing to remove); granting a feat already
    held is likewise not expected to duplicate (K1SE's own adder is the
    same one real level-up uses).

    2026-08-31 addition: on the REMOVAL path (switching AWAY from Jedi)
    also force-unequips a lightsaber from either weapon slot, AND a Jedi
    robe from the body slot. Confirmed live: removing feat 43 (Lightsaber
    Proficiency) correctly blocks RE-equipping a lightsaber afterward
    (verified by manually unequipping then trying to put it back on), but
    the engine never retroactively unequips an item just because the
    underlying proficiency feat was pulled -- equip legality is only
    checked at equip-time. Without this, a companion already wielding
    Jedi-exclusive gear at the moment of the switch keeps right on using
    it, illegally, indefinitely. Base item types 8/9/10
    (BASE_ITEM_LIGHTSABER/_DOUBLE_BLADED_LIGHTSABER/_SHORT_LIGHTSABER)
    checked in both INVENTORY_SLOT_RIGHTWEAPON and _LEFTWEAPON (dual-wield
    case). Robes were initially assumed unrestricted (a wrong guess,
    corrected same session) -- confirmed via baseitems.2da that all three
    tiers (BASE_ITEM_JEDI_ROBE/_JEDI_KNIGHT_ROBE/_JEDI_MASTER_ROBE, rows
    35/36/37) carry reqfeat0=55 (Jedi Defense), the exact feat this same
    removal path already strips -- so robes have the identical
    can't-re-equip-but-stays-on-if-already-worn gap as lightsabers, now
    checked in INVENTORY_SLOT_BODY the same way. Real armor (non-robe) is
    deliberately left alone -- non-Jedi classes have no equip restriction
    on it at all, nothing illegal to strip.

    2026-09-03 fix (promoted from temporary arm 39's proof-of-concept, see
    FutureDesign.md's "FINAL CONFIRMED SCOPE, Force Powers hotbar bug"
    entry): granting a companion a JEDI class they didn't already have
    used to go through the same raw KSE_SetCreatureField(CLASS0_TYPE)
    overwrite as every other direction -- confirmed live to leave newly-
    granted Force Powers sheet-visible but never hotbar-usable, since a
    direct field write skips the engine's own class-change housekeeping
    entirely. Now branches at runtime on whether the companion is
    CURRENTLY Jedi (checked via GetLevelByClass, not assumed from the
    target class alone -- randomize_all can roll a class change for an
    ALREADY-Jedi companion too): base-to-Jedi uses the real
    AddMultiClass() native (always lands in Class1) + a
    KSE_FIELD_CLASS1_LEVEL patch to 1 (AddMultiClass leaves it at 0, and
    no companion-equivalent of ShowLevelUpGUI() exists to level it up
    naturally) -- no separate Force-point write, since AddMultiClass's own
    housekeeping is trusted to initialize that correctly, unlike the raw
    field write. Every OTHER direction (already-Jedi or targeting a base
    class) keeps the original CLASS0_TYPE/CLASS0_LEVEL/FORCE overwrite
    unchanged -- confirmed NOT broken for Jedi-to-base (see the same
    FutureDesign.md entry) and never shown broken for the Jedi-to-
    different-Jedi case either, so left on the proven path rather than
    risking an untested AddMultiClass-onto-an-already-Jedi-Class0
    interaction. Feat grants/removals and the lightsaber/robe equip-swap
    run unconditionally either way -- redundant-but-harmless if
    AddMultiClass's own housekeeping already granted them (K1SE's adder is
    the same one real level-up uses, confirmed safe to re-fire).

    2026-09-07 fix: the base-class-target branch used to ONLY strip the 4
    universal Jedi feats, unconditionally, regardless of what the
    companion's class actually was -- confirmed a real gap via
    GameMechanics.md's base-feat-per-class data: a base-to-base switch
    (e.g. Soldier -> Scout) never granted/stripped anything at all (keeps
    Power Attack/Heavy Weapons forever, never gains Flurry/Rapid Shot), and
    a Jedi-to-base switch never stripped that Jedi's own unique power feat
    (Force Jump/Focus/Immunity Fear). Now reads the companion's real
    CURRENT class live (GetClassByPosition, 1-based) before either branch
    touches anything, and the base-class-target branch uses the same
    build_class_feat_delta_lines() helper the PC's own pc_class_soldier/
    scout/scoundrel arms use -- strips exactly the old class's base feats
    the new class doesn't share, grants exactly the new class's base feats
    the old class didn't already have. Same session, also added each Jedi
    class's own unique power feat (Force Jump=101/Force Focus=88/Force
    Immunity: Fear=98) to the Jedi-target grant list below, via the same
    proven DelayCommand pattern -- previously only the 4 UNIVERSAL Jedi
    feats were granted, never the class-specific one.

    KNOWN REMAINING GAP, deliberately not closed this pass: granting a
    Jedi class does NOT strip the companion's OLD non-shared feats (e.g. a
    Soldier who becomes a Guardian keeps Armor Prof Heavy/Power Attack
    forever), and an already-Jedi companion rolling a DIFFERENT Jedi class
    keeps their old unique power feat alongside the new one (e.g. Force
    Jump AND Force Focus both present) -- the base-class-target branch got
    the full delta treatment because that was the explicit ask; the
    Jedi-target branch only got the missing grant added, not a symmetric
    strip. Revisit if this asymmetry turns out to matter in practice."""
    tag = _COMPANION_TAGS[name]
    npc_const = _COMPANION_NPC_CONST[name]
    class_const = _CLASS_NAME_TO_CONST[class_name]
    is_jedi = class_name in ("guardian", "consular", "sentinel")
    _JEDI_FEATS = (55, 43, 116, 107)  # Jedi Defense, Lightsaber Proficiency, Force Sensitivity, Jedi Sense
    _JEDI_UNIQUE_POWER_FEAT = {"guardian": 101, "consular": 88, "sentinel": 98}  # Force Jump/Focus/Immunity:Fear
    old_class_read_lines = ["    int nOldClass = GetClassByPosition(1, oCompanion);"]
    if is_jedi:
        # 2026-09-03 fix, found live testing Canderous: granting these
        # immediately after AddMultiClass() in the same script pass lost
        # 2 of 4 feats (Jedi Sense/Force Sensitivity gone; Lightsaber
        # Proficiency/Jedi Defense survived) -- confirmed live, reproduced.
        # Read: AddMultiClass()'s own real class-init (the whole reason
        # it's used over a raw field write) evidently does its own feat
        # settling that isn't fully synchronous within the same tick, and
        # it happens to include Lightsaber Prof/Jedi Defense as real
        # per-class level-1 entitlements but NOT Sense/Force-Sensitive (no
        # class grants those at level 1) -- so its later-settling rebuild
        # silently overwrote our two "extra" grants that aren't part of
        # any class's real entitlement table, while leaving the other two
        # alone (either untouched or harmlessly re-granted). Delaying our
        # grants lets them land AFTER that settling instead of racing it.
        # CONFIRMED FIXED live (2026-09-03): Mission, a genuinely clean
        # base-to-Jedi test subject (fresh save, never touched before this
        # test), got all 4 feats via this delayed path -- Jedi Sense and
        # Force Sensitivity both landed this time. The old
        # (non-AddMultiClass) removal path below has no such race, so it
        # stays immediate/unchanged. The class-specific unique power feat
        # (added 2026-09-07) rides the same delayed grant, untested on its
        # own but no reason to expect it behaves differently from the
        # other 4 -- same host, same timing.
        feat_lines = [
            f"    DelayCommand(1.0, KSE_GrantFeatArrayA({feat}, oCompanion));"
            for feat in (*_JEDI_FEATS, _JEDI_UNIQUE_POWER_FEAT[class_name])
        ]
    else:
        feat_lines = build_class_feat_delta_lines(class_const, "oCompanion", old_class_var="nOldClass", delay_grants=False)
    _LIGHTSABER_CHECK = (
        "nBase{n} == BASE_ITEM_LIGHTSABER || nBase{n} == BASE_ITEM_SHORT_LIGHTSABER"
        " || nBase{n} == BASE_ITEM_DOUBLE_BLADED_LIGHTSABER"
    )
    _ROBE_CHECK = (
        "nBase3 == BASE_ITEM_JEDI_ROBE || nBase3 == BASE_ITEM_JEDI_KNIGHT_ROBE"
        " || nBase3 == BASE_ITEM_JEDI_MASTER_ROBE"
    )
    unequip_lines = []
    if not is_jedi:
        for n, slot in ((1, "INVENTORY_SLOT_RIGHTWEAPON"), (2, "INVENTORY_SLOT_LEFTWEAPON")):
            unequip_lines += [
                f"    object oWpn{n} = GetItemInSlot({slot}, oCompanion);",
                f"    if (GetIsObjectValid(oWpn{n}))",
                "    {",
                f"        int nBase{n} = GetBaseItemType(oWpn{n});",
                f"        if ({_LIGHTSABER_CHECK.format(n=n)})",
                "        {",
                f"            AssignCommand(oCompanion, ActionUnequipItem(oWpn{n}, TRUE));",
                "        }",
                "    }",
            ]
        unequip_lines += [
            "    object oBody3 = GetItemInSlot(INVENTORY_SLOT_BODY, oCompanion);",
            "    if (GetIsObjectValid(oBody3))",
            "    {",
            "        int nBase3 = GetBaseItemType(oBody3);",
            f"        if ({_ROBE_CHECK})",
            "        {",
            "            AssignCommand(oCompanion, ActionUnequipItem(oBody3, TRUE));",
            "        }",
            "    }",
        ]
    _OLD_PATH = [
        f"        KSE_SetCreatureField(oCompanion, KSE_FIELD_CLASS0_TYPE(), {class_const});",
        "        KSE_SetCreatureField(oCompanion, KSE_FIELD_CLASS0_LEVEL(), 1);",
        "        KSE_SetCreatureField(oCompanion, KSE_FIELD_FORCE(), 10);",
    ]
    if is_jedi:
        # Runtime branch: base-to-Jedi (the direction confirmed broken under
        # the raw field write) uses AddMultiClass + a Class1 level patch --
        # see this function's docstring's 2026-09-03 entry. An
        # already-Jedi companion rolling a DIFFERENT Jedi class under
        # randomize_all stays on the old, unmodified path (never shown
        # broken, and AddMultiClass onto an already-Jedi Class0 is
        # untested).
        #
        # 2026-09-03 addendum, found live testing Mission: the original
        # recipe only patched Class1's level to 1 and left Class0's
        # EXISTING level untouched (confirmed live: Scoundrel level 3 +
        # Guardian level 1). KOTOR's own companion auto-level-sync compares
        # TOTAL character level against the party's expected total to
        # decide whether to add a level at all -- with Class0 already at 3,
        # her total (4) may already read as "caught up," permanently
        # starving Class1 of the level-ups that would grant more Force
        # Powers. Reset Class0's level to 1 too, so both classes start
        # even and have real room for the auto-sync to add levels to
        # either side as the party progresses. Not yet confirmed this
        # actually unblocks leveling -- a reasonable next step to try
        # live, not a proven fix like the AddMultiClass call itself.
        class_lines = [
            "    int nWasJedi = GetLevelByClass(CLASS_TYPE_JEDIGUARDIAN, oCompanion) > 0 ||",
            "                   GetLevelByClass(CLASS_TYPE_JEDICONSULAR, oCompanion) > 0 ||",
            "                   GetLevelByClass(CLASS_TYPE_JEDISENTINEL, oCompanion) > 0;",
            "    if (!nWasJedi)",
            "    {",
            f"        AddMultiClass({class_const}, oCompanion);",
            "        KSE_SetCreatureField(oCompanion, KSE_FIELD_CLASS1_LEVEL(), 1);",
            "        KSE_SetCreatureField(oCompanion, KSE_FIELD_CLASS0_LEVEL(), 1);",
            "    }",
            "    else",
            "    {",
            *_OLD_PATH,
            "    }",
        ]
    else:
        # Target is a base class -- the WRITE mechanism itself is always
        # this same raw field overwrite, unchanged regardless of the
        # companion's current class (confirmed not broken for
        # Jedi-to-base; see this function's docstring). What DOES depend
        # on the current class now is feat_lines above, computed from
        # nOldClass (read below, before this write happens).
        class_lines = [line[4:] for line in _OLD_PATH]  # de-indent by one level, no runtime branch needed
    return [
        f'object oCompanion = GetObjectByTag("{tag}");',
        f"if (IsNPCPartyMember({npc_const}) && GetIsObjectValid(oCompanion))",
        "{",
        *old_class_read_lines,
        *class_lines,
        *feat_lines,
        *unequip_lines,
        f'    KSE_Diag(109, "AP|APPLIED|companion_class|name={name}|class={class_name}");',
        "}",
    ]


def build_additional_feats_block(name, feat_ids):
    """AdditionalFeats action (Options.py, 2026-09-07) -- grants exactly
    3 feats (feat_ids, already chosen client-side, see KotorClient.py's
    _check_pending_additional_feats/ADDITIONAL_FEATS_POOL) to either the
    PC (name == "pc") or a named companion, resolved by their real object
    tag (see _COMPANION_TAGS) the same way build_companion_class_block
    does -- an item-triggered action, not tied to recruit timing, so it
    needs to find the companion wherever they currently are. Companion
    targets get the same IsNPCPartyMember guard build_companion_class_block
    uses, for the same reason (a tagged object can exist and resolve as
    valid before/after they're actually a real party member).

    Every grant is guarded with a live GetHasFeat check -- belt and
    suspenders against the rare case where a character's real feat state
    already has something from this pool that KotorClient.py's own
    bookkeeping didn't account for (an incidental vanilla template pick,
    or an overlap with a class-change action's own grants). See
    GameMechanics.md for the pool's derivation.

    No target-not-found retry logic needed beyond the existing "no Diag
    emitted -> pending-queue retry fires this again next transition"
    pattern every other item-triggered action already relies on (see
    build_companion_class_block's own docstring) -- KotorClient.py's
    recruited/class-finalized gating already means this only ever fires
    once the target is known to exist, but the guard costs nothing."""
    if name == "pc":
        resolve_lines = ["object oTarget = GetFirstPC();"]
        guard = "GetIsObjectValid(oTarget)"
    else:
        tag = _COMPANION_TAGS[name]
        npc_const = _COMPANION_NPC_CONST[name]
        resolve_lines = [f'object oTarget = GetObjectByTag("{tag}");']
        guard = f"IsNPCPartyMember({npc_const}) && GetIsObjectValid(oTarget)"

    # 2026-09-08 fix #1: the confirmation used to just echo back feat_ids
    # verbatim ("feats=28,29,31"), which only proves the script ran to
    # completion -- NOT that each KSE_GrantFeatArrayA write actually took.
    # Confirmed live: Mission's additional_feats grant reported
    # feats=28,29,31 as APPLIED, but she came out with 28 and 31 while 29
    # (Power Blast) silently never landed. Now reports each feat's
    # "before" state (GetHasFeat right before the attempt).
    #
    # 2026-09-08 fix #2, root cause found via this same diagnostic on a
    # SECOND attempt: with the fix #1 diagnostic in place, a retry showed
    # ALL 3 requested feats at before=0/after=0 -- a complete, 100% write
    # failure for a companion target. This is the EXACT symptom already
    # solved once in build_companion_class_block's 2026-09-03 fix note:
    # granting feats to a companion immediately after AddMultiClass/class-
    # settling races the engine's own asynchronous feat-list rebuild,
    # which silently overwrites/discards the immediate grant. That fix's
    # proven remedy -- DelayCommand(1.0, KSE_GrantFeatArrayA(...)) instead
    # of an immediate call -- is applied here too, but ONLY for companion
    # targets (name != "pc"); the PC path has never shown this symptom
    # (additional_feats:pc's own live test only ever hit the SEPARATE
    # already-known-feat no-op case, never a genuine failed write), so it
    # stays immediate rather than adding an unproven delay with no
    # evidence it's needed.
    #
    # Delaying the grant means an immediate post-grant GetHasFeat read
    # would always show the PRE-delay state (NWScript evaluates
    # DelayCommand's argument expression immediately, only the outermost
    # action itself is deferred -- there is no cheap way to read the true
    # post-delay state from this same script without a custom helper
    # function, which build_notify_chain's own docstring already
    # documents as a fragile path in this codegen, given NWScript's
    # forward-declaration-order requirement). So for companions this now
    # honestly reports "before" + "delayed=1" instead of a fabricated
    # same-tick "after" that would always read wrong. Real confirmation
    # is a live in-game feat-sheet check a few seconds later, same as
    # build_companion_class_block's own verification story.
    # 2026-09-08 fix #3: fix #2's DelayCommand wrap didn't help either --
    # confirmed live on Bastila, who NEVER goes through AddMultiClass at
    # all under jedi_companion mode (trivially class-finalized, no roll
    # ever happens for her) -- her grant still failed the same way. That
    # rules out the AddMultiClass-settling race entirely; whatever's
    # actually wrong is unrelated to timing. The one remaining concrete
    # difference from build_companion_class_block's PROVEN-working Jedi-
    # feat grant (Canderous, confirmed live, all 4 feats landed) is that
    # proven path grants UNCONDITIONALLY -- no GetHasFeat guard at all --
    # while this one guards each grant with `if (!GetHasFeat(...))`
    # first. Matching the proven pattern exactly: companion grants are now
    # unconditional (still harmless if already known, same reasoning
    # build_companion_class_block's own docstring gives for its redundant-
    # but-harmless re-grants) and drop the guard. This is a hypothesis
    # test, not a confirmed fix -- needs a live re-check, same as the
    # last two attempts.
    grant_lines = []
    report_parts = []
    delay_grants = name != "pc"
    for i, feat in enumerate(feat_ids):
        grant_lines.append(f"    int nHadFeat{i} = GetHasFeat({feat}, oTarget);")
        if delay_grants:
            grant_lines.append(f"    DelayCommand(1.0, KSE_GrantFeatArrayA({feat}, oTarget));")
            report_parts.append(f'"{feat}:before=" + IntToString(nHadFeat{i}) + ":delayed=1"')
        else:
            grant_lines += [
                f"    if (!nHadFeat{i})",
                "    {",
                f"        KSE_GrantFeatArrayA({feat}, oTarget);",
                "    }",
                f"    int nHasFeat{i} = GetHasFeat({feat}, oTarget);",
            ]
            report_parts.append(
                f'"{feat}:" + IntToString(nHadFeat{i}) + "->" + IntToString(nHasFeat{i})'
            )

    feats_report_expr = ' + "," + '.join(report_parts)
    return [
        *resolve_lines,
        f"if ({guard})",
        "{",
        *grant_lines,
        f'    KSE_Diag(122, "AP|APPLIED|additional_feats|name={name}|feats=" + {feats_report_expr});',
        "}",
    ]


def build_trap_block(trap_type, params_str):
    """Traps action (Options.py's EnableTraps, 2026-09-08) -- ONE
    consolidated wire action ("trap:<trap_type>:<params_str>", see
    KotorClient.py's _deliver_item interception and
    kotor_extender_bridge.py's send_trap) covering all 12 trap items,
    mirroring additional_feats' shape: the item itself
    (arm_name="trap:<trap_type>", Items.py's TRAP_ITEMS) is just a
    marker, and every real specific (which feat/power ids, which
    companion, how much to reduce a stat by, the new level/XP) is
    computed client-side from the character's actual live state at the
    moment of delivery, then passed in here pre-encoded as params_str.
    PC-only for every trap except remove_companion (which targets
    whichever companion params_str names, never the PC).

    Every branch below reuses an ALREADY-PROVEN native -- see
    FutureDesign.md's Traps research entry for exactly which:
    KSE_SetCredits (credits), KSE_SetCreatureField's CLASS0_LEVEL/
    CLASS1_LEVEL fields + SetXP (level), KSE_RemoveFeatArrayA (feats),
    KSE_SetCreatureField's REMOVE_FORCE_POWER field (force powers),
    EffectAbilityDecrease (Max HP via Constitution, and the 5 standalone
    ability traps), RemoveAvailableNPC (companion removal, confirmed live
    to eject an ACTIVE party member, not just mark unavailable), and the
    existing GetFirstItemInInventory/GetNextItemInInventory/DestroyObject
    walk (inventory removal, same pattern as ap_remove_test_item.nss).
    No new native code needed for any of the 12.

    "remove_credits" is deliberately NOT one of the cases below --
    KotorClient.py calls the ALREADY-EXISTING set_credits action
    directly for that one (see build_set_credits_block), since it's
    already an exact byte-for-byte match for what this trap needs.
    """
    lines = ["object oPC = GetFirstPC();"]

    if trap_type == "reduce_skill":
        # Retired cut_level's replacement (2026-09-08) -- cut_level's
        # SetXP(oPC, new_xp) call silently no-op'd once the character had
        # already banked XP past the current level's threshold (confirmed
        # live: level field dropped, XP didn't), leaving level and XP
        # inconsistent with no reliable fix. EffectSkillDecrease is a
        # plain vanilla effect with no such threshold -- same pattern
        # already proven live for the 5 ability traps below.
        # params_str = "<skill_key>:<decrease_amount>"
        skill_key, amount = params_str.split(":")
        skill_const = {
            "computeruse": "SKILL_COMPUTER_USE", "demolitions": "SKILL_DEMOLITIONS",
            "stealth": "SKILL_STEALTH", "awareness": "SKILL_AWARENESS",
            "persuade": "SKILL_PERSUADE", "repair": "SKILL_REPAIR",
            "security": "SKILL_SECURITY", "treatinjury": "SKILL_TREAT_INJURY",
        }[skill_key]
        lines += [
            f"int nBefore = GetSkillRank({skill_const}, oPC);",
            f"ApplyEffectToObject(DURATION_TYPE_PERMANENT, EffectSkillDecrease({skill_const}, {amount}), oPC);",
            f"int nAfter = GetSkillRank({skill_const}, oPC);",
            f'KSE_Diag(134, "AP|APPLIED|trap|type=reduce_skill|skill={skill_key}|before=" + IntToString(nBefore) + "|after=" + IntToString(nAfter));',
        ]

    elif trap_type == "remove_half_feats":
        # params_str = "<id1>,<id2>,..." -- already exactly half (or the
        # whole set minus one), rounded/picked client-side; guarded with
        # a live GetHasFeat check the same defensive way
        # build_additional_feats_block's own grants are guarded.
        ids = [i for i in params_str.split(",") if i]
        for feat_id in ids:
            lines += [
                f"if (GetHasFeat({feat_id}, oPC))",
                "{",
                f"    KSE_RemoveFeatArrayA({feat_id}, oPC);",
                "}",
            ]
        lines.append(f'KSE_Diag(134, "AP|APPLIED|trap|type=remove_half_feats|ids={params_str}");')

    elif trap_type == "remove_half_powers":
        # params_str = "<id1>,<id2>,..." -- spells.2da row ids, same
        # KSE_FIELD_REMOVE_FORCE_POWER() field write confirmed live in
        # this project's own retired research arm 47 (add/remove/
        # remove-again on FORCE_POWER_CURE, all three passed first try).
        ids = [i for i in params_str.split(",") if i]
        for power_id in ids:
            lines += [
                f"if (GetHasSpell({power_id}, oPC))",
                "{",
                f"    KSE_SetCreatureField(oPC, KSE_FIELD_REMOVE_FORCE_POWER(), {power_id});",
                "}",
            ]
        lines.append(f'KSE_Diag(134, "AP|APPLIED|trap|type=remove_half_powers|ids={params_str}");')

    elif trap_type == "cut_max_hp":
        # params_str = "<con_decrease_amount>" -- already computed
        # client-side to get as close to half Max HP as this character's
        # build allows (fixed hit-die term can't be reduced via CON
        # alone, see FutureDesign.md/Options.py's EnableTraps docstring).
        # Same EffectAbilityDecrease call confirmed live 2026-09-06 to
        # correctly recompute Max HP downward, formula-exact.
        amount = params_str
        lines += [
            "int nMaxBefore = GetMaxHitPoints(oPC);",
            f"ApplyEffectToObject(DURATION_TYPE_PERMANENT, EffectAbilityDecrease(ABILITY_CONSTITUTION, {amount}), oPC);",
            "int nMaxAfter = GetMaxHitPoints(oPC);",
            f'KSE_Diag(134, "AP|APPLIED|trap|type=cut_max_hp|maxbefore=" + IntToString(nMaxBefore) + "|maxafter=" + IntToString(nMaxAfter));',
        ]

    elif trap_type == "remove_companion":
        # params_str = "<companion_key>" -- one of the 9 real keys (see
        # _COMPANION_NPC_CONST_ALL), a random currently-recruited one
        # chosen client-side (KotorClient.py's own _recruited_companions
        # tracking). RemoveAvailableNPC confirmed live (see
        # generate_companion_suppressors.py) to eject an ACTIVE party
        # member outright, not just mark them unavailable -- exactly the
        # trap behavior wanted, no extra RemovePartyMember call needed.
        name = params_str
        npc_const = _COMPANION_NPC_CONST_ALL[name]
        lines = [  # no oPC needed for this one -- overwrite the default line
            f"RemoveAvailableNPC({npc_const});",
            f'KSE_Diag(134, "AP|APPLIED|trap|type=remove_companion|name={name}");',
        ]

    elif trap_type == "remove_half_inventory":
        # params_str = "<tag1>,<tag2>,..." -- backpack-only (equipped
        # slots never eligible, quest_dependent items never eligible --
        # both filtered client-side before this fires), already chosen as
        # half the real backpack contents. One independent walk per tag
        # (simpler to generate correctly than a single-pass multi-tag
        # walker, and this only ever fires once per trap): same
        # find-then-destroy-then-stop pattern as ap_remove_test_item.nss,
        # deliberately not advancing the iterator once a match is found
        # (avoids mutating the list mid-walk).
        tags = [t for t in params_str.split(",") if t]
        for tag in tags:
            lines += [
                "{",
                "    object oItem = GetFirstItemInInventory(oPC);",
                "    while (GetIsObjectValid(oItem))",
                "    {",
                f'        if (GetTag(oItem) == "{tag}")',
                "        {",
                "            DestroyObject(oItem);",
                "            oItem = OBJECT_INVALID;",
                "        }",
                "        else",
                "        {",
                "            oItem = GetNextItemInInventory(oPC);",
                "        }",
                "    }",
                "}",
            ]
        lines.append(f'KSE_Diag(134, "AP|APPLIED|trap|type=remove_half_inventory|tags={params_str}");')

    elif trap_type in ("reduce_str", "reduce_dex", "reduce_int", "reduce_wis", "reduce_cha"):
        # params_str = "<decrease_amount>" -- current score minus half,
        # computed client-side from the already-tracked ABILITYREPORT.
        # Same EffectAbilityDecrease call as cut_max_hp above, just a
        # different ability constant -- CON deliberately has no
        # standalone case here (Cut Max Health in Half already uses it).
        ability_const = {
            "reduce_str": "ABILITY_STRENGTH", "reduce_dex": "ABILITY_DEXTERITY",
            "reduce_int": "ABILITY_INTELLIGENCE", "reduce_wis": "ABILITY_WISDOM",
            "reduce_cha": "ABILITY_CHARISMA",
        }[trap_type]
        amount = params_str
        lines += [
            f"int nBefore = GetAbilityScore(oPC, {ability_const});",
            f"ApplyEffectToObject(DURATION_TYPE_PERMANENT, EffectAbilityDecrease({ability_const}, {amount}), oPC);",
            f"int nAfter = GetAbilityScore(oPC, {ability_const});",
            f'KSE_Diag(134, "AP|APPLIED|trap|type={trap_type}|before=" + IntToString(nBefore) + "|after=" + IntToString(nAfter));',
        ]

    else:
        raise ValueError(f"unknown trap_type: {trap_type}")

    return lines


def _nwscript_string_escape(text):
    """Minimal escaping for embedding arbitrary text (item/location/player
    names, which this project doesn't control the contents of) inside an
    NWScript string literal -- backslash first, then double-quote, same
    order any string-escaping needs to run in to avoid double-escaping a
    quote's own backslash."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def build_notify_chain(texts):
    """One-shot on-screen messages (check found / item received /
    connection status), via FloatingTextStringOnCreature.

    FINAL DESIGN (2026-08-29, after a long live-debugging chain -- kept
    for the next person who touches this): each text gets its own
    directly-delayed native call --
    `DelayCommand(fDelay, FloatingTextStringOnCreature(text, oPC, FALSE))`
    -- staggered by 1.5s per text, NO custom wrapper function involved.
    CONFIRMED WORKING for a single notification: shows up in KOTOR's
    feedback message log. Known, accepted limitation: if 2+ notifications
    land in the same batch, only the FIRST one displays -- multiple
    INDEPENDENT DelayCommand calls issued from the same originating
    script execution only honor the first one, confirmed live. Not
    chased further; single-notification is the common case (usually one
    check or one item between transitions) and this project's philosophy
    is to document a narrow, confirmed limitation rather than keep
    engineering around it (see [[kotor-project-status]]).

    Three other approaches were tried and abandoned, each confirmed
    broken through direct live testing, not assumption:
    - `AurPostString(string, nX, nY, fLife)` (nwscript.nss #582, posts
      text at a fixed screen column/row): confirmed executing
      (KSE_Diag/TRAMPOLINE_BATCH_FIRED fired correctly) but nothing ever
      appeared on screen, on two separate real area entries.
    - A self-rescheduling chain of custom `NotifyChain<i>()` functions
      (each displays its text, then DelayCommand's the next step) --
      built specifically to fix the "only first shows" limitation above,
      modeled on this project's own heartbeat's proven self-rescheduling
      pattern. First hit a real compile bug: NWScript requires a
      function be declared before it's referenced, and emitting
      NotifyChain0..N-1 in ascending order put NotifyChain0's reference
      to NotifyChain1 before NotifyChain1 existed in the file --
      "Undeclared identifier", confirmed via nwnnsscomp.exe directly.
      That failure was invisible through this project's own tooling
      (which only checked `os.path.exists(ncs_path)`, true even on a
      failed compile because a stale .ncs from an earlier successful
      build was already sitting there -- fixed as its own general
      lesson, see main()'s compile step). After fixing the compile order
      (functions in descending index order) and confirming a clean
      compile with nwnnsscomp.exe directly, the chain reliably fired
      (`TRAMPOLINE_BATCH_FIRED|count=3` confirmed in kse.log) but STILL
      never displayed anything -- not even reduced to a single, non-
      chained `NotifyChain0()` wrapper with zero forward-reference
      complexity at all. That isolated the real cause: calling
      FloatingTextStringOnCreature from WITHIN a custom function that
      DelayCommand targets doesn't work in this engine, even though
      calling it AS THE DIRECT target of DelayCommand does. Reverted to
      the direct-call design as a result.
    - `ActionSpeakString` (via `AssignCommand`): tried briefly in
      between, never confirmed either way before FloatingTextStringOnCreature
      was found to already work directly -- abandoned without further
      investigation once the direct-call form was confirmed.

    No KSE_Diag("AP|APPLIED|...") confirmation for any notify -- there's
    nothing to reconcile against (see arm_orchestrator.py's
    _pending_notify.json for how repeats are avoided without one). Each
    text truncated defensively -- an AP item/location/player name is
    attacker-uncontrolled but not length-bounded. Function name kept as
    build_notify_chain (not reverted to build_notify_block) since
    arm_orchestrator.py's docs and this file's own history already
    reference it under this name -- renaming back would just add churn
    for no behavioral reason."""
    if not texts:
        return "", []
    lines = []
    for i, text in enumerate(texts):
        safe = _nwscript_string_escape(text)[:200]
        delay = 1.5 * i
        lines.append("{")
        lines.append("    object oNotifyPC = GetFirstPC();")
        lines.append(f'    DelayCommand({delay}, FloatingTextStringOnCreature("{safe}", oNotifyPC, FALSE));')
        lines.append("}")
    return "", lines


# Module-prefix -> planet name, duplicated from
# Archipelago/worlds/kotor/__init__.py's PLANET_MODULE_PREFIXES (that file
# and this one are separate packages -- the apworld vs. dev tooling -- not
# worth a cross-package import for 5 entries that rarely change).
# 2026-09-08 FIX: "tat_m": "tatooine" was missing entirely -- see the
# matching fix + full explanation in Archipelago/worlds/kotor/__init__.py's
# PLANET_MODULE_PREFIXES (this dict's real source-of-truth counterpart).
# Without it, _planet_for_module() returned None for every Tatooine
# module, so shop_stock_by_planet.get(None, []) always resolved to an
# empty catalog -- Tatooine's 2 real stores (tat_m17ab/tat_m17ad) never
# got restocked with anything.
_PLANET_PREFIXES = {
    "tar_m": "taris",
    "danm": "dantooine",
    "kas_m": "kashyyyk",
    "manm": "manaan",
    "korr_m": "korriban",
    "tat_m": "tatooine",
}


def _planet_for_module(base):
    """Returns the planet name a module belongs to, or None if it's not
    one of the 5 covered planets (e.g. Endar Spire, Ebon Hawk, Star Forge --
    no shop stocking applies there regardless)."""
    for prefix, planet in _PLANET_PREFIXES.items():
        if base.startswith(prefix):
            return planet
    return None


def build_shop_stock_block(store_tags, resrefs):
    """One-time destroy-and-restock for each store tag in this area, gated
    by a LocalBoolean on the store object itself (not the module) -- so
    each store tracks its own restocked state independently with no index-
    assignment bookkeeping needed. Runs unconditionally on every entry into
    an area that has a store (regardless of the AP pending queue -- this
    isn't an AP-item grant, it's static seed configuration), but the
    boolean gate makes repeat entries a no-op. resrefs is the SAME
    universal list for every store (v1 design: one shared catalog, not a
    per-store selection)."""
    lines = []
    for i, tag in enumerate(store_tags):
        lines.append(f'object oShop{i} = GetObjectByTag("{tag}");')
        lines.append(f'if (GetIsObjectValid(oShop{i}) && !GetLocalBoolean(oShop{i}, 0))')
        lines.append('{')
        lines.append(f'    object oShopItem{i} = GetFirstItemInInventory(oShop{i});')
        lines.append(f'    while (GetIsObjectValid(oShopItem{i}))')
        lines.append('    {')
        lines.append(f'        DestroyObject(oShopItem{i});')
        lines.append(f'        oShopItem{i} = GetNextItemInInventory(oShop{i});')
        lines.append('    }')
        for resref in resrefs:
            lines.append(f'    CreateItemOnObject("{resref}", oShop{i}, 99);')
        lines.append(f'    SetLocalBoolean(oShop{i}, 0, TRUE);')
        lines.append(f'    KSE_Diag(82, "AP|SHOPSTOCKED|{tag}");')
        lines.append('}')
    return lines


def build_batch_block(batch_items):
    """batch_items is a mixed list: plain ints are fixed arm IDs (existing
    APPLIES table), dicts like {"action": "set_xp", "value": N} are
    parameterized exact-value actions -- the value is baked directly into
    the freshly-generated/recompiled source, no runtime parameter-passing
    channel needed (see the set_xp/set_credits design discussion).

    Returns (batch_body, notify_funcs) -- notify_funcs is currently
    always "" (kept in the return shape since callers already unpack a
    2-tuple; see build_notify_chain()'s docstring for why an earlier
    version of this DID need to return real helper-function definitions,
    and why that approach was abandoned). notify actions are pulled out
    of the normal per-item loop and collected separately, then handled
    once together at the end via build_notify_chain() -- see that
    function's docstring for the full design history and the known
    "only the first of several simultaneous notifications displays"
    limitation."""
    if not batch_items:
        return "", ""
    lines = ['        KSE_Diag(108, "AP|TRAMPOLINE_BATCH_FIRED|count=' + str(len(batch_items)) + '");']
    notify_texts = []
    extra_funcs = []
    for item in batch_items:
        if isinstance(item, dict):
            action = item["action"]
            if action == "give_item":
                resref, count = item["resref"], item["count"]
                label, body = "give_item", build_give_item_block(resref, count)
                lines.append(f"        // give_item={resref}:{count}")
            elif action == "companion_class":
                name, class_name = item["name"], item["class_name"]
                label, body = "companion_class", build_companion_class_block(name, class_name)
                lines.append(f"        // companion_class={name}:{class_name}")
            elif action == "additional_feats":
                name, feat_ids = item["name"], item["feat_ids"]
                label, body = "additional_feats", build_additional_feats_block(name, feat_ids)
                lines.append(f"        // additional_feats={name}:{feat_ids}")
            elif action == "trap":
                trap_type, params = item["trap_type"], item["params"]
                label, body = "trap", build_trap_block(trap_type, params)
                lines.append(f"        // trap={trap_type}:{params}")
            elif action == "notify":
                notify_texts.append(item["text"])
                continue  # handled once, together, after this loop -- not inlined per-item
            else:
                value = item["value"]
                if action == "set_xp":
                    label, body = "set_xp", build_set_xp_block(value)
                elif action == "set_credits":
                    label, body = "set_credits", build_set_credits_block(value)
                else:
                    raise ValueError(f"unknown parameterized action: {action}")
                lines.append(f"        // {label}={value}")
        else:
            arm_id = item
            label, body = APPLIES[arm_id]
            lines.append(f"        // arm {arm_id}: {label}")
        lines.append("        {")
        for stmt in body:
            lines.append(f"            {stmt}")
        lines.append("        }")

    notify_funcs, notify_lines = build_notify_chain(notify_texts)
    notify_funcs = notify_funcs + "".join(extra_funcs)
    if notify_lines:
        lines.append("        // notify: " + " | ".join(repr(t) for t in notify_texts))
        for stmt in notify_lines:
            lines.append(f"        {stmt}")
    return "\n".join(lines), notify_funcs


def main():
    global OVERRIDE_DIR
    args = sys.argv[1:]
    if not args:
        print("usage: generate_trampoline_batch.py <arm_id> [<arm_id> ...] [--areas base1,base2|--all] [--game-dir=<path>]")
        sys.exit(1)

    areas_arg = None
    all_areas = False
    batch_items = []  # mixed: int arm IDs, or {"action": ..., "value": ...} dicts
    for a in args:
        if a == "--all":
            all_areas = True
        elif a.startswith("--game-dir="):
            OVERRIDE_DIR = os.path.join(a.split("=", 1)[1], "Override")
        elif a.startswith("--areas="):
            areas_arg = a.split("=", 1)[1].split(",")
        elif a.startswith("set_xp:"):
            batch_items.append({"action": "set_xp", "value": int(a.split(":", 1)[1])})
        elif a.startswith("set_credits:"):
            batch_items.append({"action": "set_credits", "value": int(a.split(":", 1)[1])})
        elif a.startswith("give_item:"):
            _, resref, count = a.split(":", 2)
            batch_items.append({"action": "give_item", "resref": resref, "count": int(count)})
        elif a.startswith("companion_class:"):
            _, name, class_name = a.split(":", 2)
            batch_items.append({"action": "companion_class", "name": name, "class_name": class_name})
        elif a.startswith("additional_feats:"):
            _, name, feats_csv = a.split(":", 2)
            batch_items.append({"action": "additional_feats", "name": name, "feat_ids": [int(f) for f in feats_csv.split(",")]})
        elif a.startswith("trap:"):
            # trap:<trap_type>:<params> -- params' own internal shape
            # (comma-list, colon-pair, bare int, companion key) varies by
            # trap_type, so it's passed through as a raw string and only
            # build_trap_block() knows how to parse it further.
            _, trap_type, params = a.split(":", 2)
            batch_items.append({"action": "trap", "trap_type": trap_type, "params": params})
        elif a.startswith("notify:"):
            # Sliced, not split(":", 1) -- the text itself can legitimately
            # contain colons (e.g. "Received: X (from Y's Z)"), and slicing
            # off just the fixed "notify:" prefix leaves all of those alone.
            batch_items.append({"action": "notify", "text": a[len("notify:"):]})
        else:
            batch_items.append(int(a))

    with open(os.path.join(SRC_DIR, "_mapping.json")) as f:
        mapping = json.load(f)

    shop_map_path = os.path.join(SRC_DIR, "_shop_map.json")
    shop_map = {}
    if os.path.exists(shop_map_path):
        with open(shop_map_path) as f:
            shop_map = json.load(f)

    # Set once, at Connect, by KotorClient.py via the extender's SHOPSTOCK:
    # command (one message per planet) -- see arm_orchestrator.py's
    # --set-shop-stock= handling. {planet: [resrefs]}, one distinct catalog
    # per planet (2026-08-29 -- was a single universal list before). Empty
    # (file absent, or shop_item_count option is 0) means no shop area gets
    # a stocking block at all, same as vanilla.
    shop_stock_path = os.path.join(SRC_DIR, "_shop_stock.json")
    shop_stock_by_planet = {}
    if os.path.exists(shop_stock_path):
        with open(shop_stock_path) as f:
            shop_stock_by_planet = json.load(f)

    if all_areas:
        target_bases = list(mapping.keys())
    elif areas_arg:
        target_bases = areas_arg
    else:
        # default test target
        target_bases = ["tar_m02aa"]

    # group targets by onenter (mirrors generate_area_trampolines.py grouping)
    by_onenter = defaultdict(list)
    for base in target_bases:
        if base not in mapping:
            print(f"WARNING: {base} not in mapping, skipping")
            continue
        by_onenter[mapping[base]["onenter"]].append(base)

    batch_block, notify_funcs = build_batch_block(batch_items)

    for onenter, bases in by_onenter.items():
        # need the FULL group sharing this onenter (not just the targeted
        # subset) to rebuild the correct tag-dispatch report_block
        full_group = [b for b, info in mapping.items() if info["onenter"] == onenter]
        renamed_resref = mapping[full_group[0]]["renamed"]

        def shop_lines_for(base):
            store_tags = shop_map.get(base)
            if not store_tags:
                return []
            shop_stock_resrefs = shop_stock_by_planet.get(_planet_for_module(base), [])
            if not shop_stock_resrefs:
                return []
            return build_shop_stock_block(store_tags, shop_stock_resrefs)

        if len(full_group) == 1:
            base = full_group[0]
            idx = mapping[base]["idx"]
            lines = [f'        KSE_Diag(20, "AP|CHECK|AREA|{idx}");']
            lines.extend(f"        {stmt}" for stmt in shop_lines_for(base))
            report_block = "\n".join(lines)
        else:
            lines = ['        string sAreaTag = GetTag(GetArea(OBJECT_SELF));']
            for i, base in enumerate(full_group):
                idx = mapping[base]["idx"]
                kw = "if" if i == 0 else "else if"
                lines.append(f'        {kw} (sAreaTag == "{base}")')
                lines.append('        {')
                lines.append(f'            KSE_Diag(20, "AP|CHECK|AREA|{idx}");')
                lines.extend(f"            {stmt}" for stmt in shop_lines_for(base))
                lines.append('        }')
            report_block = "\n".join(lines)

        base_list_comment = ", ".join(full_group)
        notify_funcs_block = f"\n{notify_funcs}\n" if notify_funcs else ""
        trampoline_src = f"""// AUTO-GENERATED trampoline for OnEnter={onenter}, WITH a pending arm
// batch inlined (see generate_trampoline_batch.py). Covers: {base_list_comment}
#include "kse"
{notify_funcs_block}
void main()
{{
    ExecuteScript("{renamed_resref}", OBJECT_SELF);

    object oEnterer = GetEnteringObject();
    if (GetIsPC(oEnterer))
    {{
{report_block}
        ExecuteScript("ap_poll_shared", OBJECT_SELF);

{batch_block}
    }}
}}
"""
        nss_path = os.path.join(SRC_DIR, f"{onenter}.nss")
        with open(nss_path, "w") as f:
            f.write(trampoline_src)

        ncs_path = os.path.join(SRC_DIR, f"{onenter}.ncs")
        # Real bug found live (2026-08-29): `ok = os.path.exists(ncs_path)`
        # alone stays TRUE even when THIS compile fails, because a stale
        # .ncs from an earlier, unrelated successful build is already
        # sitting at that path -- nwnnsscomp.exe just leaves it untouched
        # on a compile error rather than deleting it. Confirmed live: a
        # NotifyChain forward-reference error ("Undeclared identifier")
        # silently redeployed a stale single-item .ncs on every single
        # multi-notify attempt, with zero visible indication anywhere.
        # Two independent checks now, both required: the file's own mtime
        # must have actually advanced (proves nwnnsscomp really wrote
        # something this call, not just that a file exists from before),
        # AND its own stdout must not contain the compiler's real
        # failure markers.
        mtime_before = os.path.getmtime(ncs_path) if os.path.exists(ncs_path) else None
        result = subprocess.run(
            [NWNNSSCOMP, "-c", nss_path, "-o", ncs_path],
            capture_output=True, text=True, cwd=SRC_DIR,
        )
        compiled_fresh = os.path.exists(ncs_path) and (
            mtime_before is None or os.path.getmtime(ncs_path) != mtime_before
        )
        compile_error = "Compilation aborted" in result.stdout or "Error:" in result.stdout
        ok = compiled_fresh and not compile_error
        if ok:
            dest = os.path.join(OVERRIDE_DIR, f"{onenter}.ncs")
            with open(ncs_path, "rb") as fsrc, open(dest, "wb") as fdst:
                fdst.write(fsrc.read())
        print(f"{onenter} (covers {base_list_comment}): {'OK' if ok else 'FAILED'}")
        if not ok:
            print(result.stdout, result.stderr)


if __name__ == "__main__":
    main()
