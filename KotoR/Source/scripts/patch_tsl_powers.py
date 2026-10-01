r"""
TSL (KOTOR 2) Force Power port -- installer for the three ported power
lines. A standing feature of this build, not an AP-item pilot:
ap_extender.c's ap_bootstrap_tsl_force_powers() grants all 9 rows
automatically every game launch via the same --queue-force-power= path
the /ap_apply admin command uses -- no AP item, seed action, or
Options.py toggle involved. Still
dev/tester-run by hand (this script installs the data once per K1
install; it is not invoked by KotorClient.py). These three lines were
picked from the ~28 genuinely shipped K2 powers as the ones with a plain
level gate (no TSL prestige class or TSL-only companion), ordinary
Effect*-based mechanics (no engine-hardcoded behavior like Force
Camouflage), and -- for Revitalize -- an existing K1 community-mod
precedent proving the mechanic works in this engine.

The three lines (9 spells.2da rows), straight from K2's real data:
  Revitalize / Improved / Master   (K2 rows 173-175, Light, 50 FP)
  Force Scream / Improved / Master (K2 rows 159-161, Dark,  25 FP)
  Force Barrier / Improved / Master (K2 rows 135-137, Light, 20 FP)

What this does to the K1 install (everything backed up / reversible with
--restore):
  1. spells.2da -> Override/spells.2da with 9 new rows appended (based on
     the existing Override copy if there is one, else the BIF original).
     Every K1 column is copied from the K2 row (K1's columns are a strict
     subset of K2's -- the prestige-class and formmask columns are the
     only K2 extras, dropped). Remapped: name/spelldesc (new TLK strrefs),
     prerequisites (K2 row ids -> the new K1 row ids), impactscript (a
     generated per-row script, see below), the class level-gate columns
     (clamped to 20, K1's real cap -- Master Revitalize is 21 in K2), and
     forcehostile/forcefriendly/forcepassive (K2's own numeric AI-priority
     values are blanked -- those index K2's own AI tables, not K1's -- but
     exactly one of the three is then set to a real value matching the
     closest K1 analog's own column choice; see AI_COLUMN_BY_FAMILY's own
     comment for why this matters for menu visibility, not just AI).
  2. dialog.tlk -> 18 new strings appended (K2's real name/description
     text, verbatim apart from "Level 21" -> "Level 20"). Backed up once
     to extender/backup/dialog.tlk. K1 has no per-module TLK override, so
     the root file is the only place these can live.
  3. Icons -> Override/ip_*.tpc, the 9 real K2 hotbar icons copied
     byte-for-byte out of K2's TexturePacks/swpc_tex_gui.erf (same TPC
     format K1 uses, confirmed by K1's own ip_heal living in the same
     kind of ERF).
  4. Impact script -> Override/ap_fp_powers.ncs, ONE generated NWScript
     shared by all 9 rows (dispatched on GetSpellId(), same pattern
     several of BioWare's own shared impact scripts use) -- combined from
     the original 9-file pilot once these became a standing feature,
     since 9 near-identical Override files had no purpose once nothing
     seed-specific about them remained. Compiled here with nwnnsscomp.
     This is a K1 REWRITE of the real K2 logic (read directly from K2's
     shipped k_inc_force.nss source -- it turns out KOTOR 2 ships the
     .nss, so no disassembly was needed after all), not an include of K2
     code: K2's helpers (Sp_RemoveRelatedPowers, Sp_CalcDamage,
     Form/Stance scaling, K2-only VFX ids 9005-9008, effecticon rows)
     don't exist in K1, so the script is self-contained against K1's own
     nwscript.nss. Behavior kept:
       Barrier  : DR 4/8/15 vs bludgeoning+piercing+slashing, 30/45/60s,
                  replaces any lower/equal tier already on the caster.
       Scream   : 3/5/7 d6 sonic + -2/-4/-6 to all six abilities for 30s
                  on a failed Will save (half damage, no debuff on a
                  save); cone 20m for I/II, 12m sphere around the caster
                  for Master; enemies only, droids immune (K2 rule).
       Revitalize: I revives the CLOSEST fallen non-droid party member
                  (+10 HP); Improved/Master revive ALL (+25/+50 HP) --
                  K2's shipped fixed amounts, not its commented-out
                  percentages.
     Dropped: K2's Force Chain feat sharing (no such feat in K1), and
     SetEffectIcon (K2 effecticon.2da rows, cosmetic).

Granting: ap_extender.c's ap_bootstrap_tsl_force_powers() grants all 9 rows
automatically, once per game launch, with no seed/item/admin action needed
-- this is now a standing feature of the build, not an AP pilot. The powers
also still auto-learn at K2's level gates for any Jedi (the class columns
are exactly what the engine's own level-up reads to decide what a Jedi
learns), and can still be granted on demand with the client's admin
command (useful for re-testing without waiting for the extender's next
launch):
    /ap_apply force_power:<row id>
This script prints each power's row id, and writes them to
extender/backup/tsl_powers_manifest.json -- ap_extender.c's
AP_TSL_FORCE_POWER_ROWS array must be kept in sync with those ids if this
script is ever re-run against a different existing spells.2da state.

Re-running is safe (rows/strrefs are reused from the manifest, not
appended twice). KOTOR caches spells.2da per PROCESS -- fully exit the
game before expecting a change to show.

Usage:
  python patch_tsl_powers.py                                  -- apply
  python patch_tsl_powers.py --restore                        -- undo everything
  python patch_tsl_powers.py --game-dir "D:\...\swkotor" --k2-dir "D:\...\Knights of the Old Republic II"
"""
import json
import os
import shutil
import subprocess
import sys

