"""
Archipelago Vendor -- permanent purchase NPC on the Ebon Hawk. See
FutureDesign.md's "Archipelago Vendor" section for the full design and
decision history.

Phase 1: Train Skill (8-way picker) and Train Ability (6-way picker),
both credit-gated and capped at 5 total uses each. Phase 2 (this
revision): Train Feat (18-way picker, reusing KotorClient.py's own
already-vetted ADDITIONAL_FEATS_POOL) and Train Force Power (15-way
picker, curated straight from spells.2da's own prerequisites/class-level
columns -- every entry is genuinely base-tier, no dependency on an
earlier power). Neither is purchase-count capped like Skill/Ability --
each specific feat/power can only ever be bought once, enforced per-item
via GetHasFeat/GetHasSpell dedup on that item's own picker reply. Train
Force Power as a whole is gated on the PC having real Force levels; the
3 Jedi-signature feats (Force Jump/Force Focus/Force Immunity: Fear) get
that same check ANDed into their own per-item conditional.

Character Reset is implemented (resets level/feats/powers/abilities/
skills). Class Change is not offered: this project's class-write
mechanisms only overwrite an existing class slot's type, never allocate a
new one, so there's no safe way yet to give a single-class PC a genuine
second class -- see DEVELOPMENT_HISTORY.md for the full writeup.

Engine constraints this design works around:
- TakeGoldFromCreature is a confirmed no-op in this engine build -- credit
  deduction uses KSE_SetCredits(oPC, GetGold(oPC) - cost) instead.
- DLGLink's active1_not/active2_not fields are never used anywhere in the
  entire base game (confirmed: scanned all 1,016 unique vanilla .dlg
  files, 10,988 real active1 uses, 0 active1_not/active2_not uses) --
  pykotor's own docstring flags them "KotOR 2 Only". So the credit
  check-before-grant branch uses TWO independent, non-negated conditional
  scripts per price tier (a "has enough" and a "doesn't have enough"),
  never a shared script + negation flag.
- Every resref here is kept well under KOTOR's real 16-character resref
  cap (a longer name silently truncates on write with no error).
- Every DLGEntry/DLGReply explicitly sets plot_index = -1 (pykotor
  defaults to 0, a real plot/quest node that grants XP on reach).

Purchase-count storage: KOTOR's GetLocalNumber/SetLocalNumber are
INDEX-based, not string-keyed (a real K1 API difference from NWN).
Indices 60-63 on the PC object are reserved for this feature (60 = Train
Skill, 61 = Train Ability, 62 = Character Reset, 63 = Alignment Change
purchase count) -- no other use of PC-object-scoped LocalNumber/
LocalBoolean exists elsewhere in this project.

Alignment Change (added later): a real native AdjustAlignment(oSubject,
nAlignment, nShift) call -- not KSE_SetCreatureField -- same as every
other alignment shift this project ever does (see kotor_location_tracker.py's
own alignment-threshold bonuses). Two options sharing one 5-use cap
(ALIGNMENT_COUNT_IDX), same "N choices, one shared counter" shape as
Train Skill/Train Ability: "Steal from the Republic" (+10 dark side,
+1000 credits -- a pure gain, no credit gate needed) and "Donate to
Taris Refugees" (+10 light side, -5000 credits -- gated the same
yes/no-credit-check way every other paid option is). Not touched by
Character Reset (ap_vs_reset.nss) -- that script never adjusts alignment
at all, unlike ability/skill purchases which it explicitly wipes and
refunds the counter for.
"""
import os
import subprocess
import sys

from pykotor.extract.installation import Installation
from pykotor.resource.type import ResourceType
from pykotor.resource.formats.gff import read_gff, write_gff
from pykotor.resource.generics.utc import construct_utc, dismantle_utc
from pykotor.resource.generics.dlg import DLG, DLGEntry, DLGReply, DLGLink, dismantle_dlg
from pykotor.common.language import LocalizedString
from pykotor.common.misc import ResRef, Game

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
OVERRIDE_DIR = os.path.join(GAME_DIR, "Override")
SRC_DIR = os.path.join(REPO_ROOT, "extender", "scripts_src")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nwnnsscomp_path import resolve_nwnnsscomp  # noqa: E402
NWNNSSCOMP = resolve_nwnnsscomp()

SKILL_COUNT_IDX = 60
ABILITY_COUNT_IDX = 61
RESET_COUNT_IDX = 62
ALIGNMENT_COUNT_IDX = 63
PURCHASE_CAP = 5

SKILL_PRICE = 1000
ABILITY_PRICE = 4000
RESET_PRICE = 6000

ALIGN_SHIFT_AMOUNT = 10
ALIGN_STEAL_GAIN = 1000
ALIGN_DONATE_PRICE = 5000

# Character Reset hard-resets all 6 abilities to this flat value. 10 is
# the true d20 "neutral" baseline (a score of
# 10-11 gives a +0 modifier, no bonus or penalty); a real KOTOR starting
# character never sits at the customization floor (8, a real -1 penalty)
# across all six simultaneously, since that means spending none of their
# creation points, so 10 reads as a genuine "blank slate" reset rather
# than punishing the player below any real starting character's actual
# stats.
RESET_ABILITY_FLOOR = 10

