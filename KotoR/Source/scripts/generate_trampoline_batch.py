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
NWNNSSCOMP = r"C:\Program Files (x86)\KotOR Scripting Tool\nwnnsscomp.exe"

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
    9: ("companion_bastila", [
        'int nNPC = NPC_BASTILA;',
        'string sTemplate = "p_bastilla";',
        'int nWasAvailable = IsAvailableCreature(nNPC);',
        'AddAvailableNPCByTemplate(nNPC, sTemplate);',
        'object oPC = GetFirstPC();',
        'object oNPC = CreateObject(OBJECT_TYPE_CREATURE, sTemplate, GetLocation(oPC));',
        'int nAdded = AddPartyMember(nNPC, oNPC);',
        'KSE_Diag(4, "AP|APPLIED|companion_bastila|wasAvailable=" + IntToString(nWasAvailable) + "|added=" + IntToString(nAdded));',
    ]),
    10: ("companion_canderous", [
        'int nNPC = NPC_CANDEROUS;',
        'string sTemplate = "p_cand";',
        'int nWasAvailable = IsAvailableCreature(nNPC);',
        'AddAvailableNPCByTemplate(nNPC, sTemplate);',
        'object oPC = GetFirstPC();',
        'object oNPC = CreateObject(OBJECT_TYPE_CREATURE, sTemplate, GetLocation(oPC));',
        'int nAdded = AddPartyMember(nNPC, oNPC);',
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
    # RandomizeClass. Not reusing these IDs -- same reasoning as the other
    # retired-gap comments in this table (12, old-16).
    33: ("dump_statblock", [
        # TEMPORARY (2026-08-31): Force Powers offset research -- see
        # kotor_engine_constraints memory / PHASE14.md. Dumps 112 (0x70)
        # bytes starting at the PC's statBlock pointer (offset 0) to
        # kse.log as hex -- covers the 3 known {ptr,count,capacity}
        # feat-array/use-counter triples (0x00-0x23, per offsets.h's own
        # "the stat block opens with three consecutive triples" comment)
        # through XP (confirmed at +0x68), the candidate region for a 4th
        # such triple (Force Powers). Not a shipped feature -- retire this
        # arm (leave the gap, don't renumber) once the research pass is
        # done, same convention as every other retired arm in this table.
        'object oPC = GetFirstPC();',
        'KSE_DumpStatBlock(oPC, 0, 112);',
        'KSE_Diag(111, "AP|APPLIED|dump_statblock|offset=0|length=112");',
    ]),
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
        'AddAvailableNPCByTemplate(nNPC, sTemplate);',
        'object oPC = GetFirstPC();',
        'object oNPC = CreateObject(OBJECT_TYPE_CREATURE, sTemplate, GetLocation(oPC));',
        'int nAdded = AddPartyMember(nNPC, oNPC);',
        'KSE_Diag(50, "AP|APPLIED|companion_carth|wasAvailable=" + IntToString(nWasAvailable) + "|added=" + IntToString(nAdded));',
    ]),
    20: ("companion_hk47", [
        'int nNPC = NPC_HK_47;',
        'string sTemplate = "p_hk47";',
        'int nWasAvailable = IsAvailableCreature(nNPC);',
        'AddAvailableNPCByTemplate(nNPC, sTemplate);',
        'object oPC = GetFirstPC();',
        'object oNPC = CreateObject(OBJECT_TYPE_CREATURE, sTemplate, GetLocation(oPC));',
        'int nAdded = AddPartyMember(nNPC, oNPC);',
        'KSE_Diag(51, "AP|APPLIED|companion_hk47|wasAvailable=" + IntToString(nWasAvailable) + "|added=" + IntToString(nAdded));',
    ]),
    21: ("companion_jolee", [
        'int nNPC = NPC_JOLEE;',
        'string sTemplate = "p_jolee";',
        'int nWasAvailable = IsAvailableCreature(nNPC);',
        'AddAvailableNPCByTemplate(nNPC, sTemplate);',
        'object oPC = GetFirstPC();',
        'object oNPC = CreateObject(OBJECT_TYPE_CREATURE, sTemplate, GetLocation(oPC));',
        'int nAdded = AddPartyMember(nNPC, oNPC);',
        'KSE_Diag(52, "AP|APPLIED|companion_jolee|wasAvailable=" + IntToString(nWasAvailable) + "|added=" + IntToString(nAdded));',
    ]),
    22: ("companion_juhani", [
        'int nNPC = NPC_JUHANI;',
        'string sTemplate = "p_juhani";',
        'int nWasAvailable = IsAvailableCreature(nNPC);',
        'AddAvailableNPCByTemplate(nNPC, sTemplate);',
        'object oPC = GetFirstPC();',
        'object oNPC = CreateObject(OBJECT_TYPE_CREATURE, sTemplate, GetLocation(oPC));',
        'int nAdded = AddPartyMember(nNPC, oNPC);',
        'KSE_Diag(53, "AP|APPLIED|companion_juhani|wasAvailable=" + IntToString(nWasAvailable) + "|added=" + IntToString(nAdded));',
    ]),
    23: ("companion_mission", [
        'int nNPC = NPC_MISSION;',
        'string sTemplate = "p_mission";',
        'int nWasAvailable = IsAvailableCreature(nNPC);',
        'AddAvailableNPCByTemplate(nNPC, sTemplate);',
        'object oPC = GetFirstPC();',
        'object oNPC = CreateObject(OBJECT_TYPE_CREATURE, sTemplate, GetLocation(oPC));',
        'int nAdded = AddPartyMember(nNPC, oNPC);',
        'KSE_Diag(54, "AP|APPLIED|companion_mission|wasAvailable=" + IntToString(nWasAvailable) + "|added=" + IntToString(nAdded));',
    ]),
    24: ("companion_t3m4", [
        'int nNPC = NPC_T3_M4;',
        'string sTemplate = "p_t3m4";',
        'int nWasAvailable = IsAvailableCreature(nNPC);',
        'AddAvailableNPCByTemplate(nNPC, sTemplate);',
        'object oPC = GetFirstPC();',
        'object oNPC = CreateObject(OBJECT_TYPE_CREATURE, sTemplate, GetLocation(oPC));',
        'int nAdded = AddPartyMember(nNPC, oNPC);',
        'KSE_Diag(55, "AP|APPLIED|companion_t3m4|wasAvailable=" + IntToString(nWasAvailable) + "|added=" + IntToString(nAdded));',
    ]),
    25: ("companion_zaalbar", [
        'int nNPC = NPC_ZAALBAR;',
        'string sTemplate = "p_zaalbar";',
        'int nWasAvailable = IsAvailableCreature(nNPC);',
        'AddAvailableNPCByTemplate(nNPC, sTemplate);',
        'object oPC = GetFirstPC();',
        'object oNPC = CreateObject(OBJECT_TYPE_CREATURE, sTemplate, GetLocation(oPC));',
        'int nAdded = AddPartyMember(nNPC, oNPC);',
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
    # JediStart=random_class (2026-09-02), base-class roll only -- a Jedi
    # roll reuses class_guardian/class_consular/class_sentinel above
    # (AddMultiClass) unchanged. AddMultiClass can't REPLACE an existing
    # base class, so a base-class roll needs the same direct-write
    # mechanism RandomizeClass already uses for companions
    # (KSE_SetCreatureField) instead, targeting the PC. Deliberately
    # minimal -- no Force write (base classes aren't Force-sensitive, and
    # the companion recipe's Force=10 is Jedi-specific), no
    # ShowLevelUpGUI (untested for this "replace an already-created
    # character's class" scenario, and the companion recipe this mirrors
    # doesn't call it either), no CLASS0_LEVEL write (this only ever fires
    # via generate_early() precollection, immediately on a freshly
    # created level-1 character, so it's already 1).
    34: ("pc_class_soldier", [
        'object oPC = GetFirstPC();',
        'KSE_SetCreatureField(oPC, KSE_FIELD_CLASS0_TYPE(), CLASS_TYPE_SOLDIER);',
        'KSE_Diag(9, "AP|APPLIED|pc_class_soldier");',
    ]),
    35: ("pc_class_scout", [
        'object oPC = GetFirstPC();',
        'KSE_SetCreatureField(oPC, KSE_FIELD_CLASS0_TYPE(), CLASS_TYPE_SCOUT);',
        'KSE_Diag(9, "AP|APPLIED|pc_class_scout");',
    ]),
    36: ("pc_class_scoundrel", [
        'object oPC = GetFirstPC();',
        'KSE_SetCreatureField(oPC, KSE_FIELD_CLASS0_TYPE(), CLASS_TYPE_SCOUNDREL);',
        'KSE_Diag(9, "AP|APPLIED|pc_class_scoundrel");',
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
    # NWScript has no direct "set gold" call -- only relative
    # GiveGoldToCreature/TakeGoldFromCreature -- so compute the delta at
    # runtime and apply whichever direction closes it.
    #
    # CONFIRMED BROKEN: TakeGoldFromCreature is a complete no-op in this
    # engine build (tested directly: before/after identical regardless of
    # bDestroy TRUE or FALSE). GiveGoldToCreature works fine (used all
    # session). This means the nDelta<0 branch below never actually
    # reduces gold -- harmless under the current deficit-only reconciliation
    # policy (only ever calls this when expected > current, so only the
    # nDelta>0 branch is exercised), but a real blocker if this is ever
    # extended to also correct overages (unlike set_xp, whose SetXP is a
    # true absolute setter and works both directions fine).
    # See build_set_xp_block for why the diag name is "set_credits", not
    # "credits".
    return [
        "object oPC = GetFirstPC();",
        "int nBefore = GetGold(oPC);",
        f"int nTarget = {value};",
        "int nDelta = nTarget - nBefore;",
        "if (nDelta > 0) { GiveGoldToCreature(oPC, nDelta); }",
        "else if (nDelta < 0) { TakeGoldFromCreature(-nDelta, oPC, FALSE); }",
        "int nAfter = GetGold(oPC);",
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


def build_companion_class_block(name, class_name):
    """Companion-class-randomization action (Options.py's RandomizeClass) --
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
    on it at all, nothing illegal to strip."""
    tag = _COMPANION_TAGS[name]
    npc_const = _COMPANION_NPC_CONST[name]
    class_const = _CLASS_NAME_TO_CONST[class_name]
    is_jedi = class_name in ("guardian", "consular", "sentinel")
    _JEDI_FEATS = (55, 43, 116, 107)  # Jedi Defense, Lightsaber Proficiency, Force Sensitivity, Jedi Sense
    feat_lines = [
        f"    {'KSE_GrantFeatArrayA' if is_jedi else 'KSE_RemoveFeatArrayA'}({feat}, oCompanion);"
        for feat in _JEDI_FEATS
    ]
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
    return [
        f'object oCompanion = GetObjectByTag("{tag}");',
        f"if (IsNPCPartyMember({npc_const}) && GetIsObjectValid(oCompanion))",
        "{",
        f"    KSE_SetCreatureField(oCompanion, KSE_FIELD_CLASS0_TYPE(), {class_const});",
        "    KSE_SetCreatureField(oCompanion, KSE_FIELD_CLASS0_LEVEL(), 1);",
        "    KSE_SetCreatureField(oCompanion, KSE_FIELD_FORCE(), 10);",
        *feat_lines,
        *unequip_lines,
        f'    KSE_Diag(109, "AP|APPLIED|companion_class|name={name}|class={class_name}");',
        "}",
    ]


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
_PLANET_PREFIXES = {
    "tar_m": "taris",
    "danm": "dantooine",
    "kas_m": "kashyyyk",
    "manm": "manaan",
    "korr_m": "korriban",
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