from pykotor.extract.installation import Installation, SearchLocation
from pykotor.resource.formats.erf import read_erf
from pykotor.resource.formats.tlk import read_tlk, write_tlk
from pykotor.resource.formats.twoda import read_2da, write_2da
from pykotor.resource.type import ResourceType

from nwnnsscomp_path import resolve_nwnnsscomp  # noqa: E402 -- see that module's docstring

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(REPO_ROOT, "extender", "scripts_src")
BACKUP_DIR = os.path.join(REPO_ROOT, "extender", "backup")
MANIFEST_PATH = os.path.join(BACKUP_DIR, "tsl_powers_manifest.json")
DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
DEFAULT_K2_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\Knights of the Old Republic II"
NWNNSSCOMP = resolve_nwnnsscomp()
K1_LEVEL_CAP = 20

# (K2 label, K2 row, K1 script resref, family, tier). Rows verified
# against the real K2 spells.2da; the label is what's actually matched at
# apply time (row numbers are only a sanity check).
POWERS = [
    # Revitalize excluded: its real spells.2da level-gate columns
    # (guardian/consular/sentinel 9/15/20) make it a naturally-selectable
    # choice on KOTOR's own level-up screen for any Jedi reaching those
    # levels, independent of whether the Vendor exposes it. Rows 133-135
    # are left as harmless orphans in Override/spells.2da (see the
    # manifest-diff cleanup below, which blanks an orphaned row's name so
    # it can't be offered) -- same "leave gaps, don't renumber" convention
    # this project uses elsewhere. Re-enabling is a 3-line uncomment.
    # ("FORCE_POWER_REVITALIZE",            173, "ap_fp_revit1",  "revitalize", 1),
    # ("FORCE_POWER_IMPROVED_REVITALIZE",   174, "ap_fp_revit2",  "revitalize", 2),
    # ("FORCE_POWER_MASTER_REVITALIZE",     175, "ap_fp_revit3",  "revitalize", 3),
    ("FORCE_POWER_FORCE_SCREAM",          159, "ap_fp_scream1", "scream",     1),
    ("FORCE_POWER_IMPROVED_FORCE_SCREAM", 160, "ap_fp_scream2", "scream",     2),
    ("FORCE_POWER_MASTER_FORCE_SCREAM",   161, "ap_fp_scream3", "scream",     3),
    # Force Barrier excluded: its character-sheet "next tier" navigation
    # lands on Force Shield's own screen instead of Improved Force
    # Barrier. Not a category collision (see CATEGORY_OVERRIDE_BY_FAMILY's
    # own comment for what was ruled out) -- root cause still open. Rows
    # 139-141 are left as harmless orphans in Override/spells.2da, same
    # convention as Revitalize above. Re-enabling is a 3-line uncomment
    # once the real cause is found.
    # ("FORCE_POWER_FORCE_BARRIER",         135, "ap_fp_barr1",   "barrier",    1),
    # ("FORCE_POWER_IMPROVED_FORCE_BARRIER", 136, "ap_fp_barr2",  "barrier",    2),
    # ("FORCE_POWER_MASTER_FORCE_BARRIER",  137, "ap_fp_barr3",   "barrier",    3),
    # Single-tier caps on two lines K1 already has (Resist Energy I/II,
    # Cure/Heal). Verified column-clean against their real K1
    # predecessors -- no category/level-gate/AI-column collision the way
    # Barrier had (see CATEGORY_OVERRIDE_BY_FAMILY's comment).
    ("FORCE_POWER_MASTER_ENERGY_RESISTANCE", 133, "ap_fp_enres3", "energy_resistance", 1),
    ("FORCE_POWER_MASTER_HEAL",               134, "ap_fp_masheal", "master_heal",     1),
]
LEVEL_GATE_COLUMNS = ("guardian", "consular", "sentinel", "inate")
AI_COLUMNS = ("forcehostile", "forcefriendly", "forcepassive")
# FOUND 2026-09-20 -- this was the actual reason none of the 9 ported rows
# ever showed up in the in-game Force Powers menu (confirmed known via a
# real granted-without-error test; see ap_extender.c's disabled
# ap_bootstrap_tsl_force_powers() for the original, never-root-caused
# report). Scanned every genuine player-selectable Jedi Force Power in
# vanilla K1's own spells.2da: ALL of them have EXACTLY ONE of forcehostile/
# forcefriendly/forcepassive set to a real number and the other two blank
# -- never all three blank at once, which is what blanking every AI_COLUMNS
# entry (below) produced. The exact numeric value looks like an AI
# priority weight (irrelevant to menu visibility), but which ONE column is
# non-blank appears to be how the game categorizes/displays the power at
# all. Mapped by family to the closest real K1 analog's own column choice:
# revitalize (heal, ally-targeted) matches FORCE_POWER_CURE/HEAL's
# forcefriendly='0'; barrier (personal defensive buff) matches FORCE_POWER_
# FORCE_SHIELD/FORCE_AURA's forcefriendly='1' (passive is used by a
# different category -- mind-affecting utility powers like Affect Mind/
# Dominate -- not defensive buffs); scream (attack) matches other hostile
# attack powers' forcehostile column, graduated by tier the same way
# vanilla's own tiered attack powers scale (e.g. Affliction=3, Shock=5,
# Death Field=7).
AI_COLUMN_BY_FAMILY = {
    "revitalize": ("forcefriendly", {1: "0", 2: "0", 3: "0"}),
    "barrier":    ("forcefriendly", {1: "1", 2: "1", 3: "1"}),
    "scream":     ("forcehostile",  {1: "3", 2: "5", 3: "7"}),
    # Matches FORCE_POWER_RESIST_ENERGY_1/2's own real forcefriendly value.
    "energy_resistance": ("forcefriendly", {1: "5"}),
    # Matches FORCE_POWER_CURE/HEAL's own real forcefriendly value.
    "master_heal":       ("forcefriendly", {1: "0"}),
}