# A blanket "strip every known feat" Character Reset would permanently
# lose each class's automatic level-1 proficiencies (Weapon/Armor Prof,
# Force Sensitive, etc.): KOTOR only grants these once, the first time a
# character takes level 1 in that class -- an ordinary subsequent
# level-up (even back up from level 1 again) never re-runs that one-time
# grant, only the per-level CHOICE feats. So Character Reset must never
# strip a feat the PC's current class(es) would auto-grant -- everything
# else (level-up choices, Vendor Train Feat purchases) still gets
# stripped and correctly comes back naturally as they relevel. Source:
# feat.2da's own per-class `<code>_granted` columns (see GameMechanics.md's
# "Auto-granted feats" table and research/feats/class_feats.json for the
# full dump).
CLASS_AUTO_GRANTED_FEATS = {
    "CLASS_TYPE_SOLDIER": [4, 5, 6, 28, 29, 39, 40, 42, 44],
    "CLASS_TYPE_SCOUT": [5, 6, 11, 14, 30, 39, 40, 44],
    "CLASS_TYPE_SCOUNDREL": [5, 8, 31, 39, 40, 44, 60, 104],
    "CLASS_TYPE_JEDIGUARDIAN": [39, 43, 44, 55, 101, 107, 116],
    "CLASS_TYPE_JEDICONSULAR": [39, 43, 44, 55, 88, 107, 116],
    "CLASS_TYPE_JEDISENTINEL": [39, 43, 44, 55, 98, 107, 116],
}

# (short resref suffix, display text, SKILL_* constant)
SKILLS = [
    ("cu", "Train Computer Use", "SKILL_COMPUTER_USE"),
    ("dem", "Train Demolitions", "SKILL_DEMOLITIONS"),
    ("ste", "Train Stealth", "SKILL_STEALTH"),
    ("awa", "Train Awareness", "SKILL_AWARENESS"),
    ("per", "Train Persuade", "SKILL_PERSUADE"),
    ("rep", "Train Repair", "SKILL_REPAIR"),
    ("sec", "Train Security", "SKILL_SECURITY"),
    ("ti", "Train Treat Injury", "SKILL_TREAT_INJURY"),
]

# (short resref suffix, display text, ABILITY_* constant)
ABILITIES = [
    ("str", "Train Strength", "ABILITY_STRENGTH"),
    ("dex", "Train Dexterity", "ABILITY_DEXTERITY"),
    ("con", "Train Constitution", "ABILITY_CONSTITUTION"),
    ("int", "Train Intelligence", "ABILITY_INTELLIGENCE"),
    ("wis", "Train Wisdom", "ABILITY_WISDOM"),
    ("cha", "Train Charisma", "ABILITY_CHARISMA"),
]

FEAT_PRICE = 3000
POWER_PRICE = 3000

# Reuses the SAME curated pool KotorClient.py's ADDITIONAL_FEATS_POOL
# already vets and grants elsewhere (weapon/armor profs, Implant Level 1,
# each base class's signature feat) -- not reinvented here. (feat.2da id,
# display text, is_signature). The 3 Jedi-signature feats
# (Force Jump/Force Focus/Force Immunity: Fear -- KotorClient.py's own
# _JEDI_ONLY_FEATS) are additionally gated on the PC actually having Force
# levels, same is_jedi reasoning _check_pending_additional_feats already
# applies for companions.
#
# REAL BUG confirmed live, 2026-09-19: Power Attack, Power Blast, Flurry,
# Rapid Shot, Critical Strike, Sniper Shot, and Force Jump (feat, not the
# power) are all ACTIVE/toggle combat feats -- granting Flurry via this
# vendor confirmed the grant call runs (logged, credits deducted,
# KSE_Diag confirms it) and GetHasFeat presumably returns true, but the
# feat does NOT appear in the character sheet's trained/usable feats
# list AND does not work against a real enemy in combat, even after a
# real area transition. This is the first live-confirmed answer to the
# previously-open question research arm 51 (test_grant_active_feat,
# generate_trampoline_batch.py) was built to test -- KSE_GrantFeatArrayA
# does not make an active/toggle feat genuinely usable, only sheet-
# flag-set. Every PASSIVE feat below (no hotbar/quickbar slot needed) is
# unaffected and matches feats already confirmed working elsewhere in
# the project via this exact native.
#
# RULED OUT, 2026-09-19: tried the client/server-split theory above --
# temporarily restored these 7, bought Flurry, saved, fully closed and
# relaunched the game, reloaded that save. Result: Flurry was STILL
# purchasable in the vendor afterward (i.e. the game now thinks the PC
# never had it). Confirmed the real reason by reading the actual save
# file directly (pykotor, same GFF tooling this project always uses):
# feat id 11 is genuinely absent from Mod_PlayerList[0].FeatList inside
# the saved module IFO (ebo_m12aa's SAV inside SAVEGAME.sav) -- 16 real
# feats there, none of them Flurry. So this was never a UI-refresh or
# client/server-sync gap -- KSE_GrantFeatArrayA writes to a live,
# in-memory-only "Array A" that GetHasFeat/GetHasSpell scan (why the
# grant "looked" successful), but that array is NOT the same list the
# game's save writer treats as authoritative. Removed again -- do not
# re-add without a real extender-level fix (see FutureDesign.md's
# research leads, especially the never-wired-up "container" feat
# structure in offsets.h).
FEATS = [
    (40, "Train Weapon Proficiency: Blaster Rifle", False),
    (42, "Train Weapon Proficiency: Heavy Weapons", False),
    (43, "Train Weapon Proficiency: Lightsaber", False),
    (4, "Train Armor Proficiency: Heavy", False),
    (5, "Train Armor Proficiency: Light", False),
    (6, "Train Armor Proficiency: Medium", False),
    (14, "Train Implant Level 1", False),
    (60, "Train Sneak Attack I", False),
    (104, "Train Scoundrel's Luck", False),
    (88, "Train Force Focus", True),
    (98, "Train Force Immunity: Fear", True),
]

