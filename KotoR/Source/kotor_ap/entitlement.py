"""
entitlement.py -- pure computation of "what should this character currently
have," factored out of kotor_reconciliation.py so it's testable independent
of how the result gets dispatched. See FutureDesign.md's "Entitlement/
dispatch redesign" entry for the full incident writeup and confirmed scope.

No I/O, no sending, no mutation of the tracker it reads from -- everything
here takes a ReconciliationTracker (for its already-tracked config/state)
and returns a snapshot of what the AP-side authority says should be true
right now. Callers decide what to do about a mismatch.

xp/credits formulas are intentionally DUPLICATED here, not yet migrated
away from their existing call sites (kotor_reconciliation.py's _reconcile()
credits block and handle_event()'s _AREA_RE xp branch) -- those two are the
freshly-fixed/proven-sensitive halves of tonight's credit death-spiral and
companion-class-crash incidents, and cutting them over to read from this
module instead carries real regression risk for zero behavioral benefit
this pass (nothing new consumes xp/credits from here yet -- only pc_class/
companion_classes are wired into the new class-reconciliation branch). Fold
the old call sites over to compute_entitlement() once that's proven stable
live, instead of touching both at once.
"""
from __future__ import annotations

import typing
from dataclasses import dataclass, field

if typing.TYPE_CHECKING:
    from kotor_reconciliation import ReconciliationTracker

# CLASS_TYPE_* constants (nwscript.nss) -- matches generate_trampoline_
# batch.py's own _CLASS_NAME_TO_CONST (there as NWScript identifier
# strings for codegen; here as the real int values CheckClasses()/
# CheckCompanionClasses() report over the wire).
CLASS_NAME_TO_CONST: typing.Dict[str, int] = {
    "soldier": 0,
    "scout": 1,
    "scoundrel": 2,
    "guardian": 3,
    "consular": 4,
    "sentinel": 5,
}

# CLASS_TYPE_* constant -> the arm that sets a PC to that class. Covers all
# 6 real one-shot class-switch items (Options.py's StartingClass=
# random_class roll for the first 3, any seed's Jedi-conversion items for
# the last 3) -- see generate_trampoline_batch.py's APPLIES table, ids
# 13/14/26/34/35/36.
PC_CLASS_CONST_TO_ARM: typing.Dict[int, str] = {
    0: "pc_class_soldier",
    1: "pc_class_scout",
    2: "pc_class_scoundrel",
    3: "class_guardian",
    4: "class_consular",
    5: "class_sentinel",
}

# The 4 "universal" Jedi feats plus each class's own unique Force-power
# feat -- granted alongside every Jedi class-conversion, PC or companion.
# Companions get this exact bundle via generate_trampoline_batch.py's
# build_companion_class_block(), hardcoded as _JEDI_FEATS/_JEDI_UNIQUE_
# POWER_FEAT and fired via DelayCommand(1.0, ...) (needed for engine
# settling) right after the class field write. The PC's own class_
# guardian/consular/sentinel arms grant the identical ids via a different
# mechanism (CLASS_BASE_FEATS' full old-class/new-class delta), but the
# resulting set is the same. Real incident this exists to catch: a
# DelayCommand grant lost to a crash in that 1s window leaves the
# character permanently missing these feats -- the class field itself
# already reads correct, so nothing else would ever notice or retry it.
# Duplicated here rather than imported from generate_trampoline_batch.py
# (a dev-time codegen script, not meant to be a runtime dependency), same
# reasoning as CLASS_NAME_TO_CONST/HEAVY_ARMS -- keep in sync with that
# file's _JEDI_FEATS/_JEDI_UNIQUE_POWER_FEAT/CLASS_BASE_FEATS by hand.
_JEDI_UNIVERSAL_FEATS = {55, 43, 116, 107}  # Jedi Defense, Lightsaber Proficiency, Force Sensitivity, Jedi Sense
JEDI_CLASS_FEATS: typing.Dict[int, typing.Set[int]] = {
    3: _JEDI_UNIVERSAL_FEATS | {101},  # CLASS_TYPE_JEDIGUARDIAN + Force Jump
    4: _JEDI_UNIVERSAL_FEATS | {88},   # CLASS_TYPE_JEDICONSULAR + Force Focus
    5: _JEDI_UNIVERSAL_FEATS | {98},   # CLASS_TYPE_JEDISENTINEL + Force Immunity: Fear
}