# Ruled out as Force Barrier's root cause (kept for reference, unused
# while "barrier" is excluded from POWERS above): Barrier's raw K2
# category (0x1808) matched Force Shield/Force Aura's real K1 category,
# and Barrier's level-gate value (6) matched Force Shield's too. Moving
# the whole family to 0x1809 (confirmed unused anywhere in K1's
# spells.2da) did not change the character-sheet "next tier" behavior,
# so category/gate collision is not the actual mechanism. The shared
# level-gate value alone is a candidate but unconfirmed -- several other
# vanilla K1 powers already share gate values across different categories
# with no such bug, so it doesn't obviously explain this on its own
# either.
CATEGORY_OVERRIDE_BY_FAMILY = {"barrier": "0x1809"}

# Force Scream's raw K2 castanim ('fury') isn't used by any vanilla K1
# power, so this fixes it to 'self' (what Shock and every other real K1
# attack power use). Confirmed a real, valid correctness fix on its own
# terms ('fury' is definitively invalid in K1), but does not by itself
# change Force Scream's cast animation, which still looks identical to
# Shock's -- that visual's actual cause is a separate, still-open
# question.
CASTANIM_OVERRIDE_BY_FAMILY = {"scream": "self"}

# Master Heal's raw K2 'range' column is a touch/target value, but the
# real mechanic (_master_heal_body) heals the whole party automatically
# from OBJECT_SELF -- the same self-contained shape Revitalize already
# uses (range='P', no target selection needed). Without this override the
# UI would prompt for a touch target it then ignores.
RANGE_OVERRIDE_BY_FAMILY = {"master_heal": "P"}


def _arg_value(flag, default):
    for i, a in enumerate(sys.argv):
        if a == flag and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
        if a.startswith(flag + "="):
            return a.split("=", 1)[1]
    return default


def _load_manifest():
    try:
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"rows": {}, "strrefs": {}, "files": []}


def _save_manifest(m):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=2)


# ---------------------------------------------------------------------------
# Impact scripts -- K1 rewrites of the K2 k_inc_force.nss branches.
# ---------------------------------------------------------------------------

def _strip_related_lines(ids, target_var):
    """NWScript that removes any effect on target_var whose spell id is one
    of `ids` -- the K1 stand-in for K2's Sp_RemoveRelatedPowers (a new tier
    replaces an older/equal one instead of stacking). Uses its own
    nOldSid (not nSid) since this is inlined into the combined script's
    main(), which already has an outer nSid for the GetSpellId() dispatch."""
    cond = " || ".join(f"nOldSid == {i}" for i in ids)
    return f"""effect eOld = GetFirstEffect({target_var});
        while (GetIsEffectValid(eOld))
        {{
            int nOldSid = GetEffectSpellId(eOld);
            if ({cond}) RemoveEffect({target_var}, eOld);
            eOld = GetNextEffect({target_var});
        }}"""