# Curated from spells.2da directly (not guessed) -- every row here has an
# empty "prerequisites" column AND guardian/consular/sentinel==0 (the
# columns that gate a vanilla level-up pick behind an earlier power/a
# minimum class level), i.e. genuinely base-tier, no-dependency powers.
# Excludes every Advanced/Master/_XXX-suffixed tier and everything that
# needs a lower-tier power already known. The whole Train Force Power
# option is gated on the PC having real Force levels (see
# ap_vpwr_jedi below) -- these are dead weight otherwise, same reasoning
# ADDITIONAL_FEATS_POOL's is_jedi filter already applies. (spells.2da id,
# display text)
#
# IDs 21 (Force Jump) and 39 (Regeneration) were originally on this list
# -- both matched the empty-prerequisites/no-min-level filter above, but
# turned out to be real cut content: confirmed live (granting Regeneration
# via the vendor produced no effect and no in-game power at all), then
# confirmed why directly in spells.2da -- both rows have an EMPTY "name"
# TLK reference and forcepoints=0, unlike every real power (e.g. Force
# Push has name=282, forcepoints=10). The "_XXX" suffix on their own
# spells.2da labels (FORCE_POWER_FORCE_JUMP_XXX /
# FORCE_POWER_REGENERATION_XXX) is BioWare's own cut-content marker --
# should have been cross-checked against the label text, not just the
# prerequisite/level columns, before trusting a row as grantable.
#
# BIGGER BUG confirmed live, 2026-09-19: bought Resist Energy I (id 42,
# a genuinely real, non-cut power) via the vendor -- KSE_Diag confirmed
# the grant script ran and credits were deducted, but it never appeared
# in the Force Powers menu at all. Same shape as the active-feat bug
# found in FEATS above (KSE_SetCreatureField's ADD_FORCE_POWER field is
# a raw write, and this project already separately confirmed elsewhere
# that a raw field write "skips the engine's own class-change
# housekeeping entirely" for Force Powers granted to companions -- this
# is now confirmed true for the PC too, live, not just companions).
#
# RULED OUT, 2026-09-19: same test as FEATS above -- bought a new power,
# saved, fully closed and relaunched, reloaded. Confirmed via the actual
# save file (Mod_PlayerList[0].ClassList[0].KnownList0 inside the saved
# module IFO): Resist Energy I (id 42) is genuinely absent, exact same
# root cause as the feats bug (KSE_SetCreatureField's ADD_FORCE_POWER
# writes to a live in-memory list, not whatever the save writer treats
# as authoritative). reply_power is NOT wired into entry_greet in
# build_dlg() below -- do not re-add without a real extender-level fix.
#
# TSL-ported powers (see scripts/patch_tsl_powers.py). Only the base tier
# of each tiered family -- Improved/Master both have real prerequisites on
# the lower tier (same "no dependency" curation rule as the vanilla pool),
# so those tiers are excluded the same way Advanced/Master vanilla tiers
# are.
#
# Revitalize (row 133) intentionally excluded: it's the target of
# ap_extender.c's ap_bootstrap_tsl_force_powers() (currently disabled, see
# that function's own call site comment), so a Vendor entry for it would
# be redundant even once that's re-enabled. Force Scream (136) has a known
# cosmetic bug -- its cast animation looks identical to Shock's even after
# fixing its raw K2 castanim to 'self' (see CASTANIM_OVERRIDE_BY_FAMILY in
# patch_tsl_powers.py); the actual cause is still open, but the power
# itself is otherwise fully functional (damage/save/debuff all work), so
# it stays exposed here. Force Barrier (139) is excluded here too: its
# character-sheet "next tier" navigation lands on Force Shield instead of
# Improved Force Barrier (see patch_tsl_powers.py's
# CATEGORY_OVERRIDE_BY_FAMILY comment for what was ruled out). Master
# Energy Resistance (142) and Master Heal (143) are new additions,
# single-tier caps on lines K1 already has -- verified column-clean
# against their real K1 predecessors, no override needed.
POWERS = [
    (6, "Train Affect Mind"),
    (8, "Train Speed Burst"),
    (16, "Train Fear"),
    (18, "Train Force Aura"),
    (22, "Train Force Valor"),
    (23, "Train Force Push"),
    (42, "Train Resist Energy I"),
    (43, "Train Shock"),
    (45, "Train Slow"),
    (46, "Train Stun"),
    (47, "Train Droid Stun"),
    (49, "Train Lightsaber Throw"),
    (50, "Train Wound"),
    (136, "Train Force Scream"),
    (142, "Train Master Energy Resistance"),
    (143, "Train Master Heal"),
]

# The curated POWERS pool above is restricted to powers with an empty
# spells.2da "prerequisites" column (see this list's own docstring), so
# most entries need no tier-gate check at the point of purchase. Master
# Energy Resistance (142, real prereq "40_42" = Resist Energy II + I) and
# Master Heal (143, real prereq "10_28" = Cure + Heal) are the exception --
# without this, a player could buy straight into the Master tier via the
# Vendor without ever having earned the lower ones. power_id -> list of
# OTHER power_ids that must ALL already be known first (empty list/absent
# key = no additional gate, matching every other entry above).
POWER_PREREQUISITES = {
    142: [40, 42],
    143: [10, 28],
}

VENDOR_LOCATION = (55.5, 36.5, 1.80)


def write_and_compile(resref, source):
    """Writes an .nss to SRC_DIR and compiles it to .ncs in place, using
    the mtime-advance + stdout-failure-marker check established in
    generate_trampoline_batch.py (a bare os.path.exists check stays TRUE
    even on a failed compile, because nwnnsscomp.exe leaves a stale prior
    .ncs untouched on error)."""
    nss_path = os.path.join(SRC_DIR, f"{resref}.nss")
    ncs_path = os.path.join(SRC_DIR, f"{resref}.ncs")
    with open(nss_path, "w") as f:
        f.write(source)

    mtime_before = os.path.getmtime(ncs_path) if os.path.exists(ncs_path) else None
    result = subprocess.run(
        [NWNNSSCOMP, "-c", nss_path, "-o", ncs_path],
        capture_output=True, text=True, cwd=SRC_DIR, timeout=30,
    )
    compiled_fresh = os.path.exists(ncs_path) and (
        mtime_before is None or os.path.getmtime(ncs_path) != mtime_before
    )
    if not compiled_fresh:
        print(f"  COMPILE FAILED: {resref}\n{result.stdout}\n{result.stderr}")
        return False
    with open(ncs_path, "rb") as f:
        data = f.read()
    with open(os.path.join(OVERRIDE_DIR, f"{resref}.ncs"), "wb") as f:
        f.write(data)
    print(f"  compiled + deployed -> {resref}.ncs")
    return True