# Arms that do AddMultiClass / ShowLevelUpGUI / AddPartyMember / CreateObject
# -- batching several of these together (even all first-time applications,
# no repeats involved) crashes the game. These get serialized client-side,
# one in flight at a time (KotorClient.py's _queue_heavy/_process_heavy_
# queue), instead of firing immediately like everything else. Deliberately
# NOT everything: skills/abilities/force_death don't touch multiclassing,
# the level-up GUI, or party membership, and have shown no crash risk even
# in much larger batches.
#
# Single canonical definition -- moved here (was KotorClient.py-only) so
# kotor_reconciliation.py can classify a correction's arm_name without a
# second, parallel copy of this set (which is exactly how it briefly
# existed as _HEAVY_CORRECTION_ARMS before this consolidation:
# kotor_reconciliation.py can't import from KotorClient.py, since the
# dependency runs the other way, so entitlement.py -- pure data, no I/O,
# already imported by both -- is the one place both sides can read this
# from).
HEAVY_ARMS: typing.Set[str] = {
    "class_guardian", "class_consular", "class_sentinel",
    "companion_bastila", "companion_canderous", "companion_carth",
    "companion_hk47", "companion_jolee", "companion_juhani",
    "companion_mission", "companion_t3m4", "companion_zaalbar",
    # StartingClass=random_class's base-class roll -- a KSE_SetCreatureField
    # write on the PC, same heavy classification as companion_class's
    # write, same reasoning (see _queue_heavy).
    "pc_class_soldier", "pc_class_scout", "pc_class_scoundrel",
}


def is_heavy_arm(arm_name: str) -> bool:
    """True for any HEAVY_ARMS member, or a companion_class:<name>:<class>
    send -- the latter can't be a plain set entry (it's a colon-
    parameterized string, a different one per companion/class pair), so it
    needs its own prefix check. A companion_X recruit arm also starts with
    "companion_", so this one check covers both recruit arms and
    companion_class: sends -- deliberately not narrowed to just the
    "companion_class:" form."""
    return arm_name.startswith("companion_") or arm_name in HEAVY_ARMS


# The 8 ItemClassification.progression give_item: entries confirmed
# softlock-capable if silently lost (all 4 Star Maps are required to reach
# the Star Forge) -- see FutureDesign.md's "Entitlement/dispatch redesign"
# entry. Duplicated here rather than imported from worlds/kotor/Items.py
# (a world-generation-side module, not meant to be a runtime dependency of
# the client process), same reasoning as CLASS_NAME_TO_CONST/HEAVY_ARMS --
# keep in sync with that file's own PROGRESSION_ITEM_RESREFS by hand.
PROGRESSION_ITEM_RESREFS: typing.Dict[str, str] = {
    "sith_armor": "ptar_sitharmor",
    "sith_papers": "ptar_sithpapers",
    "shield_codes": "ptar_shieldcodes",
    "enviro_suit": "man28_envirosuit",
    "starmap_tatooine": "tat_starpad",
    "starmap_kashyyyk": "kas_starpad",
    "starmap_manaan": "man_starpad",
    "starmap_korriban": "kor_starpad",
}


@dataclass
class EntitlementSnapshot:
    pc_class: int  # CLASS_TYPE_* constant, or -1 if PC class isn't AP-managed this seed (no class item received yet)
    companion_classes: typing.Dict[str, int] = field(default_factory=dict)  # npc_key -> CLASS_TYPE_* constant, only for companions with a roll
    xp: int = 0
    credits: int = 0


def compute_entitlement(tracker: "ReconciliationTracker") -> EntitlementSnapshot:
    """Mirrors the exact formulas already live elsewhere -- see this
    module's docstring for why xp/credits are relocated here as a copy,
    not yet a cutover. pc_class/companion_classes ARE the real, only
    authority the new class-reconciliation branch reads."""
    if tracker.experience_mode == 0:  # off -- pure vanilla, nothing to enforce
        xp = tracker.current_scalar.get("xp", 0)
    elif tracker.experience_mode == 2:  # ap_gated
        xp = tracker.expected_scalar.get("xp", 0)
    else:  # ap_limited
        xp = tracker.checked_location_count * tracker.experience_limiter

    if tracker.credit_mode == 0:  # off
        credits = tracker.current_scalar.get("credits", 0)
    elif tracker.credit_mode == 2:  # ap_gated
        credits = tracker.expected_scalar.get("credits", 0)
    else:  # ap_limited
        credits = tracker.checked_location_count * tracker.credit_limiter

    # companion_class_rolls (CompanionClass=no_jedi/randomize_all) is a
    # fixed roll set once from slot_data at Connect -- unlike pc_class,
    # it's never delivery-order-dependent, so no tracking is needed beyond
    # what's already there. Empty for off/jedi_companion, matching
    # _maybe_queue_companion_class's own no-op reasoning for those modes.
    companion_classes = {
        npc_key: CLASS_NAME_TO_CONST[class_name]
        for npc_key, class_name in tracker.companion_class_rolls.items()
        if class_name in CLASS_NAME_TO_CONST
    }

    return EntitlementSnapshot(
        pc_class=tracker.expected_pc_class,
        companion_classes=companion_classes,
        xp=xp,
        credits=credits,
    )