def _barrier_body(tier, family_ids):
    amount = {1: 4, 2: 8, 3: 15}[tier]
    duration = {1: 30.0, 2: 45.0, 3: 60.0}[tier]
    return f"""{{
        // K1 port of KOTOR 2's FORCE_POWER_{'' if tier == 1 else ('IMPROVED_' if tier == 2 else 'MASTER_')}FORCE_BARRIER (k_inc_force.nss, DJS-OEI 12/11/2003).
        object oCaster = OBJECT_SELF;
{_strip_related_lines(family_ids, "oCaster")}
        effect eLink = EffectDamageResistance(DAMAGE_TYPE_BLUDGEONING, {amount});
        eLink = EffectLinkEffects(eLink, EffectDamageResistance(DAMAGE_TYPE_PIERCING, {amount}));
        eLink = EffectLinkEffects(eLink, EffectDamageResistance(DAMAGE_TYPE_SLASHING, {amount}));
        effect eVis = EffectVisualEffect(VFX_PRO_FORCE_ARMOR);
        eVis = EffectLinkEffects(eVis, EffectVisualEffect(VFX_PRO_FORCE_SHIELD));
        ApplyEffectToObject(DURATION_TYPE_TEMPORARY, eLink, oCaster, {duration:.1f});
        ApplyEffectToObject(DURATION_TYPE_TEMPORARY, eVis, oCaster, 3.0);
        KSE_Diag(151, "AP|FORCEPOWER|barrier|tier={tier}|dr={amount}|dur={duration:.0f}");
    }}"""


def _scream_body(tier, family_ids):
    dice = {1: 3, 2: 5, 3: 7}[tier]
    attr = {1: 2, 2: 4, 3: 6}[tier]
    if tier == 3:
        shape, size, loc = "SHAPE_SPHERE", "12.0", "GetLocation(oCaster)"
    else:
        shape, size, loc = "SHAPE_SPELLCONE", "20.0", "GetLocation(GetSpellTarget())"
    return f"""{{
        // K1 port of KOTOR 2's FORCE_POWER_{'' if tier == 1 else ('IMPROVED_' if tier == 2 else 'MASTER_')}FORCE_SCREAM (k_inc_force.nss, DJS-OEI 12/30/2003).
        // K2's dedicated scream VFX (9005-9007) don't exist in K1's visualeffects.2da;
        // VFX_FNF_FORCE_WAVE is the closest shipped K1 burst.
        object oCaster = OBJECT_SELF;
        int nDC = GetSpellSaveDC();
        location lTarget = {loc};
        int nHit = 0;
        ApplyEffectToObject(DURATION_TYPE_INSTANT, EffectVisualEffect(VFX_FNF_FORCE_WAVE), oCaster);
        object oTarget = GetFirstObjectInShape({shape}, {size}, lTarget, TRUE, OBJECT_TYPE_CREATURE);
        while (GetIsObjectValid(oTarget))
        {{
            if (oTarget != oCaster && GetIsEnemy(oTarget, oCaster) && GetRacialType(oTarget) != RACIAL_TYPE_DROID)
            {{
                SignalEvent(oTarget, EventSpellCastAt(oCaster, GetSpellId(), TRUE));
                int nDamage = d6({dice});
                if (WillSave(oTarget, nDC, SAVING_THROW_TYPE_SONIC, oCaster) == 0)
                {{
                    ApplyEffectToObject(DURATION_TYPE_INSTANT, EffectDamage(nDamage, DAMAGE_TYPE_SONIC), oTarget);
{_strip_related_lines(family_ids, "oTarget")}
                    effect eAttr = EffectAbilityDecrease(ABILITY_STRENGTH, {attr});
                    eAttr = EffectLinkEffects(eAttr, EffectAbilityDecrease(ABILITY_DEXTERITY, {attr}));
                    eAttr = EffectLinkEffects(eAttr, EffectAbilityDecrease(ABILITY_CONSTITUTION, {attr}));
                    eAttr = EffectLinkEffects(eAttr, EffectAbilityDecrease(ABILITY_INTELLIGENCE, {attr}));
                    eAttr = EffectLinkEffects(eAttr, EffectAbilityDecrease(ABILITY_WISDOM, {attr}));
                    eAttr = EffectLinkEffects(eAttr, EffectAbilityDecrease(ABILITY_CHARISMA, {attr}));
                    ApplyEffectToObject(DURATION_TYPE_TEMPORARY, eAttr, oTarget, 30.0);
                }}
                else
                {{
                    ApplyEffectToObject(DURATION_TYPE_INSTANT, EffectDamage(nDamage / 2, DAMAGE_TYPE_SONIC), oTarget);
                    ApplyEffectToObject(DURATION_TYPE_INSTANT, EffectForceResisted(oCaster), oTarget);
                }}
                nHit++;
            }}
            oTarget = GetNextObjectInShape({shape}, {size}, lTarget, TRUE, OBJECT_TYPE_CREATURE);
        }}
        KSE_Diag(151, "AP|FORCEPOWER|scream|tier={tier}|targets=" + IntToString(nHit));
    }}"""