def build_conditional_scripts():
    ok = True
    ok &= write_and_compile("ap_vg1000y", f'''#include "kse"

int StartingConditional()
{{
    return GetGold(GetPCSpeaker()) >= {SKILL_PRICE};
}}
''')
    ok &= write_and_compile("ap_vg1000n", f'''#include "kse"

int StartingConditional()
{{
    return GetGold(GetPCSpeaker()) < {SKILL_PRICE};
}}
''')
    ok &= write_and_compile("ap_vg4000y", f'''#include "kse"

int StartingConditional()
{{
    return GetGold(GetPCSpeaker()) >= {ABILITY_PRICE};
}}
''')
    ok &= write_and_compile("ap_vg4000n", f'''#include "kse"

int StartingConditional()
{{
    return GetGold(GetPCSpeaker()) < {ABILITY_PRICE};
}}
''')
    ok &= write_and_compile("ap_vsk_cap", f'''#include "kse"

int StartingConditional()
{{
    return GetLocalNumber(GetPCSpeaker(), {SKILL_COUNT_IDX}) < {PURCHASE_CAP};
}}
''')
    ok &= write_and_compile("ap_vab_cap", f'''#include "kse"

int StartingConditional()
{{
    return GetLocalNumber(GetPCSpeaker(), {ABILITY_COUNT_IDX}) < {PURCHASE_CAP};
}}
''')
    ok &= write_and_compile("ap_vg3000y", f'''#include "kse"

int StartingConditional()
{{
    return GetGold(GetPCSpeaker()) >= {FEAT_PRICE};
}}
''')
    ok &= write_and_compile("ap_vg3000n", f'''#include "kse"

int StartingConditional()
{{
    return GetGold(GetPCSpeaker()) < {FEAT_PRICE};
}}
''')
    # Same is_jedi test KotorClient.py's _check_pending_additional_feats
    # already uses for the PC (any real level in one of the 3 Jedi
    # classes) -- gates the whole Train Force Power option, and is ANDed
    # directly into each of the 3 Jedi-signature feats' own conditional
    # below (DLGLink's active2/logic combinator fields are, like
    # active1_not, never used anywhere in the base game -- not relied on).
    is_jedi_expr = (
        "(GetLevelByClass(CLASS_TYPE_JEDIGUARDIAN, oPC) > 0 ||"
        " GetLevelByClass(CLASS_TYPE_JEDICONSULAR, oPC) > 0 ||"
        " GetLevelByClass(CLASS_TYPE_JEDISENTINEL, oPC) > 0)"
    )
    ok &= write_and_compile("ap_vpwr_jedi", f'''#include "kse"

int StartingConditional()
{{
    object oPC = GetPCSpeaker();
    return {is_jedi_expr};
}}
''')
    for feat_id, _text, is_signature in FEATS:
        resref = f"ap_vfck{feat_id}"
        if is_signature:
            body = f'''#include "kse"

int StartingConditional()
{{
    object oPC = GetPCSpeaker();
    return !GetHasFeat({feat_id}, oPC) && {is_jedi_expr};
}}
'''
        else:
            body = f'''#include "kse"

int StartingConditional()
{{
    return !GetHasFeat({feat_id}, GetPCSpeaker());
}}
'''
        ok &= write_and_compile(resref, body)
    for power_id, _text in POWERS:
        resref = f"ap_vpck{power_id}"
        prereq_ids = POWER_PREREQUISITES.get(power_id, [])
        if prereq_ids:
            prereq_expr = " && ".join(f"GetHasSpell({pid}, oPC)" for pid in prereq_ids)
            body = f'''#include "kse"

int StartingConditional()
{{
    object oPC = GetPCSpeaker();
    return !GetHasSpell({power_id}, oPC) && {prereq_expr};
}}
'''
        else:
            body = f'''#include "kse"

int StartingConditional()
{{
    return !GetHasSpell({power_id}, GetPCSpeaker());
}}
'''
        ok &= write_and_compile(resref, body)

    # Character Reset -- price + purchase-cap gates, same shape as every
    # other priced option above.
    ok &= write_and_compile("ap_vg6000y", f'''#include "kse"

int StartingConditional()
{{
    return GetGold(GetPCSpeaker()) >= {RESET_PRICE};
}}
''')
    ok &= write_and_compile("ap_vg6000n", f'''#include "kse"

int StartingConditional()
{{
    return GetGold(GetPCSpeaker()) < {RESET_PRICE};
}}
''')
    ok &= write_and_compile("ap_vrs_cap", f'''#include "kse"

int StartingConditional()
{{
    return GetLocalNumber(GetPCSpeaker(), {RESET_COUNT_IDX}) < {PURCHASE_CAP};
}}
''')

    # Alignment Change -- shared cap gate (top-level menu entry only, same
    # "checked once at the menu, not re-checked per sub-option" shape as
    # Train Skill/Train Ability above) plus a credit gate for Donate's
    # cost. Steal is a pure gain, so it needs no credit gate at all.
    ok &= write_and_compile("ap_val_cap", f'''#include "kse"

int StartingConditional()
{{
    return GetLocalNumber(GetPCSpeaker(), {ALIGNMENT_COUNT_IDX}) < {PURCHASE_CAP};
}}
''')
    ok &= write_and_compile("ap_vg5000y", f'''#include "kse"

int StartingConditional()
{{
    return GetGold(GetPCSpeaker()) >= {ALIGN_DONATE_PRICE};
}}
''')
    ok &= write_and_compile("ap_vg5000n", f'''#include "kse"

int StartingConditional()
{{
    return GetGold(GetPCSpeaker()) < {ALIGN_DONATE_PRICE};
}}
''')
    return ok


