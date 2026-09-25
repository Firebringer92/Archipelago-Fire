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

# new_companion (Options.py) -- read the same way patch_item_suppression.py's
# _connected_progression_system() reads its own per-seed flag out of
# _slot_data.json (KotorClient.py's write_slot_data_for_patch_scripts(),
# written fresh on every Connect). Safe to read once at module-parse time,
# not per-call, because arm_orchestrator.py invokes this whole script as a
# fresh subprocess for every real delivery -- there is no live-process
# staleness risk the way there would be for a long-running import.
_SLOT_DATA_PATH = os.path.join(SRC_DIR, "_slot_data.json")


def _connected_galactic_shop() -> bool:
    if not os.path.isfile(_SLOT_DATA_PATH):
        return False
    try:
        with open(_SLOT_DATA_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return bool(data.get("galactic_shop", False))
    except Exception:
        return False


_GALACTIC_SHOP_ON = _connected_galactic_shop()

# Permanent-object spawns that must survive every regeneration of an
# area's OnEnter trampoline -- this script rebuilds the target area's
# trampoline from scratch on every real arm delivery, so a permanent
# addition has to live here (and in generate_area_trampolines.py's own
# copy of this same dict), never hand-edited into a generated .nss.
#
# The AP Vendor's own spawn is gated on Options.py's GalacticShop (the
# same option that drives the Void Trade cargo-hold crates via
# patch_galactic_shop.py) -- selecting Galactic Shop gets you both the
# trade crates AND the vendor NPC together, ungated for every purchase
# category (per-item/per-category gating on receiving a specific AP item
# is a real, deliberately deferred follow-up, not built here). Read the
# same way _connected_new_companion() reads its own per-seed flag --
# see that function's own comment for why this is safe to compute once
# at module-parse time rather than per-call.
AREA_PERMANENT_SPAWNS = {
    "ebo_m12aa": [
        'if (!GetIsObjectValid(GetObjectByTag("ap_vendor_npc")))',
        '{',
        '    CreateObject(OBJECT_TYPE_CREATURE, "ap_vendor_npc", Location(Vector(55.5, 36.5, 1.80), 0.0));',
        '}',
    ],
} if _GALACTIC_SHOP_ON else {}


def permanent_spawn_lines_for(base, indent):
    return [f"{indent}{stmt}" for stmt in AREA_PERMANENT_SPAWNS.get(base, [])]


def _connected_new_companion() -> bool:
    if not os.path.isfile(_SLOT_DATA_PATH):
        return False
    try:
        with open(_SLOT_DATA_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return bool(data.get("new_companion", False))
    except Exception:
        return False


# Her real object Tag stays "HK47" and her NPC slot stays NPC_HK_47 either
# way (see _COMPANION_TAGS's own comment) -- only the template resref (what
# .utc gets spawned) changes. p_meetra is the new companion's template,
# built alongside the vanilla-trigger-replacement rebuild (Meetra Surik,
# Jedi Sentinel) -- see DEVELOPMENT_HISTORY.md's "New Companion" section.
NEW_COMPANION_TEMPLATE = "p_meetra"
_USE_NEW_COMPANION = _connected_new_companion()

# For build_trap_block's remove_half_inventory branch, which
# needs to know quest_dependent tags at CODEGEN time to bake an exemption
# check directly into the generated NWScript (see that branch's own
# docstring for why -- avoids ever re-introducing the 512-byte inventory-
# report string limit this project hit live). Same three-location fallback
# as patch_item_suppression.py/patch_additional_enemies.py: old bundled
# location, dev checkout's real Archipelago/worlds/kotor/ source, then the
# current PlayerBundle location (worlds/kotor/ at the bundle root).
GEAR_JSON = os.path.join(REPO_ROOT, "scripts", "gear_items.json")
if not os.path.isfile(GEAR_JSON):
    GEAR_JSON = os.path.join(REPO_ROOT, "Archipelago", "worlds", "kotor", "gear_items.json")
if not os.path.isfile(GEAR_JSON):
    GEAR_JSON = os.path.join(REPO_ROOT, "worlds", "kotor", "gear_items.json")
try:
    with open(GEAR_JSON, encoding="utf-8") as _f:
        _GEAR = json.load(_f)
    QUEST_EXEMPT_TAGS = sorted(tag for tag, v in _GEAR.items() if v.get("quest_dependent"))
except Exception:
    QUEST_EXEMPT_TAGS = []

# Base (auto-granted, feat.2da's <code>_granted=1) feats per class -- confirmed
# via pykotor against the real game data (feat.2da), see
# research/feats/class_feats.json for the raw per-class data. Used by
# build_class_feat_delta_lines() below to compute exactly which feats a
# class-change should strip/grant, instead of the raw KSE_SetCreatureField
# CLASS0_TYPE overwrite touching feats at all (which it never did on its
# own -- confirmed a class write alone leaves the old
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

# Armor Prof ordering, confirmed via feat.2da's prereqfeat1/2 columns:
# Heavy(4) requires Medium(6)+Light(5); Medium(6) requires
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
    build_companion_class_block's own fix note below); base-class grants
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
    # GUARD against a real bug: two Bastilas can result after her
    # grant arm re-fires on a later area transition, since the known
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
        # Marks that Canderous's availability, whatever it is right now,
        # is legitimately AP's doing (this arm only ever runs via a real
        # received item or the vanilla_mode auto-grant, never vanilla
        # story progression on its own) -- see k_ptar_davatk_en.nss's own
        # header for why IsAvailableCreature() alone can't tell a
        # legitimate grant apart from vanilla making him available for
        # free with no AP gating at all.
        'KSE_SetData("ap_canderous_legit", "1");',
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
    # REWRITTEN (second fix -- see git history for the first):
    # the AddMultiClass()+CLASS1_LEVEL patch (matching the companion_class
    # recipe) reliably crashed the game a few seconds after a clean,
    # successful grant -- confirmed across multiple fresh characters/
    # seeds, with two other guarded natives (CheckForce/CheckForcePowers)
    # ruled out as the trigger. Root cause, per this project's own
    # earlier finding: a freshly AddMultiClass'd, still-level-1
    # character's Force-power data isn't allocated until a real level-up
    # runs -- documented THEN as a companion-only crash ("opening a
    # freshly-Jedi'd companion's Force Powers screen crashes the game"),
    # workaround "don't open that screen yet". The PC has no such
    # workaround available -- the PC's own live HUD reads Force Points
    # continuously just by being on screen, unlike a backgrounded
    # companion whose stats are only read on an explicit sheet-open. Same
    # root bug, just unavoidable for the PC instead of dodgeable.
    # Switched to the SAME raw CLASS0_TYPE overwrite + feat-delta pattern
    # already proven crash-free all session for base-class changes (see
    # pc_class_scoundrel below) -- known tradeoff, per this project's own
    # earlier Juhani-reclass work: Force Powers may be sheet-visible
    # without being hotbar-functional this way (unconfirmed for the PC
    # specifically as of this rewrite -- that gap is exactly what this
    # rewrite exists to test).
    #
    # CLASS0_LEVEL forced to 1: a raw
    # type overwrite alone leaves the PC's existing level untouched, which
    # for anything other than jedi_start (fired at level 1 anyway) would
    # let an already-leveled character keep banked feats/skill points from
    # their old class AND immediately receive the new class's base feat
    # kit on top -- effectively double-dipping. Forcing level 1 avoids
    # that, matching the OLD AddMultiClass path's own level-1 reset
    # (though for a different original reason -- that one was about not
    # starving future auto-level-up catch-up, not double-dipped feats).
    13: ("class_guardian", [
        'object oPC = GetFirstPC();',
        'int nOldClass = GetClassByPosition(1, oPC);',
        *build_class_feat_delta_lines("CLASS_TYPE_JEDIGUARDIAN", "oPC"),
        'KSE_SetCreatureField(oPC, KSE_FIELD_CLASS0_TYPE(), CLASS_TYPE_JEDIGUARDIAN);',
        'KSE_SetCreatureField(oPC, KSE_FIELD_CLASS0_LEVEL(), 1);',
        # Trailing "|ok=1" is load-bearing, not decorative: ap_extender.c's
        # confirmation parser finds the arm name by scanning for the NEXT
        # "|" after "AP|APPLIED|", falling back to the rest of the raw log
        # line when none exists -- which then includes the closing '"' of
        # the log line's own msg="..." quoting, so the extracted name
        # becomes "class_guardian\"" and never matches AP_ARM_NAMES. This
        # arm silently never dequeued for exactly that reason from
        # whenever the AddMultiClass->raw-write rewrite dropped this arm's
        # old "|before=X|after=Y" suffix until this fix -- confirmed via
        # kse.log/extender.log cross-reference, see docs/MODE_DEPENDENCIES.md.
        'KSE_Diag(9, "AP|APPLIED|class_guardian|ok=1");',
    ]),
    14: ("class_consular", [
        'object oPC = GetFirstPC();',
        'int nOldClass = GetClassByPosition(1, oPC);',
        *build_class_feat_delta_lines("CLASS_TYPE_JEDICONSULAR", "oPC"),
        'KSE_SetCreatureField(oPC, KSE_FIELD_CLASS0_TYPE(), CLASS_TYPE_JEDICONSULAR);',
        'KSE_SetCreatureField(oPC, KSE_FIELD_CLASS0_LEVEL(), 1);',
        # See class_guardian's own comment above -- same fix, same reason.
        'KSE_Diag(9, "AP|APPLIED|class_consular|ok=1");',
    ]),
    # 16 (companion_jedi_xp) stays RETIRED -- confirmed that
    # GiveXPToCreature has zero effect on a non-PC party member. Not in
    # item_table/KNOWN_ARM_NAMES, permanently unreachable via real AP items.
    #
    # 15/16 (test_setfield/test_combined) RETIRED -- were the
    # throwaway live tests that confirmed KSE_SetCreatureField works on a
    # companion (Zaalbar -> Level 20 Jedi Guardian, 76 Force). The real
    # feature is now the "companion_class" parameterized action (see
    # build_companion_class_block() and the companion_class: token
    # handling below), wired into the real AP flow via Options.py's
    # CompanionClass. Not reusing these IDs -- same reasoning as the other
    # retired-gap comments in this table (12, old-16).
    # 33 (dump_statblock) RETIRED -- Force Powers offset research
    # concluded; the confirmed layout shipped as
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
        # never cleared the pending queue -- confirmed: it silently
        # re-fires on every single area transition indefinitely once
        # received, until caught.
        # REWRITTEN to an absolute KSE_SetCreatureField SET instead of
        # ApplyEffectToObject + EffectAbilityIncrease -- see arms 27-31's own
        # comment (same file) for the full reasoning: the old Effect-based
        # approach stacks a new effect object every single firing, and this
        # arm is specifically designed to fire N times in a row for a "+N"
        # starting preset, which is exactly the repeated-firing pattern that
        # exhausted a real character's stacked-effect budget live. Same "+1
        # per firing" external behavior, just reading the live current value
        # and writing current+1 as an absolute base instead of stacking.
        'object oPC = GetFirstPC();',
        'int nBefore = GetAbilityScore(oPC, ABILITY_CHARISMA);',
        'KSE_SetCreatureField(oPC, KSE_FIELD_SET_CHA_BASE(), nBefore + 1);',
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
        f'string sTemplate = "{NEW_COMPANION_TEMPLATE if _USE_NEW_COMPANION else "p_hk47"}";',
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
    # REWRITTEN: same raw CLASS0_TYPE overwrite rewrite as 13/14
    # above -- see that comment for the full crash history/reasoning.
    26: ("class_sentinel", [
        'object oPC = GetFirstPC();',
        'int nOldClass = GetClassByPosition(1, oPC);',
        *build_class_feat_delta_lines("CLASS_TYPE_JEDISENTINEL", "oPC"),
        'KSE_SetCreatureField(oPC, KSE_FIELD_CLASS0_TYPE(), CLASS_TYPE_JEDISENTINEL);',
        'KSE_SetCreatureField(oPC, KSE_FIELD_CLASS0_LEVEL(), 1);',
        # See class_guardian's own comment (arm 13) -- same fix, same reason:
        # a bare "AP|APPLIED|class_sentinel" with no trailing "|" let the C
        # extender's confirmation parser swallow the closing '"' into the
        # name, so this arm never dequeued and kept re-arming/re-firing on
        # every subsequent area transition, repeatedly resetting the PC's
        # real earned Sentinel level back to 1. Confirmed live 2026-09-16.
        'KSE_Diag(9, "AP|APPLIED|class_sentinel|ok=1");',
    ]),
    # Ability-score increases 27-31 -- same shape as grant_test_ability (18,
    # Charisma) above, covering the remaining 5 abilities for the starting-
    # abilities option. Increment-only (fire N times for a "+N" preset,
    # matching how grant_test_ability already works) -- unlike set_xp/
    # set_credits there's no single "clamp to target" call site, since each
    # firing only knows "add one more," not the eventual total.
    #
    # 4 of 5 REWRITTEN to an absolute KSE_SetCreatureField SET instead of
    # ApplyEffectToObject + EffectAbilityIncrease -- same reasoning as
    # grant_test_ability/the 5 ability traps: the old approach stacks a new
    # effect object every firing, and firing N times in a row for a preset
    # is exactly the repeated pattern that exhausted a real character's
    # stacked-effect budget live (confirmed by the tester's own follow-up:
    # equipping a real vanilla +DEX item afterward produced no change either
    # -- the ability's modifier-effect slot was completely full, not just
    # this project's own traps/grants being blocked). Same "+1 per firing"
    # external behavior, just reading the live current value and writing
    # current+1 as an absolute base instead of stacking. CONSTITUTION (29)
    # deliberately NOT converted -- see offsets.h's KSE_FIELD_SET_STR_BASE-
    # family comment for why CON needs its own Max-HP-interaction decision
    # first, same as the reduce_* traps.
    27: ("ability_strength", [
        'object oPC = GetFirstPC();',
        'int nBefore = GetAbilityScore(oPC, ABILITY_STRENGTH);',
        'KSE_SetCreatureField(oPC, KSE_FIELD_SET_STR_BASE(), nBefore + 1);',
        'int nAfter = GetAbilityScore(oPC, ABILITY_STRENGTH);',
        'KSE_Diag(58, "AP|APPLIED|ability_strength|before=" + IntToString(nBefore) + "|after=" + IntToString(nAfter));',
    ]),
    28: ("ability_dexterity", [
        'object oPC = GetFirstPC();',
        'int nBefore = GetAbilityScore(oPC, ABILITY_DEXTERITY);',
        'KSE_SetCreatureField(oPC, KSE_FIELD_SET_DEX_BASE(), nBefore + 1);',
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
        'KSE_SetCreatureField(oPC, KSE_FIELD_SET_INT_BASE(), nBefore + 1);',
        'int nAfter = GetAbilityScore(oPC, ABILITY_INTELLIGENCE);',
        'KSE_Diag(61, "AP|APPLIED|ability_intelligence|before=" + IntToString(nBefore) + "|after=" + IntToString(nAfter));',
    ]),
    31: ("ability_wisdom", [
        'object oPC = GetFirstPC();',
        'int nBefore = GetAbilityScore(oPC, ABILITY_WISDOM);',
        'KSE_SetCreatureField(oPC, KSE_FIELD_SET_WIS_BASE(), nBefore + 1);',
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
    # StartingClass=random_class, base-class roll only -- a Jedi
    # roll reuses class_guardian/class_consular/class_sentinel above
    # unchanged (those now use the same raw
    # KSE_SetCreatureField CLASS0_TYPE overwrite this base-class roll
    # always used, not AddMultiClass -- see that entry's own comment for
    # the full crash/rewrite history). A base-class roll here uses the
    # same direct-write mechanism CompanionClass already uses for
    # companions (KSE_SetCreatureField) targeting the PC. No Force write
    # (base classes aren't Force-sensitive, and the companion recipe's
    # Force=10 is Jedi-specific); CLASS0_LEVEL write not needed here
    # specifically since this only ever fires via generate_early()
    # precollection, immediately on a freshly created level-1 character,
    # so it's already 1.
    #
    # FIX: the raw field write above NEVER touched feats on its
    # own -- confirmed for the companion equivalent (a
    # class change alone leaves the OLD class's feats in place forever,
    # e.g. keeping Heavy Weapons after rolling into Scout). Now reads the
    # PC's real starting class live (GetClassByPosition, 1-based) BEFORE
    # overwriting it, and uses build_class_feat_delta_lines() to strip
    # exactly the old class's base feats the new class doesn't share, then
    # grant exactly the new class's base feats the old class didn't
    # already have -- see that function's docstring and CLASS_BASE_FEATS
    # above for the base-feat-per-class data this is computed from.
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
    # 45/46 (test_con_boost_effect/test_con_decrease_effect) ALL RETIRED --
    # every research question they existed to answer is now
    # confirmed (results noted in each archived entry) and shipped as real
    # offsets/natives (see offsets.h's KSE_OBJ_CURRENT_HP_OFF/
    # KSE_FIELD_ADD_FORCE_POWER/KSE_FIELD_REMOVE_FORCE_POWER, kse_hook.cpp's
    # KseGetCurrentHP/KseForcePowerOp). Archived verbatim at
    # extender/research_archive/generate_trampoline_batch_temp_arms_2026-09-06.py.txt,
    # same gap convention as 12/15/16/33 above -- IDs never reused.
    # 47 (test_hp_fp_natives) and 48 (test_alignment_shift) RETIRED --
    # both LIVE-CONFIRMED working (see kse.log results
    # archived below). All four new
    # KseGetCurrentHP/KSE_FIELD_CURRENT_HP/ADD_FORCE_POWER/
    # REMOVE_FORCE_POWER capabilities, plus the standard AdjustAlignment()
    # action, are now confirmed shipped and working. Archived verbatim
    # (with the exact confirmed kse.log result lines) at
    # extender/research_archive/test_hp_fp_alignment_arms_2026-09-06.py.txt,
    # same gap-preserving convention as every other retired arm above --
    # IDs never reused.
    # 49 (test_add_100_hp) RETIRED -- confirmed the write
    # succeeds and reads back correctly at the instant of the write
    # (84->184), but current HP appears clamped back to Max HP once it
    # exceeds it (no visible change on the character sheet afterward) --
    # a sane engine invariant, not a bug, and not a real use case anyway.
    # Archived at extender/research_archive/test_hp_fp_alignment_arms_2026-09-06.py.txt.
    # 50 (test_lower_hp) RETIRED -- confirmed: a
    # within-max current-HP write persisted correctly on the character
    # sheet past the instant of the write. Combined with arms 47/49, ALL
    # current-HP native behavior relevant to real features is now
    # confirmed. Archived at extender/research_archive/
    # test_hp_fp_alignment_arms_2026-09-06.py.txt.
    # 51 (test_grant_active_feat) RETIRED -- CONFIRMED NEGATIVE, 2026-09-19,
    # via the Archipelago Vendor's real Train Feat option (not this arm
    # directly, but the same question, same underlying native): granting
    # Flurry (an active/toggle combat feat) to the PC via
    # KSE_GrantFeatArrayA logged as fired (KSE_Diag confirmed, credits
    # deducted) but the feat did NOT appear in the character sheet's
    # trained/usable feats list, and did not work in real combat against
    # a live enemy. Retested after a REAL area transition (not just
    # closing/reopening the menu) -- no change. Same shape confirmed for
    # Force Powers: KSE_SetCreatureField's ADD_FORCE_POWER field granted
    # Resist Energy I (a real, non-cut power, confirmed via spells.2da),
    # logged as fired, but never appeared in the Force Powers menu either,
    # also unaffected by an area transition. See FutureDesign.md's
    # "Archipelago Vendor" section for the full research trail and next
    # steps (a save+reload test, and a promising unused-native lead in
    # offsets.h's KSE_CONTAINER_FEATLIST_OFF/KSE_LIST_FEAT_ADD_RVA family
    # -- reverse-engineered but never wired into the shipping grant path).
    # Passive feats (weapon/armor profs, Implant Level 1, Sneak Attack I,
    # Scoundrel's Luck, Force Focus, Force Immunity: Fear) are NOT
    # affected -- confirmed working via this exact native elsewhere in
    # the project, no hotbar/quickbar slot needed for those.
    # 52 (test_resolve_item) RETIRED -- its later repurposing (proving out
    # the Archipelago Vendor's spawn-a-real-NPC dialogue mechanism) is
    # concluded: the real Vendor is fully built and shipped. See
    # DEVELOPMENT_HISTORY.md's Vendor section for the real feature.
    # 53 (diag_scan_client_stats) RETIRED -- the client-stats offset
    # question it existed to answer is resolved and shipped (the real
    # force-power client-mirror-sync fix). See DEVELOPMENT_HISTORY.md.
    # 54 (test_grant_juhani_power) RETIRED -- confirmed the client-mirror-
    # sync fix works end to end via a granted (not just naturally learned)
    # power. See DEVELOPMENT_HISTORY.md's Vendor section.
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
    # dropped -- confirmed, across separate tests, that SetXP (like
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
    # Direct memory write via KSE_SetCredits (confirmed): resolves pRes fresh via
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


def build_delevel_block(level, xp, force):
    # Reconciler fix for the documented SetXP gap: native
    # SetXP() silently refuses to lower XP below the CURRENT level's
    # banked threshold once vanilla combat/quest XP has carried the
    # player past it. A raw memory write has no
    # such native-function validation
    # to race against, so this writes level and XP directly via
    # KSE_SetCreatureField instead of relying on SetXP for the down
    # direction. See kotor_reconciliation.py for the trigger condition
    # (expected XP maps to a lower level than the player's real current
    # level).
    #
    # force=-1 is the sentinel for "don't touch Force" (non-Jedi PC).
    # Any other value writes it directly too -- the reconciler computes
    # this as a simple proportional scale (currentForce * newLevel /
    # oldLevel), NOT a per-class formula: confirmed empirically
    # that Force-points-per-level does NOT generalize across
    # Jedi classes via a simple relationship to forcedie (Sentinel:
    # +14/level; Consular: +11/level, despite Consular having the BIGGER
    # forcedie) -- chasing an exact per-class table wasn't worth it for
    # a correction that just needs to be reasonable, not pixel-perfect.
    #
    # Note: GetHitDice()/GetXP() read back in the SAME script tick as the
    # write may show STALE (pre-write) values -- this project has
    # already confirmed a same-tick immediate-readback cache quirk for
    # class/level fields elsewhere. The
    # raw write itself still lands correctly regardless; only this
    # diagnostic's "after" numbers might lag by one tick. Not chased
    # further since it's cosmetic (logging only), not functional.
    lines = [
        "object oPC = GetFirstPC();",
        "int nLevelBefore = GetHitDice(oPC);",
        "int nXPBefore = GetXP(oPC);",
        f"KSE_SetCreatureField(oPC, KSE_FIELD_CLASS0_LEVEL(), {level});",
        f"KSE_SetCreatureField(oPC, KSE_FIELD_XP(), {xp});",
    ]
    if force >= 0:
        lines.append(f"KSE_SetCreatureField(oPC, KSE_FIELD_FORCE(), {force});")
    lines.append(
        'KSE_Diag(9, "AP|APPLIED|delevel|levelBefore=" + IntToString(nLevelBefore)'
        ' + "|xpBefore=" + IntToString(nXPBefore)'
        ' + "|levelAfter=" + IntToString(GetHitDice(oPC))'
        ' + "|xpAfter=" + IntToString(GetXP(oPC)));'
    )
    return lines


def build_force_power_block(spell_id):
    # TSL Force Power port pilot -- the grant half of the
    # "three tests" for porting KOTOR 2 powers into K1 (Revitalize, Force
    # Scream, Force Barrier -- see scripts/patch_tsl_powers.py for the
    # spells.2da/TLK/icon/impact-script install half). Reuses the
    # KSE_FIELD_ADD_FORCE_POWER field write already confirmed by the
    # retired research arm 47 (add/remove/remove-again on
    # FORCE_POWER_CURE all passed first try) and shipped for the Remove
    # Half Known Force Powers trap's REMOVE twin. spell_id is a spells.2da
    # row index -- for a ported power that's a row patch_tsl_powers.py
    # appended (133+ on a vanilla table), for a vanilla power any real
    # FORCE_POWER_* row. Guarded with GetHasSpell so a reconnect replay is
    # a harmless no-op rather than a duplicate entry in the power list.
    return [
        "object oPC = GetFirstPC();",
        f"int nHad = GetHasSpell({spell_id}, oPC);",
        "if (!nHad)",
        "{",
        f"    KSE_SetCreatureField(oPC, KSE_FIELD_ADD_FORCE_POWER(), {spell_id});",
        "}",
        f'KSE_Diag(150, "AP|APPLIED|force_power|id={spell_id}|had=" + IntToString(nHad)'
        f' + "|has=" + IntToString(GetHasSpell({spell_id}, oPC)));',
    ]


# See patch_item_suppression.py's PROGRESS_MARKER_RESREF comment for the
# full reasoning -- KSE_SetData's "granted_exempt_" flag below doesn't
# survive a game restart, and possession of the starpad item itself isn't
# a safe restart-persistent signal for these 4 specifically (each has an
# independent vanilla creation point outside this delivery path). Must
# stay in sync with k_sup_galaxymap_progression.nss/
# k_pla_actmap_progression.nss's own bit reads and with
# patch_item_suppression.py's PROGRESS_MARKER_RESREF.
PROGRESS_MARKER_RESREF = "ap_progress_marker"
STARPAD_MARKER_BIT = {
    "tat_starpad": 0,
    "kas_starpad": 1,
    "man_starpad": 2,
    "kor_starpad": 3,
}


def build_give_item_block(resref, count):
    # Generic gear-delivery action -- the resref and count are baked
    # directly into the freshly-regenerated source, same as set_xp/
    # set_credits's value. This is the ONE mechanism for every gear item
    # in gear_items.json: no per-item numbered arm ever needed, so adding
    # or changing gear items later is pure data (edit the JSON), never a
    # DLL rebuild. CreateItemOnObject alone (no AddMultiClass/
    # ShowLevelUpGUI/AddPartyMember) is not a HEAVY_ARMS-category
    # operation -- confirmed safe in large batches, same as
    # skills/abilities.
    #
    # granted_exempt_ marking: CreateItemOnObject fires
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
    # FIXED (real bug): a single
    # CreateItemOnObject(resref, oPC, count) call is capped by the
    # ITEM'S OWN real StackSize field, silently -- confirmed for
    # both Computer Spike (g_i_progspike01, StackSize=1) and Security
    # Spike (BOTH g_i_secspike01 and g_i_secspike02, StackSize=1 --
    # vanilla has no stackable variant of this item at all), meaning a
    # requested count of 10/20 was actually only ever delivering 1. Loop
    # calling CreateItemOnObject with count=1 each time instead -- KOTOR's
    # own inventory naturally merges repeated creates of a genuinely
    # stackable item into one stack (so this is a no-op behavior change
    # for anything that already worked), while a StackSize=1 item just
    # ends up as N separate 1-count inventory entries instead of failing
    # to deliver the rest silently. Universally correct regardless of
    # whether a given resref's real stack limit was ever checked.
    lines = [
        "object oPC = GetFirstPC();",
        f'KSE_SetData("granted_exempt_{resref.lower()}", "1");',
    ]
    for _ in range(count):
        lines.append(f'CreateItemOnObject("{resref}", oPC, 1);')
    bit = STARPAD_MARKER_BIT.get(resref.lower())
    if bit is not None:
        lines.extend([
            f'object oProgMarker = GetItemPossessedBy(oPC, "{PROGRESS_MARKER_RESREF}");',
            "if (!GetIsObjectValid(oProgMarker))",
            "{",
            f'    oProgMarker = CreateItemOnObject("{PROGRESS_MARKER_RESREF}", oPC, 1);',
            "}",
            f"SetLocalBoolean(oProgMarker, {bit}, TRUE);",
        ])
    lines.append(f'KSE_Diag(81, "AP|APPLIED|give_item|resref={resref}|count={count}");')
    return lines


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
    # new_companion=on only (Options.py) -- her real object Tag stays "HK47"
    # regardless of the swap (see NEW_COMPANION_TEMPLATE's own comment
    # below for why: ~450 of 498 game-wide "HK47" string hits are a
    # generic 9-companion tag-exclusion check shared by every companion,
    # safe only as long as this tag doesn't change). Added here so
    # build_companion_class_block()/the Additional Feats block generator
    # (both index this dict by name) don't KeyError the first time either
    # processes her -- __init__.py's COMPANION_CLASS_KEYS is NEVER
    # statically extended with "hk47" (that would wrongly make vanilla
    # HK-47 eligible too), so this entry existing unconditionally is safe:
    # it's only ever looked up for a name that reaches these functions in
    # the first place, which only happens when new_companion is on.
    "hk47": "HK47",
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
# build_companion_class_block (see its docstring's own fix note below).
_COMPANION_NPC_CONST = {
    "bastila": "NPC_BASTILA",
    "canderous": "NPC_CANDEROUS",
    "carth": "NPC_CARTH",
    "jolee": "NPC_JOLEE",
    "juhani": "NPC_JUHANI",
    "mission": "NPC_MISSION",
    "zaalbar": "NPC_ZAALBAR",
    # new_companion=on only -- see _COMPANION_TAGS's comment above for why
    # this is safe to add unconditionally. _COMPANION_NPC_CONST_ALL below
    # already carried this same key/value as an explicit merge addition;
    # this makes it redundant there, not conflicting (same value).
    "hk47": "NPC_HK_47",
}

# All 9 companions including the 2 droids -- _COMPANION_NPC_CONST above is
# deliberately non-droid-scoped (Randomize_class never targets HK-47/T3-M4),
# but the "Remove a Companion" trap has no such restriction (by design:
# "a companion the player has access to", no exclusion), so it needs
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

    The "found" check must not be plain
    GetIsObjectValid(oCompanion) on a GetObjectByTag() lookup. Confirmed
    (Carth) that this is not sufficient -- a Carth-
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

    Recipe (level 1 + 10 Force) is the exact one confirmed
    on Zaalbar -> Level 20 Jedi Guardian, 76 Force -- KOTOR's own
    companion auto-level-sync catches them up to the party's real level
    over subsequent play, same as it did there.

    Also grants/removes the feats a real Jedi
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
    class switch should ever touch (see research/feats/class_feats.json
    for the full per-class table). Without this fix a companion switched
    AWAY from a Jedi class (Jolee -> Soldier)
    could still wield a lightsaber, because the class write never touches
    the feat list. Deliberately just these four (not the tiered
    Advanced/Master Jedi Defense, Weapon Focus/Specialization: Lightsaber,
    or the level-6/12 tiers like Knight/Master Sense) -- matches the exact
    scope defined for this feature, not everything a real multi-level Jedi
    progression would eventually grant. Uses K1SE's own proven
    KSE_GrantFeatArrayA/KSE_RemoveFeatArrayA (routines 618/634) -- no new
    native needed.
    Removal of a feat the creature doesn't hold is a safe no-op
    (drain-and-rebuild finds nothing to remove); granting a feat already
    held is likewise not expected to duplicate (K1SE's own adder is the
    same one real level-up uses).

    On the REMOVAL path (switching AWAY from Jedi)
    also force-unequips a lightsaber from either weapon slot, AND a Jedi
    robe from the body slot. Confirmed: removing feat 43 (Lightsaber
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
    since corrected) -- confirmed via baseitems.2da that all three
    tiers (BASE_ITEM_JEDI_ROBE/_JEDI_KNIGHT_ROBE/_JEDI_MASTER_ROBE, rows
    35/36/37) carry reqfeat0=55 (Jedi Defense), the exact feat this same
    removal path already strips -- so robes have the identical
    can't-re-equip-but-stays-on-if-already-worn gap as lightsabers, now
    checked in INVENTORY_SLOT_BODY the same way. Real armor (non-robe) is
    deliberately left alone -- non-Jedi classes have no equip restriction
    on it at all, nothing illegal to strip.

    FIX (promoted from temporary arm 39's proof-of-concept):
    granting a companion a JEDI class they didn't already have
    used to go through the same raw KSE_SetCreatureField(CLASS0_TYPE)
    overwrite as every other direction -- confirmed to leave newly-
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
    unchanged -- confirmed NOT broken for Jedi-to-base (a clean re-test
    without a contaminated arm queue) and never shown broken for the Jedi-to-
    different-Jedi case either, so left on the proven path rather than
    risking an untested AddMultiClass-onto-an-already-Jedi-Class0
    interaction. Feat grants/removals and the lightsaber/robe equip-swap
    run unconditionally either way -- redundant-but-harmless if
    AddMultiClass's own housekeeping already granted them (K1SE's adder is
    the same one real level-up uses, confirmed safe to re-fire).

    FIX: the base-class-target branch used to ONLY strip the 4
    universal Jedi feats, unconditionally, regardless of what the
    companion's class actually was -- confirmed a real gap via
    CLASS_BASE_FEATS' base-feat-per-class data: a base-to-base switch
    (e.g. Soldier -> Scout) never granted/stripped anything at all (keeps
    Power Attack/Heavy Weapons forever, never gains Flurry/Rapid Shot), and
    a Jedi-to-base switch never stripped that Jedi's own unique power feat
    (Force Jump/Focus/Immunity Fear). Now reads the companion's real
    CURRENT class live (GetClassByPosition, 1-based) before either branch
    touches anything, and the base-class-target branch uses the same
    build_class_feat_delta_lines() helper the PC's own pc_class_soldier/
    scout/scoundrel arms use -- strips exactly the old class's base feats
    the new class doesn't share, grants exactly the new class's base feats
    the old class didn't already have. Also added each Jedi
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
    the full delta treatment, matching the PC's own arms; the
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
        # FIX, found testing Canderous: granting these
        # immediately after AddMultiClass() in the same script pass lost
        # 2 of 4 feats (Jedi Sense/Force Sensitivity gone; Lightsaber
        # Proficiency/Jedi Defense survived) -- confirmed, reproduced.
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
        # CONFIRMED FIXED: Mission, a genuinely clean
        # base-to-Jedi test subject (fresh save, never touched before this
        # test), got all 4 feats via this delayed path -- Jedi Sense and
        # Force Sensitivity both landed this time. The old
        # (non-AddMultiClass) removal path below has no such race, so it
        # stays immediate/unchanged. The class-specific unique power feat
        # rides the same delayed grant, untested on its
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
        # see this function's docstring's own entry on this fix above. An
        # already-Jedi companion rolling a DIFFERENT Jedi class under
        # randomize_all stays on the old, unmodified path (never shown
        # broken, and AddMultiClass onto an already-Jedi Class0 is
        # untested).
        #
        # ADDENDUM, found testing Mission: the original
        # recipe only patched Class1's level to 1 and left Class0's
        # EXISTING level untouched (confirmed: Scoundrel level 3 +
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
    """AdditionalFeats action (Options.py) -- grants exactly
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
    or an overlap with a class-change action's own grants). The pool is
    KotorClient.py's ADDITIONAL_FEATS_POOL (derived from feat.2da).

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

    # FIX #1: the confirmation must not just echo back feat_ids
    # verbatim ("feats=28,29,31"), since that only proves the script ran to
    # completion -- NOT that each KSE_GrantFeatArrayA write actually took.
    # A real failure mode: Mission's additional_feats grant reported
    # feats=28,29,31 as APPLIED, but she came out with 28 and 31 while 29
    # (Power Blast) silently never landed. Now reports each feat's
    # "before" state (GetHasFeat right before the attempt).
    #
    # FIX #2, root cause found via this same diagnostic on a
    # SECOND attempt: with the fix #1 diagnostic in place, a retry showed
    # ALL 3 requested feats at before=0/after=0 -- a complete, 100% write
    # failure for a companion target. This is the EXACT symptom already
    # solved once in build_companion_class_block's own fix note above:
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
    # FIX #3: fix #2's DelayCommand wrap didn't help either --
    # confirmed on Bastila, who NEVER goes through AddMultiClass at
    # all under jedi_companion mode (trivially class-finalized, no roll
    # ever happens for her) -- her grant still failed the same way. That
    # rules out the AddMultiClass-settling race entirely; whatever's
    # actually wrong is unrelated to timing. The one remaining concrete
    # difference from build_companion_class_block's PROVEN-working Jedi-
    # feat grant (Canderous, confirmed, all 4 feats landed) is that
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
    """Traps action (Options.py's Traps) -- ONE
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

    Every branch below reuses an ALREADY-PROVEN native:
    KSE_SetCredits (credits), KSE_SetCreatureField's CLASS0_LEVEL/
    CLASS1_LEVEL fields + SetXP (level), KSE_RemoveFeatArrayA (feats),
    KSE_SetCreatureField's REMOVE_FORCE_POWER field (force powers),
    KSE_FIELD_HALVE_MAX_HP_VIA_CON (Max HP via Constitution, entirely
    self-contained -- reads true CON and both class slots live, no
    params needed) and KSE_FIELD_HALVE_*_BASE (the 5 standalone ability
    traps, same self-contained shape), RemoveAvailableNPC (companion
    removal, confirmed to eject an ACTIVE party member, not just mark
    unavailable), and the existing GetFirstItemInInventory/
    GetNextItemInInventory/DestroyObject walk (inventory removal, same
    pattern as ap_remove_test_item.nss).

    "remove_credits" is deliberately NOT one of the cases below --
    KotorClient.py calls the ALREADY-EXISTING set_credits action
    directly for that one (see build_set_credits_block), since it's
    already an exact byte-for-byte match for what this trap needs.
    """
    lines = ["object oPC = GetFirstPC();"]

    if trap_type == "reduce_skill":
        # Retired cut_level's replacement -- cut_level's
        # SetXP(oPC, new_xp) call silently no-ops once the character has
        # already banked XP past the current level's threshold (level
        # field drops, XP doesn't), leaving level and XP
        # inconsistent with no reliable fix. EffectSkillDecrease is a
        # plain vanilla effect with no such threshold -- same pattern
        # already proven for the 5 ability traps below.
        #
        # Decrease amount computed LIVE here from a fresh GetSkillRank()
        # read, NOT client-side from KotorClient.py's reconciler.current_
        # skills (a cache from the last SKILLREPORT poll) -- same real bug
        # class confirmed live for the 5 ability traps below (see that
        # block's own comment): a stale cached rank would halve the wrong
        # (stale) number instead of the true live one, and would compound
        # incorrectly if this trap type is ever received more than once.
        # params_str is now just "<skill_key>" -- Python still picks WHICH
        # skill randomly (NWScript would need to query all 8 skills live to
        # replicate that eligibility list, not worth it here), but the
        # decrease AMOUNT for whichever skill got chosen is computed here.
        skill_key = params_str
        skill_const = {
            "computeruse": "SKILL_COMPUTER_USE", "demolitions": "SKILL_DEMOLITIONS",
            "stealth": "SKILL_STEALTH", "awareness": "SKILL_AWARENESS",
            "persuade": "SKILL_PERSUADE", "repair": "SKILL_REPAIR",
            "security": "SKILL_SECURITY", "treatinjury": "SKILL_TREAT_INJURY",
        }[skill_key]
        # REWRITTEN to KSE_AdjustCreatureSkills (routine 684) instead of
        # ApplyEffectToObject + EffectSkillDecrease -- same reasoning as the
        # 5 ability traps above: EffectSkillDecrease stacks a new effect
        # object every call with no ceiling, while KSE_AdjustCreatureSkills
        # writes directly to the real base skill-rank byte (already proven
        # live -- the Train Skill vendor feature above already uses it the
        # same way, just with a positive amount). Still a relative amount,
        # not an absolute set like the ability fields, but that's fine here:
        # the write itself doesn't stack, so there's nothing to accumulate
        # and no ceiling to hit regardless of delta-vs-absolute shape.
        lines += [
            f"int nBefore = GetSkillRank({skill_const}, oPC);",
            "if (nBefore <= 0)",
            "{",
            f'    KSE_Diag(134, "AP|NOOP|trap|type=reduce_skill|skill={skill_key}|current=" + IntToString(nBefore));',
            "}",
            "else",
            "{",
            "    int nDecrease = nBefore - (nBefore / 2);",
            f"    KSE_AdjustCreatureSkills(oPC, {skill_const}, -nDecrease);",
            f"    int nAfter = GetSkillRank({skill_const}, oPC);",
            f'    KSE_Diag(134, "AP|APPLIED|trap|type=reduce_skill|skill={skill_key}|before=" + IntToString(nBefore) + "|after=" + IntToString(nAfter));',
            "}",
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
        # KSE_FIELD_REMOVE_FORCE_POWER() field write confirmed in
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
        # No params needed -- KSE_FIELD_HALVE_MAX_HP_VIA_CON computes the
        # CON decrease that lands Max HP closest to half entirely
        # natively (fixed hit-die term can't be reduced via CON alone,
        # see Options.py's Traps docstring) and applies it via the same
        # real engine setter INCREMENT_CON_BASE uses (setHP=TRUE), as a
        # real base-score rewrite rather than a stacking effect object
        # with no ceiling on repeated triggers.
        lines += [
            "int nMaxBefore = GetMaxHitPoints(oPC);",
            "KSE_SetCreatureField(oPC, KSE_FIELD_HALVE_MAX_HP_VIA_CON(), 0);",
            "int nMaxAfter = GetMaxHitPoints(oPC);",
            f'KSE_Diag(134, "AP|APPLIED|trap|type=cut_max_hp|maxbefore=" + IntToString(nMaxBefore) + "|maxafter=" + IntToString(nMaxAfter));',
        ]

    elif trap_type == "remove_companion":
        # params_str = "<companion_key>" -- one of the 9 real keys (see
        # _COMPANION_NPC_CONST_ALL), a random currently-recruited one
        # chosen client-side (KotorClient.py's own _recruited_companions
        # tracking). RemoveAvailableNPC confirmed (see
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
        # REDESIGNED -- params_str is now unused/empty. This
        # used to take an already-chosen tag list computed client-side
        # from kotor_reconciliation.py's current_inventory, which was fed
        # by ap_poll_shared.nss's CheckInventory() -- a giant concatenated
        # string across the whole backpack that silently truncates past
        # NWScript's ~512-byte string limit for a large enough inventory
        # (root-caused via the Bounty Card count bug).
        # Rather than keep a Python-side selection fed by an unreliable
        # report, this now does the ENTIRE thing natively in one shot:
        # backpack walk, quest_dependent exemption (QUEST_EXEMPT_TAGS is
        # static gear_items.json data, known at codegen time -- baked in
        # directly, same pattern every other suppression whitelist in this
        # project already uses), and random selection, all in NWScript, so
        # no giant string is EVER built for this trap. Object references
        # are stored via SetLocalObject on oPC during the first pass (not
        # text), so there's no size limit regardless of backpack size.
        #
        # Random-without-replacement is a standard single-pass-per-walk
        # reservoir selection: walking the nEligible candidates in order,
        # each is removed with probability (remaining still needed) /
        # (remaining unvisited) -- exactly nEligible/2 removed overall, no
        # shuffle/array needed. Two full inventory walks (count, then
        # decide-and-destroy) rather than one, since this engine's
        # nwscript.nss has NO SetLocalObject/GetLocalObject/DeleteLocalObject
        # at all (confirmed via a real compile error -- only the Boolean/
        # Number local variants exist here), so there's no way to remember
        # which specific item objects were eligible between a count pass and
        # an act pass. Recomputing eligibility fresh in the second walk
        # (a pure function of GetTag()) costs nothing extra and needs no
        # storage. Second walk fetches GetNextItemInInventory() BEFORE
        # possibly destroying the current item -- GetNextItemInInventory
        # cursors off oPC's inventory itself, not the current item, so
        # this is safe, but destroying first and then asking oPC to
        # advance from a now-destroyed reference is exactly the "mutating
        # the list mid-walk" hazard the original per-tag walk above was
        # already written to avoid.
        exempt_conditions = " ||\n            ".join(f'sTag == "{r}"' for r in QUEST_EXEMPT_TAGS)
        is_exempt_expr = f"({exempt_conditions})" if exempt_conditions else "FALSE"
        lines += [
            "string sTag;",
            "int nEligible = 0;",
            "object oCountItem = GetFirstItemInInventory(oPC);",
            "while (GetIsObjectValid(oCountItem))",
            "{",
            "    sTag = GetTag(oCountItem);",
            f"    if (!{is_exempt_expr})",
            "    {",
            "        nEligible = nEligible + 1;",
            "    }",
            "    oCountItem = GetNextItemInInventory(oPC);",
            "}",
            "",
            "int nToRemove = nEligible / 2;",
            "int nRemaining = nEligible;",
            "int nRemovedSoFar = 0;",
            "int nRemoved = 0;",
            "object oCurrent = GetFirstItemInInventory(oPC);",
            "while (GetIsObjectValid(oCurrent))",
            "{",
            "    object oNext = GetNextItemInInventory(oPC);",
            "    sTag = GetTag(oCurrent);",
            f"    if (!{is_exempt_expr})",
            "    {",
            "        if (Random(nRemaining) < nToRemove - nRemovedSoFar)",
            "        {",
            "            DestroyObject(oCurrent);",
            "            nRemovedSoFar = nRemovedSoFar + 1;",
            "            nRemoved = nRemoved + 1;",
            "        }",
            "        nRemaining = nRemaining - 1;",
            "    }",
            "    oCurrent = oNext;",
            "}",
        ]
        lines.append('KSE_Diag(134, "AP|APPLIED|trap|type=remove_half_inventory|removed=" + IntToString(nRemoved));')

    elif trap_type in ("reduce_str", "reduce_dex", "reduce_int", "reduce_wis", "reduce_cha"):
        # Uses KSE_FIELD_HALVE_*_BASE: reads the TRUE base score and writes
        # base - (base/2) entirely natively, via the real engine setter --
        # not ApplyEffectToObject + EffectAbilityDecrease (stacks a new
        # effect object every call, no ceiling on how many accumulate), and
        # not NWScript's own GetAbilityScore() + KSE_FIELD_SET_*_BASE (that
        # reads the EFFECTIVE score -- base plus any equipped item bonus --
        # so it could compute "half" from an inflated number and bake the
        # item's bonus into the new permanent base). See offsets.h's
        # KSE_FIELD_HALVE_STR_BASE comment. CON isn't included here --
        # "Cut Max Health in Half" needs a specific decrease amount, not a
        # flat halving, and uses KSE_FIELD_INCREMENT_CON_BASE instead.
        ability_const = {
            "reduce_str": "ABILITY_STRENGTH", "reduce_dex": "ABILITY_DEXTERITY",
            "reduce_int": "ABILITY_INTELLIGENCE", "reduce_wis": "ABILITY_WISDOM",
            "reduce_cha": "ABILITY_CHARISMA",
        }[trap_type]
        field_const = {
            "reduce_str": "KSE_FIELD_HALVE_STR_BASE", "reduce_dex": "KSE_FIELD_HALVE_DEX_BASE",
            "reduce_int": "KSE_FIELD_HALVE_INT_BASE", "reduce_wis": "KSE_FIELD_HALVE_WIS_BASE",
            "reduce_cha": "KSE_FIELD_HALVE_CHA_BASE",
        }[trap_type]
        lines += [
            f"int nBefore = GetAbilityScore(oPC, {ability_const});",
            f"KSE_SetCreatureField(oPC, {field_const}(), 0);",
            f"int nAfter = GetAbilityScore(oPC, {ability_const});",
            "if (nAfter == nBefore)",
            "{",
            f'    KSE_Diag(134, "AP|NOOP|trap|type={trap_type}|current=" + IntToString(nBefore));',
            "}",
            "else",
            "{",
            f'    KSE_Diag(134, "AP|APPLIED|trap|type={trap_type}|before=" + IntToString(nBefore) + "|after=" + IntToString(nAfter));',
            "}",
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

    FINAL DESIGN (kept as the documented outcome of a long debugging
    chain, for the next person who touches this): each text gets its own
    directly-delayed native call --
    `DelayCommand(fDelay, FloatingTextStringOnCreature(text, oPC, FALSE))`
    -- staggered by 1.5s per text, NO custom wrapper function involved.
    CONFIRMED WORKING for a single notification: shows up in KOTOR's
    feedback message log. Known, accepted limitation: if 2+ notifications
    land in the same batch, only the FIRST one displays -- multiple
    INDEPENDENT DelayCommand calls issued from the same originating
    script execution only honor the first one, confirmed. Not
    chased further; single-notification is the common case (usually one
    check or one item between transitions) and this project's philosophy
    is to document a narrow, confirmed limitation rather than keep
    engineering around it.

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
# FIX: "tat_m": "tatooine" was missing entirely -- see the
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
            elif action == "delevel":
                level, xp, force = item["level"], item["xp"], item["force"]
                label, body = "delevel", build_delevel_block(level, xp, force)
                lines.append(f"        // delevel={level}:{xp}:{force}")
            elif action == "force_power":
                spell_id = item["spell_id"]
                label, body = "force_power", build_force_power_block(spell_id)
                lines.append(f"        // force_power={spell_id}")
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
        elif a.startswith("delevel:"):
            # delevel:<level>:<xp>:<force> -- see build_delevel_block()'s
            # own docstring for the full reconciler SetXP-gap fix design.
            _, level_s, xp_s, force_s = a.split(":", 3)
            batch_items.append({"action": "delevel", "level": int(level_s), "xp": int(xp_s), "force": int(force_s)})
        elif a.startswith("force_power:"):
            # force_power:<spells.2da row id> -- see build_force_power_block().
            batch_items.append({"action": "force_power", "spell_id": int(a.split(":", 1)[1])})
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
    # per planet (not a single universal list). Empty
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
            lines.extend(permanent_spawn_lines_for(base, "        "))
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
                lines.extend(permanent_spawn_lines_for(base, "            "))
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
        # Real bug: `ok = os.path.exists(ncs_path)`
        # alone stays TRUE even when THIS compile fails, because a stale
        # .ncs from an earlier, unrelated successful build is already
        # sitting at that path -- nwnnsscomp.exe just leaves it untouched
        # on a compile error rather than deleting it. Confirmed: a
        # NotifyChain forward-reference error ("Undeclared identifier")
        # can silently redeploy a stale single-item .ncs on every single
        # multi-notify attempt, with zero visible indication anywhere.
        # Two independent checks now, both required: the file's own mtime
        # must have actually advanced (proves nwnnsscomp really wrote
        # something this call, not just that a file exists from before),
        # AND its own stdout must not contain the compiler's real
        # failure markers.
        mtime_before = os.path.getmtime(ncs_path) if os.path.exists(ncs_path) else None
        # timeout=30 (hang-safeguard): a real compile "takes well
        # under a second in practice" (see ap_extender.c's own comment on
        # the caller of this whole chain), so 30s is generous, not tight.
        # Real risk this closes: this subprocess.run() previously had NO
        # timeout at all, and this call sits at the bottom of a 3-layer
        # chain (extender's C code -> arm_orchestrator.py -> this file ->
        # nwnnsscomp.exe) where NONE of the 3 subprocess calls had one --
        # if nwnnsscomp.exe ever hung (a plausible, ordinary trigger:
        # antivirus real-time scanning intercepting a frequently-spawned,
        # less-common .exe, not just a dev-editing collision), the C
        # extender's log-tail thread would block forever inside a
        # ReadFile with no timeout of its own, silently freezing all
        # future event relay for the rest of the game session with zero
        # error anywhere -- exactly the "extender silently died" symptom.
        # Bounding this call is enough to
        # fix that from the Python side alone: the C code's ReadFile only
        # blocks until the whole child process tree exits and closes its
        # output handle, so a bounded exit here anywhere in the chain is
        # sufficient, no DLL rebuild needed.
        try:
            result = subprocess.run(
                [NWNNSSCOMP, "-c", nss_path, "-o", ncs_path],
                capture_output=True, text=True, cwd=SRC_DIR, timeout=30,
            )
            compiled_fresh = os.path.exists(ncs_path) and (
                mtime_before is None or os.path.getmtime(ncs_path) != mtime_before
            )
            compile_error = "Compilation aborted" in result.stdout or "Error:" in result.stdout
            ok = compiled_fresh and not compile_error
            out, err = result.stdout, result.stderr
        except subprocess.TimeoutExpired as e:
            # subprocess.run() already killed the hung process before
            # raising this (that's what unblocks the C extender's
            # ReadFile) -- e.stdout/e.stderr hold whatever was captured
            # before the kill (may be None, since capture_output+timeout
            # doesn't always populate these on every Python version).
            print(f"  COMPILE TIMED OUT after 30s: {onenter} -- nwnnsscomp.exe did not exit "
                  "(hung child process, killed) -- treating as a compile failure")
            ok = False
            out, err = (e.stdout or ""), (e.stderr or "")
        if ok:
            dest = os.path.join(OVERRIDE_DIR, f"{onenter}.ncs")
            with open(ncs_path, "rb") as fsrc, open(dest, "wb") as fdst:
                fdst.write(fsrc.read())
        print(f"{onenter} (covers {base_list_comment}): {'OK' if ok else 'FAILED'}")
        if not ok:
            print(out, err)


if __name__ == "__main__":
    main()