def _revitalize_body(tier, family_ids):
    del family_ids  # Revitalize doesn't replace a lower tier (Sp_RemoveRelatedPowers analogue) -- N/A
    heal = {1: 10, 2: 25, 3: 50}[tier]
    if tier == 1:
        loop = f"""        object oBest = OBJECT_INVALID;
        float fBest = 999999.0;
        int i;
        for (i = 0; i < 3; i++)
        {{
            object oPM = GetPartyMemberByIndex(i);
            if (GetIsObjectValid(oPM) && oPM != oCaster && GetRacialType(oPM) != RACIAL_TYPE_DROID
                && GetCurrentHitPoints(oPM) < 1)
            {{
                float fDist = GetDistanceBetween(oCaster, oPM);
                if (fDist < fBest) {{ fBest = fDist; oBest = oPM; }}
            }}
        }}
        if (GetIsObjectValid(oBest)) {{ Revive(oCaster, oBest, {heal}); nRevived++; }}"""
    else:
        loop = f"""        int i;
        for (i = 0; i < 3; i++)
        {{
            object oPM = GetPartyMemberByIndex(i);
            if (GetIsObjectValid(oPM) && oPM != oCaster && GetRacialType(oPM) != RACIAL_TYPE_DROID
                && GetCurrentHitPoints(oPM) < 1)
            {{
                Revive(oCaster, oPM, {heal});
                nRevived++;
            }}
        }}"""
    return f"""{{
        // K1 port of KOTOR 2's FORCE_POWER_{'' if tier == 1 else ('IMPROVED_' if tier == 2 else 'MASTER_')}REVITALIZE (k_inc_force.nss, DJS-OEI 1/2/2004;
        // fixed heal amounts per RWT-OEI 09/27/04 FMP#4893). Same EffectResurrection+
        // EffectHeal shape the K1FPP mod's Revitalise already proved works in K1.
        object oCaster = OBJECT_SELF;
        int nRevived = 0;
        if (!IsObjectPartyMember(oCaster)) return;
{loop}
        KSE_Diag(151, "AP|FORCEPOWER|revitalize|tier={tier}|revived=" + IntToString(nRevived));
    }}"""


def _energy_resistance_body(tier, family_ids):
    del tier  # single-tier addition, no I/II/III
    return f"""{{
        // K1 port of KOTOR 2's FORCE_POWER_MASTER_ENERGY_RESISTANCE
        // (k_inc_force.nss, DJS-OEI 12/9-10/2003). Self-only, unlike K2's
        // real script (which also buffs the whole party for a PC caster)
        // -- kept consistent with K1's own Resist Energy 1/2, which are
        // both self-only, rather than introducing new party-wide scope
        // for what's meant to be a small, single-tier addition.
        object oCaster = OBJECT_SELF;
{_strip_related_lines(family_ids, "oCaster")}
        effect eLink = EffectDamageResistance(DAMAGE_TYPE_COLD, 20);
        eLink = EffectLinkEffects(eLink, EffectDamageResistance(DAMAGE_TYPE_FIRE, 20));
        eLink = EffectLinkEffects(eLink, EffectDamageResistance(DAMAGE_TYPE_SONIC, 20));
        eLink = EffectLinkEffects(eLink, EffectDamageResistance(DAMAGE_TYPE_BLASTER, 20));
        eLink = EffectLinkEffects(eLink, EffectDamageResistance(DAMAGE_TYPE_ELECTRICAL, 20));
        effect eVis = EffectVisualEffect(VFX_PRO_RESIST_ELEMENTS);
        ApplyEffectToObject(DURATION_TYPE_TEMPORARY, eLink, oCaster, 120.0);
        ApplyEffectToObject(DURATION_TYPE_TEMPORARY, eVis, oCaster, 1.0);
        KSE_Diag(151, "AP|FORCEPOWER|energy_resistance|dr=20|dur=120");
    }}"""


def _master_heal_body(tier, family_ids):
    del tier  # single-tier addition, no I/II/III
    return f"""{{
        // K1 port of KOTOR 2's FORCE_POWER_MASTER_HEAL (k_inc_force.nss,
        // "Same as Improved Heal with addition 5 VP and Stun removal").
        // Party-wide like Revitalize -- heals the caster plus every valid
        // party member. Formula is K2's own active code path verbatim
        // (its Form/Stance multiplier branch is commented out in K2's
        // own shipped source too, so nMultiplier is always 1 there).
        object oCaster = OBJECT_SELF;
{_strip_related_lines(family_ids, "oCaster")}
        int nHeal = GetAbilityModifier(ABILITY_WISDOM, oCaster) + GetAbilityModifier(ABILITY_CHARISMA, oCaster)
                  + 15 + 2 * GetHitDice(oCaster);
        int i;
        for (i = 0; i < 3; i++)
        {{
            object oPM = GetPartyMemberByIndex(i);
            if (GetIsObjectValid(oPM))
            {{
{_strip_related_lines(family_ids, "oPM")}
                ApplyEffectToObject(DURATION_TYPE_INSTANT, EffectHeal(nHeal), oPM);
                effect eStun = GetFirstEffect(oPM);
                while (GetIsEffectValid(eStun))
                {{
                    if (GetEffectType(eStun) == EFFECT_TYPE_STUNNED) RemoveEffect(oPM, eStun);
                    eStun = GetNextEffect(oPM);
                }}
                ApplyEffectToObject(DURATION_TYPE_INSTANT, EffectVisualEffect(VFX_IMP_HEAL), oPM);
            }}
        }}
        KSE_Diag(151, "AP|FORCEPOWER|master_heal|amount=" + IntToString(nHeal));
    }}"""