def build_success_scripts():
    ok = True
    for suffix, _text, const in SKILLS:
        resref = f"ap_vs_{suffix}"
        ok &= write_and_compile(resref, f'''#include "kse"

void main()
{{
    object oPC = GetPCSpeaker();
    int nAfter = KSE_SetCredits(oPC, GetGold(oPC) - {SKILL_PRICE});
    KSE_AdjustCreatureSkills(oPC, {const}, 2);
    int nCount = GetLocalNumber(oPC, {SKILL_COUNT_IDX}) + 1;
    SetLocalNumber(oPC, {SKILL_COUNT_IDX}, nCount);
    KSE_Diag(200, "AP|APPLIED|vendor_train_skill|skill={const}|creditsAfter=" + IntToString(nAfter) + "|count=" + IntToString(nCount));
}}
''')
    # All 6 abilities use an absolute KSE_SetCreatureField SET instead of
    # ApplyEffectToObject + EffectAbilityIncrease -- this is a REPEATABLE
    # purchase (see ABILITY_COUNT_IDX below), so a player buying Train
    # Dexterity several times over a playthrough is exactly the
    # repeated-firing pattern that exhausted a real character's stacked-
    # effect budget live -- see offsets.h's KSE_FIELD_SET_STR_BASE-family
    # comment and generate_trampoline_batch.py's ability-trap/starting-bonus
    # rewrites for the full reasoning (same real bug, same fix). CON
    # routes through KSE_FIELD_INCREMENT_CON_BASE rather than the plain
    # KSE_FIELD_INCREMENT_*_BASE the other 5 use, since CON's real engine
    # setter needs the extra HP-recalculation parameter the others don't.
    #
    # Uses KSE_FIELD_INCREMENT_*_BASE rather than computing "new base =
    # GetAbilityScore(oPC, const) + 1" in NWScript: K1's GetAbilityScore
    # has no "base only" variant (only the 2-arg form exists in
    # nwscript.nss), so it returns the EFFECTIVE score (base + any
    # equipped item bonus), which would silently bake a temporary item
    # bonus in as a permanent base stat increase. KSE_FIELD_INCREMENT_*_BASE
    # reads the true base natively and adds the delta there instead -- see
    # offsets.h's KSE_STATS_STR_BASE_OFF comment.
    _VENDOR_ABILITY_INCREMENT_FIELD = {
        "str": "KSE_FIELD_INCREMENT_STR_BASE", "dex": "KSE_FIELD_INCREMENT_DEX_BASE",
        "con": "KSE_FIELD_INCREMENT_CON_BASE",
        "int": "KSE_FIELD_INCREMENT_INT_BASE", "wis": "KSE_FIELD_INCREMENT_WIS_BASE",
        "cha": "KSE_FIELD_INCREMENT_CHA_BASE",
    }
    for suffix, _text, const in ABILITIES:
        resref = f"ap_va_{suffix}"
        grant_line = f"KSE_SetCreatureField(oPC, {_VENDOR_ABILITY_INCREMENT_FIELD[suffix]}(), 1);"
        ok &= write_and_compile(resref, f'''#include "kse"

void main()
{{
    object oPC = GetPCSpeaker();
    int nAfter = KSE_SetCredits(oPC, GetGold(oPC) - {ABILITY_PRICE});
    {grant_line}
    int nCount = GetLocalNumber(oPC, {ABILITY_COUNT_IDX}) + 1;
    SetLocalNumber(oPC, {ABILITY_COUNT_IDX}, nCount);
    KSE_Diag(200, "AP|APPLIED|vendor_train_ability|ability={const}|creditsAfter=" + IntToString(nAfter) + "|count=" + IntToString(nCount));
}}
''')
    for feat_id, _text, _is_signature in FEATS:
        resref = f"ap_vfg{feat_id}"
        ok &= write_and_compile(resref, f'''#include "kse"

void main()
{{
    object oPC = GetPCSpeaker();
    int nAfter = KSE_SetCredits(oPC, GetGold(oPC) - {FEAT_PRICE});
    KSE_GrantFeatArrayA({feat_id}, oPC);
    KSE_Diag(200, "AP|APPLIED|vendor_train_feat|feat={feat_id}|creditsAfter=" + IntToString(nAfter));
}}
''')
    for power_id, _text in POWERS:
        resref = f"ap_vpg{power_id}"
        ok &= write_and_compile(resref, f'''#include "kse"

void main()
{{
    object oPC = GetPCSpeaker();
    int nAfter = KSE_SetCredits(oPC, GetGold(oPC) - {POWER_PRICE});
    KSE_SetCreatureField(oPC, KSE_FIELD_ADD_FORCE_POWER(), {power_id});
    KSE_Diag(200, "AP|APPLIED|vendor_train_power|power={power_id}|creditsAfter=" + IntToString(nAfter));
}}
''')

    # Character Reset: resets current level (both class slots if
    # multiclassed) to 1, strips every known Feat and Force Power
    # completely (not half, unlike the Trap version), hard-resets all 6
    # abilities to RESET_ABILITY_FLOOR, and zeroes every skill rank. XP is
    # deliberately left untouched -- the point is letting the player
    # re-level and reassign those choices naturally, not punish them by
    # also losing XP progress. Feat/Power stripping loops over every real
    # feat.2da/spells.2da row (125/144 rows respectively) rather than
    # tracking a known-list ourselves -- GetHasFeat/GetHasSpell are the
    # same authoritative checks every other picker here already dedups
    # against.
    skill_zero_lines = "\n    ".join(
        f"KSE_AdjustCreatureSkills(oPC, {const}, -GetSkillRank({const}, oPC));"
        for _suffix, _text, const in SKILLS
    )
    is_protected_branches = "\n    ".join(
        f'if (nClass == {const}) {{ return ({" || ".join(f"nFeat == {fid}" for fid in feat_ids)}); }}'
        for const, feat_ids in CLASS_AUTO_GRANTED_FEATS.items()
    )
    ok &= write_and_compile("ap_vs_reset", f'''#include "kse"

// See CLASS_AUTO_GRANTED_FEATS's own comment (generate_ap_vendor.py) --
// these are the per-class ONE-TIME level-1 auto-grants that never come
// back on an ordinary relevel, so Character Reset must never strip them.
int IsFeatProtected(int nClass, int nFeat)
{{
    {is_protected_branches}
    return FALSE;
}}

void main()
{{
    object oPC = GetPCSpeaker();
    int nAfter = KSE_SetCredits(oPC, GetGold(oPC) - {RESET_PRICE});

    int nClass0 = GetClassByPosition(0, oPC);
    int nClass1 = GetClassByPosition(1, oPC);

    KSE_SetCreatureField(oPC, KSE_FIELD_CLASS0_LEVEL(), 1);
    if (nClass1 != CLASS_TYPE_INVALID)
    {{
        KSE_SetCreatureField(oPC, KSE_FIELD_CLASS1_LEVEL(), 1);
    }}

    int i;
    for (i = 0; i < 125; i++)
    {{
        if (GetHasFeat(i, oPC) && !IsFeatProtected(nClass0, i) && !IsFeatProtected(nClass1, i))
        {{
            KSE_RemoveFeatArrayA(i, oPC);
        }}
    }}
    for (i = 0; i < 144; i++)
    {{
        if (GetHasSpell(i, oPC)) {{ KSE_SetCreatureField(oPC, KSE_FIELD_REMOVE_FORCE_POWER(), i); }}
    }}

    KSE_SetCreatureField(oPC, KSE_FIELD_SET_STR_BASE(), {RESET_ABILITY_FLOOR});
    KSE_SetCreatureField(oPC, KSE_FIELD_SET_DEX_BASE(), {RESET_ABILITY_FLOOR});
    KSE_SetCreatureField(oPC, KSE_FIELD_SET_CON_BASE(), {RESET_ABILITY_FLOOR});
    KSE_SetCreatureField(oPC, KSE_FIELD_SET_INT_BASE(), {RESET_ABILITY_FLOOR});
    KSE_SetCreatureField(oPC, KSE_FIELD_SET_WIS_BASE(), {RESET_ABILITY_FLOOR});
    KSE_SetCreatureField(oPC, KSE_FIELD_SET_CHA_BASE(), {RESET_ABILITY_FLOOR});

    {skill_zero_lines}

    // Also refunds the Train Ability/Train Skill purchase-count caps --
    // Reset already wipes the abilities/skills those purchases raised, so
    // leaving the old counts in place would leave the player permanently
    // short of their full 5 uses of each with nothing to show for the
    // ones already spent.
    SetLocalNumber(oPC, {ABILITY_COUNT_IDX}, 0);
    SetLocalNumber(oPC, {SKILL_COUNT_IDX}, 0);

    int nCount = GetLocalNumber(oPC, {RESET_COUNT_IDX}) + 1;
    SetLocalNumber(oPC, {RESET_COUNT_IDX}, nCount);
    KSE_Diag(200, "AP|APPLIED|vendor_character_reset|creditsAfter=" + IntToString(nAfter) + "|count=" + IntToString(nCount));
}}
''')

    # Alignment Change -- real native AdjustAlignment(oSubject, nAlignment,
    # nShift), not KSE_SetCreatureField (unlike ability/skill training,
    # there's no engine limitation here forcing a raw-offset write --
    # AdjustAlignment is a real, standard NWScript native, same one every
    # vanilla dialogue alignment shift in the base game already uses).
    ok &= write_and_compile("ap_val_steal", f'''#include "kse"

void main()
{{
    object oPC = GetPCSpeaker();
    int nAfter = KSE_SetCredits(oPC, GetGold(oPC) + {ALIGN_STEAL_GAIN});
    AdjustAlignment(oPC, ALIGNMENT_DARK_SIDE, {ALIGN_SHIFT_AMOUNT});
    int nCount = GetLocalNumber(oPC, {ALIGNMENT_COUNT_IDX}) + 1;
    SetLocalNumber(oPC, {ALIGNMENT_COUNT_IDX}, nCount);
    KSE_Diag(200, "AP|APPLIED|vendor_align_steal|creditsAfter=" + IntToString(nAfter) + "|count=" + IntToString(nCount));
}}
''')
    ok &= write_and_compile("ap_val_donate", f'''#include "kse"

void main()
{{
    object oPC = GetPCSpeaker();
    int nAfter = KSE_SetCredits(oPC, GetGold(oPC) - {ALIGN_DONATE_PRICE});
    AdjustAlignment(oPC, ALIGNMENT_LIGHT_SIDE, {ALIGN_SHIFT_AMOUNT});
    int nCount = GetLocalNumber(oPC, {ALIGNMENT_COUNT_IDX}) + 1;
    SetLocalNumber(oPC, {ALIGNMENT_COUNT_IDX}, nCount);
    KSE_Diag(200, "AP|APPLIED|vendor_align_donate|creditsAfter=" + IntToString(nAfter) + "|count=" + IntToString(nCount));
}}
''')

    return ok