BODY_BUILDERS = {"barrier": _barrier_body, "scream": _scream_body, "revitalize": _revitalize_body,
                  "energy_resistance": _energy_resistance_body, "master_heal": _master_heal_body}
COMBINED_SCRIPT_NAME = "ap_fp_powers"


def build_combined_script(row_ids, family_ids):
    """One shared impact script for all 9 ported powers, dispatched on
    GetSpellId() -- the same pattern several of BioWare's own shared impact
    scripts already use in this engine. Replaces the original 9-file pilot
    now that these are a standing feature (see ap_extender.c's
    ap_bootstrap_tsl_force_powers()) rather than a per-seed AP item, so
    there's no reason to keep 9 near-identical Override files."""
    branches = []
    for label, _, _, family, tier in POWERS:
        body = BODY_BUILDERS[family](tier, family_ids[family])
        branches.append(f"if (nSid == {row_ids[label]})\n    {body}")
    dispatch = "    " + "\n    else ".join(branches)
    return f"""// Combined impact script for the 9 ported KOTOR 2 Force Powers (Revitalize,
// Force Scream, Force Barrier -- all 3 tiers each). Generated by
// scripts/patch_tsl_powers.py. One shared resref instead of 9: these are a
// standing feature of this build (granted automatically every launch, see
// ap_extender.c's ap_bootstrap_tsl_force_powers()), not a per-seed AP pilot.
#include "kse"

void Revive(object oCaster, object oTarget, int nHeal)
{{
    SignalEvent(oTarget, EventSpellCastAt(oCaster, GetSpellId(), FALSE));
    ApplyEffectToObject(DURATION_TYPE_INSTANT, EffectResurrection(), oTarget);
    ApplyEffectToObject(DURATION_TYPE_INSTANT, EffectHeal(nHeal), oTarget);
    ApplyEffectToObject(DURATION_TYPE_INSTANT, EffectVisualEffect(VFX_IMP_HEAL), oTarget);
}}

void main()
{{
    int nSid = GetSpellId();
{dispatch}
}}
"""


# ---------------------------------------------------------------------------

def restore(game_dir):
    manifest = _load_manifest()
    override_dir = os.path.join(game_dir, "Override")
    tlk_backup = os.path.join(BACKUP_DIR, "dialog.tlk")
    if os.path.exists(tlk_backup):
        shutil.copy2(tlk_backup, os.path.join(game_dir, "dialog.tlk"))
        print("  restored dialog.tlk from backup")
    spells_backup = os.path.join(BACKUP_DIR, "spells.2da.override")
    spells_live = os.path.join(override_dir, "spells.2da")
    if os.path.exists(spells_backup):
        shutil.copy2(spells_backup, spells_live)
        print("  restored the pre-existing Override/spells.2da from backup")
    elif manifest.get("spells_was_absent") and os.path.exists(spells_live):
        os.remove(spells_live)
        print("  removed Override/spells.2da (none existed before)")
    for fname in manifest.get("files", []):
        p = os.path.join(override_dir, fname)
        if os.path.exists(p):
            os.remove(p)
            print(f"  removed Override/{fname}")
    print("TSL powers: vanilla restored (the manifest is kept so a re-apply reuses the same row ids).")