def new_entry(text):
    e = DLGEntry()
    e.text = LocalizedString.from_english(text)
    e.plot_index = -1
    e.speaker = "ap_vendor_npc"
    return e


def new_reply(text):
    r = DLGReply()
    r.text = LocalizedString.from_english(text)
    r.plot_index = -1
    return r


def build_dlg():
    dlg = DLG()

    entry_greet = new_entry(
        "Welcome to the Archipelago Vendor. What can I help you with today?"
    )
    entry_not_enough = new_entry("You don't seem to have enough credits for that.")
    entry_skill_picker = new_entry(f"Which skill? {SKILL_PRICE} credits each, up to {PURCHASE_CAP} total.")
    entry_ability_picker = new_entry(f"Which ability? {ABILITY_PRICE} credits each, up to {PURCHASE_CAP} total.")

    # KOTOR dialogue graphs must strictly alternate Entry -> Reply -> Entry
    # -- an Entry can never link directly to another Entry (confirmed via
    # a real pykotor ValueError when first tried). A shared blank-text
    # reply auto-advances with no visible player choice (the same real
    # vanilla technique used to chain multi-line NPC monologues), reused
    # here as the loop-back-to-greeting target from every outcome node.
    reply_continue = new_reply("")
    reply_continue.links.append(DLGLink(entry_greet))
    entry_not_enough.links.append(DLGLink(reply_continue))

    reply_skill = new_reply(f"Train Skill -- {SKILL_PRICE} credits (up to {PURCHASE_CAP} total)")
    reply_skill.links.append(DLGLink(entry_skill_picker))
    reply_skill_link = DLGLink(reply_skill)
    reply_skill_link.active1 = ResRef("ap_vsk_cap")

    reply_ability = new_reply(f"Train Ability -- {ABILITY_PRICE} credits (up to {PURCHASE_CAP} total)")
    reply_ability.links.append(DLGLink(entry_ability_picker))
    reply_ability_link = DLGLink(reply_ability)
    reply_ability_link.active1 = ResRef("ap_vab_cap")

    entry_feat_picker = new_entry(f"Which feat? {FEAT_PRICE} credits each.")
    entry_power_picker = new_entry(f"Which power? {POWER_PRICE} credits each.")

    # No purchase-count cap for Feat/Power (unlike Skill/Ability) -- each
    # specific feat/power can only ever be bought once, enforced per-item
    # via GetHasFeat/GetHasSpell dedup on each picker reply below, not a
    # counter. Train Feat itself is always visible; Train Force Power is
    # gated on the PC having real Force levels (see ap_vpwr_jedi).
    reply_feat = new_reply(f"Train Feat -- {FEAT_PRICE} credits each")
    reply_feat.links.append(DLGLink(entry_feat_picker))

    # RE-ENABLED 2026-09-20 -- unlinked 2026-09-19 after confirming via the
    # actual save file that a granted power never reached the persisted,
    # authoritative known-spells list ("do not re-add without a real
    # extender-level fix"). That fix now exists: KseForcePowerOp's ADD path
    # calls the engine's own real AddKnownSpell instead of a raw array poke,
    # AND resolves which class slot (0 or 1) actually holds the creature's
    # Jedi class live on every call instead of assuming a fixed slot (see
    # offsets.h's KSE_ADD_KNOWN_SPELL_RVA / KSE_STATS_CATEGORY_TABLE_OFF
    # comments) -- the second bug is what was actually hiding this menu
    # entirely for a character converted through this project's own class-
    # change arms (Jedi in slot 0), independent of the persistence question
    # this link was originally removed for. Re-linked to test both fixes
    # together; if persistence still fails, unlink again with a fresh note
    # explaining what was actually tried.
    reply_power = new_reply(f"Train Force Power -- {POWER_PRICE} credits each")
    reply_power.links.append(DLGLink(entry_power_picker))
    reply_power_link = DLGLink(reply_power)
    reply_power_link.active1 = ResRef("ap_vpwr_jedi")

    reply_exit = new_reply("Nevermind.")

    entry_greet.links.append(reply_skill_link)
    entry_greet.links.append(reply_ability_link)
    entry_greet.links.append(DLGLink(reply_feat))
    entry_greet.links.append(reply_power_link)

    for suffix, text, _const in SKILLS:
        picker_reply = new_reply(text)
        success_entry = new_entry("Transaction completed. Your training is done.")
        success_entry.script1 = ResRef(f"ap_vs_{suffix}")

        link_yes = DLGLink(success_entry)
        link_yes.active1 = ResRef("ap_vg1000y")
        link_no = DLGLink(entry_not_enough)
        link_no.active1 = ResRef("ap_vg1000n")
        picker_reply.links.append(link_yes)
        picker_reply.links.append(link_no)

        entry_skill_picker.links.append(DLGLink(picker_reply))

    for suffix, text, _const in ABILITIES:
        picker_reply = new_reply(text)
        success_entry = new_entry("Transaction completed. Your training is done.")
        success_entry.script1 = ResRef(f"ap_va_{suffix}")

        link_yes = DLGLink(success_entry)
        link_yes.active1 = ResRef("ap_vg4000y")
        link_no = DLGLink(entry_not_enough)
        link_no.active1 = ResRef("ap_vg4000n")
        picker_reply.links.append(link_yes)
        picker_reply.links.append(link_no)

        entry_ability_picker.links.append(DLGLink(picker_reply))

    for feat_id, text, _is_signature in FEATS:
        picker_reply = new_reply(text)
        picker_link = DLGLink(picker_reply)
        picker_link.active1 = ResRef(f"ap_vfck{feat_id}")

        success_entry = new_entry("Transaction completed. Your training is done.")
        success_entry.script1 = ResRef(f"ap_vfg{feat_id}")

        link_yes = DLGLink(success_entry)
        link_yes.active1 = ResRef("ap_vg3000y")
        link_no = DLGLink(entry_not_enough)
        link_no.active1 = ResRef("ap_vg3000n")
        picker_reply.links.append(link_yes)
        picker_reply.links.append(link_no)

        entry_feat_picker.links.append(picker_link)

    for power_id, text in POWERS:
        picker_reply = new_reply(text)
        picker_link = DLGLink(picker_reply)
        picker_link.active1 = ResRef(f"ap_vpck{power_id}")

        success_entry = new_entry("Transaction completed. Your training is done.")
        success_entry.script1 = ResRef(f"ap_vpg{power_id}")

        link_yes = DLGLink(success_entry)
        link_yes.active1 = ResRef("ap_vg3000y")
        link_no = DLGLink(entry_not_enough)
        link_no.active1 = ResRef("ap_vg3000n")
        picker_reply.links.append(link_yes)
        picker_reply.links.append(link_no)

        entry_power_picker.links.append(picker_link)

    # Alignment Change -- 2-way picker, one shared cap (checked once at
    # the top-level menu entry, same shape as Train Skill/Train Ability
    # above). Steal is a pure gain (no credit gate needed, links straight
    # to its success entry); Donate costs credits, so it gets the same
    # yes/no credit-check split every other paid option uses.
    entry_align_picker = new_entry("Which option?")

    reply_align = new_reply(f"Alignment Change (up to {PURCHASE_CAP} total)")
    reply_align.links.append(DLGLink(entry_align_picker))
    reply_align_link = DLGLink(reply_align)
    reply_align_link.active1 = ResRef("ap_val_cap")

    picker_reply_steal = new_reply(
        f"Steal from the Republic (+{ALIGN_SHIFT_AMOUNT} Dark Side Points, gain {ALIGN_STEAL_GAIN} credits)"
    )
    success_entry_steal = new_entry("Transaction completed. Your training is done.")
    success_entry_steal.script1 = ResRef("ap_val_steal")
    picker_reply_steal.links.append(DLGLink(success_entry_steal))
    entry_align_picker.links.append(DLGLink(picker_reply_steal))

    picker_reply_donate = new_reply(
        f"Donate to Taris Refugees (+{ALIGN_SHIFT_AMOUNT} Light Side Points, cost {ALIGN_DONATE_PRICE} credits)"
    )
    success_entry_donate = new_entry("Transaction completed. Your training is done.")
    success_entry_donate.script1 = ResRef("ap_val_donate")
    link_yes = DLGLink(success_entry_donate)
    link_yes.active1 = ResRef("ap_vg5000y")
    link_no = DLGLink(entry_not_enough)
    link_no.active1 = ResRef("ap_vg5000n")
    picker_reply_donate.links.append(link_yes)
    picker_reply_donate.links.append(link_no)
    entry_align_picker.links.append(DLGLink(picker_reply_donate))

    entry_greet.links.append(reply_align_link)

    # Character Reset -- no sub-choice, so reply_reset's own links go
    # straight to the credit-check split, same shape as Skill/Ability but
    # skipping the "which one?" picker entry since there's nothing to pick.
    reply_reset = new_reply(f"Character Reset -- {RESET_PRICE} credits (up to {PURCHASE_CAP} total)")
    reply_reset_link = DLGLink(reply_reset)
    reply_reset_link.active1 = ResRef("ap_vrs_cap")

    success_entry_reset = new_entry("Transaction completed. Your training is done.")
    success_entry_reset.script1 = ResRef("ap_vs_reset")

    link_yes = DLGLink(success_entry_reset)
    link_yes.active1 = ResRef("ap_vg6000y")
    link_no = DLGLink(entry_not_enough)
    link_no.active1 = ResRef("ap_vg6000n")
    reply_reset.links.append(link_yes)
    reply_reset.links.append(link_no)

    entry_greet.links.append(reply_reset_link)

    # Class Change is not offered: this project's class-write mechanisms
    # (KSE_SetCreatureField's CLASS0_TYPE/CLASS1_TYPE) only ever overwrite
    # an EXISTING class slot's type value, never allocate a new one, so
    # there's no safe way yet to give a single-class PC a genuine second
    # class. See DEVELOPMENT_HISTORY.md for the full writeup and what a
    # real fix would need.

    # "Nevermind" appended last so it's always the final option on screen,
    # not wherever it happened to land based on definition order.
    entry_greet.links.append(DLGLink(reply_exit))

    dlg.starters.append(DLGLink(entry_greet))
    return dlg


def build_npc(installation):
    res = installation.resource("tar02_larrim", ResourceType.UTC)
    utc = construct_utc(read_gff(res.data))
    utc.resref = ResRef("ap_vendor_npc")
    utc.tag = "ap_vendor_npc"
    utc.first_name = LocalizedString.from_english("Archipelago Vendor")
    utc.last_name = LocalizedString.from_english("")
    utc.conversation = ResRef("ap_vendor_dlg")
    data = bytearray()
    write_gff(dismantle_utc(utc), data)
    return bytes(data)


def main():
    print("Building conditional scripts...")
    if not build_conditional_scripts():
        print("ABORT: one or more conditional scripts failed to compile.")
        sys.exit(1)

    print("Building success/grant scripts...")
    if not build_success_scripts():
        print("ABORT: one or more success scripts failed to compile.")
        sys.exit(1)

    print("Building dialogue tree...")
    dlg = build_dlg()
    gff = dismantle_dlg(dlg, Game.K1)
    dlg_path = os.path.join(SRC_DIR, "ap_vendor_dlg.dlg")
    data = bytearray()
    write_gff(gff, data)
    with open(dlg_path, "wb") as f:
        f.write(bytes(data))
    with open(os.path.join(OVERRIDE_DIR, "ap_vendor_dlg.dlg"), "wb") as f:
        f.write(bytes(data))
    print(f"  wrote + deployed ap_vendor_dlg.dlg ({len(data)} bytes)")

    print("Building vendor NPC template...")
    installation = Installation(GAME_DIR)
    utc_bytes = build_npc(installation)
    utc_path = os.path.join(SRC_DIR, "ap_vendor_npc.utc")
    with open(utc_path, "wb") as f:
        f.write(utc_bytes)
    with open(os.path.join(OVERRIDE_DIR, "ap_vendor_npc.utc"), "wb") as f:
        f.write(utc_bytes)
    print(f"  wrote + deployed ap_vendor_npc.utc ({len(utc_bytes)} bytes)")

    print()
    print(f"Vendor spot: {VENDOR_LOCATION} in ebo_m12aa.")
    print("Remember: this is a brand-new Override file set -- the game's")
    print("Override scan happens once at startup, so a full relaunch is")
    print("needed before any of this is visible in-game.")
    print()
    print("Next: wire the permanent spawn into ebo_m12aa's OnEnter trampoline")
    print("(generate_area_trampolines.py / generate_trampoline_batch.py),")
    print("then regenerate just that one area's trampoline.")


if __name__ == "__main__":
    main()