def main():
    game_dir = _arg_value("--game-dir", DEFAULT_GAME_DIR)
    k2_dir = _arg_value("--k2-dir", DEFAULT_K2_DIR)
    if "--restore" in sys.argv:
        restore(game_dir)
        return
    if not os.path.isfile(os.path.join(k2_dir, "chitin.key")):
        sys.exit(f"KOTOR 2 install not found at {k2_dir!r} (no chitin.key) -- pass --k2-dir. "
                 "This pilot copies the powers' real data/icons out of a local K2 install; "
                 "nothing is bundled.")
    if not os.path.exists(NWNNSSCOMP):
        sys.exit(f"nwnnsscomp.exe not found ({NWNNSSCOMP}) -- needed to compile the 9 impact scripts.")

    override_dir = os.path.join(game_dir, "Override")
    os.makedirs(override_dir, exist_ok=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)
    manifest = _load_manifest()
    manifest.setdefault("rows", {})
    manifest.setdefault("strrefs", {})
    manifest.setdefault("files", [])

    print("Reading both games' spells.2da ...")
    k1 = Installation(game_dir)
    k2 = Installation(k2_dir)
    k2_spells = read_2da(k2.resource("spells", ResourceType.TwoDA).data)
    spells_live = os.path.join(override_dir, "spells.2da")
    spells_backup = os.path.join(BACKUP_DIR, "spells.2da.override")
    if os.path.exists(spells_live):
        if not os.path.exists(spells_backup) and not manifest.get("spells_was_absent"):
            shutil.copy2(spells_live, spells_backup)
            print(f"  backed up the pre-existing Override/spells.2da -> {spells_backup}")
        with open(spells_live, "rb") as f:
            k1_spells = read_2da(f.read())
    else:
        manifest["spells_was_absent"] = True
        k1_spells = read_2da(k1.resource("spells", ResourceType.TwoDA, [SearchLocation.CHITIN]).data)
    k1_headers = k1_spells.get_headers()
    k2_headers = set(k2_spells.get_headers())
    missing = [h for h in k1_headers if h not in k2_headers]
    if missing:
        sys.exit(f"K2 spells.2da lacks K1 columns {missing} -- schema assumption broken, refusing to guess.")

    # --- TLK ---------------------------------------------------------------
    tlk_path = os.path.join(game_dir, "dialog.tlk")
    tlk_backup = os.path.join(BACKUP_DIR, "dialog.tlk")
    if not os.path.exists(tlk_backup):
        shutil.copy2(tlk_path, tlk_backup)
        print(f"  backed up dialog.tlk -> {tlk_backup}")
    with open(tlk_path, "rb") as f:
        k1_tlk = read_tlk(f.read())
    with open(os.path.join(k2_dir, "dialog.tlk"), "rb") as f:
        k2_tlk = read_tlk(f.read())
    tlk_dirty = False

    def ensure_strref(label, kind, text):
        nonlocal tlk_dirty
        existing = manifest["strrefs"].get(label, {}).get(kind)
        if existing is not None and existing < len(k1_tlk) and k1_tlk.get(existing).text == text:
            return existing
        idx = k1_tlk.add(text)
        manifest["strrefs"].setdefault(label, {})[kind] = idx
        tlk_dirty = True
        return idx

    # --- Locate every K2 row by label, assign K1 row ids -------------------
    k2_rows = {}
    for i in range(k2_spells.get_height()):
        k2_rows[k2_spells.get_cell(i, "label")] = i
    k1_existing = {k1_spells.get_cell(i, "label"): i for i in range(k1_spells.get_height())}
    row_ids = {}
    for label, expected_row, script, family, tier in POWERS:
        if label not in k2_rows:
            sys.exit(f"{label} not found in K2's spells.2da")
        if k2_rows[label] != expected_row:
            print(f"  note: {label} is K2 row {k2_rows[label]}, expected {expected_row} (using the real one)")
        if label in k1_existing:
            row_ids[label] = k1_existing[label]
        else:
            row_ids[label] = k1_spells.add_row(str(k1_spells.get_height()))
            k1_existing[label] = row_ids[label]
        manifest["rows"][label] = row_ids[label]
    k2_to_k1 = {k2_rows[label]: row_ids[label] for label, *_ in POWERS}
    family_ids = {}
    for label, _, _, family, _ in POWERS:
        family_ids.setdefault(family, []).append(row_ids[label])

    # Removing a label from POWERS above does not by itself stop it being
    # offered -- its row still carries real, valid data from whenever it
    # was last ported, so KOTOR's own native level-up screen keeps
    # naturally selecting it for any Jedi reaching that level, independent
    # of the Vendor or this script's own POWERS loop. manifest["rows"]
    # persists every label ever ported (never cleaned up on its own), so
    # it's the source of truth for "orphaned" rows -- anything it
    # remembers that's no longer in POWERS gets neutered here.
    #
    # Blanking "name" to '' is the fix, not blanking guardian/consular/
    # sentinel to "****": confirmed vanilla cut-content rows
    # (FORCE_JUMP_XXX/REGENERATION_XXX) actually have
    # guardian=consular=sentinel='0' (a value plenty of real, legitimate
    # powers also use, meaning "available from level 1" -- the opposite of
    # exclusion). What those cut-content rows share instead is an empty
    # "name" TLK strref -- the level-up UI has no valid label to render,
    # so it can't offer them. Blanking "name" matches that same,
    # already-shipping-in-retail-K1 convention.
    current_labels = {label for label, *_ in POWERS}
    for label, row in list(manifest["rows"].items()):
        if label in current_labels:
            continue
        if row >= k1_spells.get_height():
            continue
        k1_spells.set_cell(row, "name", "")
        print(f"  orphaned row {row} ({label}): blanked name strref so it can't be offered on level-up")

    # --- Fill the rows -----------------------------------------------------
    for label, _, script, family, tier in POWERS:
        src = k2_rows[label]
        dst = row_ids[label]
        for h in k1_headers:
            k1_spells.set_cell(dst, h, k2_spells.get_cell(src, h))
        name_ref = int(k2_spells.get_cell(src, "name"))
        desc_ref = int(k2_spells.get_cell(src, "spelldesc"))
        name_text = k2_tlk.get(name_ref).text
        desc_text = k2_tlk.get(desc_ref).text.replace("Character Level 21", f"Character Level {K1_LEVEL_CAP}")
        k1_spells.set_cell(dst, "name", str(ensure_strref(label, "name", name_text)))
        k1_spells.set_cell(dst, "spelldesc", str(ensure_strref(label, "desc", desc_text)))
        prereq = k2_spells.get_cell(src, "prerequisites")
        if prereq:
            k1_spells.set_cell(dst, "prerequisites",
                               "_".join(str(k2_to_k1.get(int(p), p)) for p in prereq.split("_") if p))
        k1_spells.set_cell(dst, "impactscript", COMBINED_SCRIPT_NAME)
        for col in LEVEL_GATE_COLUMNS:
            v = k2_spells.get_cell(src, col)
            if v.strip().lstrip("-").isdigit() and int(v) > K1_LEVEL_CAP:
                k1_spells.set_cell(dst, col, str(K1_LEVEL_CAP))
        for col in AI_COLUMNS:
            k1_spells.set_cell(dst, col, "")
        ai_col, ai_values = AI_COLUMN_BY_FAMILY[family]
        k1_spells.set_cell(dst, ai_col, ai_values[tier])
        if family in CATEGORY_OVERRIDE_BY_FAMILY:
            k1_spells.set_cell(dst, "category", CATEGORY_OVERRIDE_BY_FAMILY[family])
        if family in CASTANIM_OVERRIDE_BY_FAMILY:
            k1_spells.set_cell(dst, "castanim", CASTANIM_OVERRIDE_BY_FAMILY[family])
        if family in RANGE_OVERRIDE_BY_FAMILY:
            k1_spells.set_cell(dst, "range", RANGE_OVERRIDE_BY_FAMILY[family])
        print(f"  row {dst:3d}  {name_text:<24s}  (gate L{k1_spells.get_cell(dst, 'guardian')}, "
              f"{k1_spells.get_cell(dst, 'forcepoints')} FP, {k1_spells.get_cell(dst, 'goodevil')})")

    data = bytearray()
    write_2da(k1_spells, data)
    with open(spells_live, "wb") as f:
        f.write(bytes(data))
    print(f"  wrote Override/spells.2da ({k1_spells.get_height()} rows)")
    if tlk_dirty:
        data = bytearray()
        write_tlk(k1_tlk, data)
        with open(tlk_path, "wb") as f:
            f.write(bytes(data))
        print(f"  wrote dialog.tlk ({len(k1_tlk)} entries)")
    else:
        print("  dialog.tlk already had every string, untouched")

    # --- Icons ---------------------------------------------------------------
    wanted = {k2_spells.get_cell(k2_rows[label], "iconresref").lower() for label, *_ in POWERS}
    gui_erf = read_erf(open(os.path.join(k2_dir, "TexturePacks", "swpc_tex_gui.erf"), "rb").read())
    copied = 0
    for res in gui_erf:
        name = str(res.resref).lower()
        if name in wanted:
            fname = f"{name}.{res.restype.extension}"
            with open(os.path.join(override_dir, fname), "wb") as f:
                f.write(res.data)
            if fname not in manifest["files"]:
                manifest["files"].append(fname)
            copied += 1
    print(f"  copied {copied}/{len(wanted)} icons from K2's swpc_tex_gui.erf")

    # --- Impact script -------------------------------------------------------
    # One combined script (dispatched on GetSpellId()) instead of 9 separate
    # ones -- these are a standing feature now, not a per-seed AP pilot, so
    # remove any leftover per-power files from an older run of this script.
    old_per_power_files = {f"{script}.ncs" for _, _, script, _, _ in POWERS} | \
        {f"{script}.nss" for _, _, script, _, _ in POWERS}
    for fname in old_per_power_files:
        for d in (override_dir, SRC_DIR):
            p = os.path.join(d, fname)
            if os.path.exists(p):
                os.remove(p)
        if fname in manifest["files"]:
            manifest["files"].remove(fname)

    nss_path = os.path.join(SRC_DIR, f"{COMBINED_SCRIPT_NAME}.nss")
    ncs_path = os.path.join(SRC_DIR, f"{COMBINED_SCRIPT_NAME}.ncs")
    with open(nss_path, "w", encoding="utf-8") as f:
        f.write(build_combined_script(row_ids, family_ids))
    result = subprocess.run([NWNNSSCOMP, "-c", nss_path, "-o", ncs_path],
                            capture_output=True, text=True, cwd=SRC_DIR)
    if not os.path.exists(ncs_path) or os.path.getmtime(ncs_path) < os.path.getmtime(nss_path) - 5:
        sys.exit(f"COMPILE FAILED for {COMBINED_SCRIPT_NAME}:\n{result.stdout}\n{result.stderr}")
    shutil.copy2(ncs_path, os.path.join(override_dir, f"{COMBINED_SCRIPT_NAME}.ncs"))
    if f"{COMBINED_SCRIPT_NAME}.ncs" not in manifest["files"]:
        manifest["files"].append(f"{COMBINED_SCRIPT_NAME}.ncs")
    print(f"  compiled + deployed 1 combined impact script for all {len(POWERS)} powers")

    _save_manifest(manifest)
    print("\nTSL powers: INSTALLED. Row ids for /ap_apply force_power:<id> --")
    for label, _, script, family, tier in POWERS:
        print(f"    {row_ids[label]:3d}  {label}")
    print(f"(manifest: {MANIFEST_PATH}; fully exit KOTOR before testing -- spells.2da is cached per process)")


if __name__ == "__main__":
    main()
