"""
kotor_reconciliation.py -- the client-authoritative half of the design:
the game reports its honest current state every poll (XP, credits, skill
ranks, companion availability -- via ap_poll_shared, already flowing
through the extender bridge as EVENT: lines), and the CLIENT decides
whether that matches what the player should have based on AP items
received so far, re-sending grants to close any deficit.

Scope (deliberately not everything): only arm types whose effect is a
plain, repeatable ADDITIVE increment are auto-corrected here -- the 8
skill ranks (each grant is a fixed +N, safe to re-fire to close an exact
gap) and the two companion adds (idempotent: re-adding an already-present
companion is a safe no-op via IsAvailableCreature/AddPartyMember). Class
switches and ability increases are NOT auto-corrected -- those are closer
to one-shot state transitions than repeatable increments (unlike skills,
which have no AP item cap and are meant to be received many times), and
blindly re-firing them on a mismatch risks doing something the player
didn't ask for (e.g. re-running AddMultiClass) rather than fixing a real
deficit.

Deficit-only for skills/companions specifically (a deliberate design
decision): if the game reports MORE than
expected there, that's left alone -- no correction fires, since those
arms are fixed-increment grants only, not "set to exact value."

XP and credits are DIFFERENT -- both are full bidirectional clamps under
their respective non-off modes (experience_mode/credit_mode), correcting
vanilla gains DOWN as well as topping deficits UP, via a true absolute
setter (SetXP / KSE_SetCredits) rather than a fixed-increment arm. XP
clamps once per real area transition (see handle_event()'s _AREA_RE
branch); credits clamp every poll cycle instead, in _reconcile() below,
since spending is granular enough (shop purchases) that waiting for a
transition would be too coarse. Credits additionally detects real spends
(a decrease) and treats them as legitimate rather than fighting them --
see _reconcile()'s purchase-detection comment.
"""
from __future__ import annotations

import logging
import re
import time
import typing

from entitlement import (EntitlementSnapshot, PC_CLASS_CONST_TO_ARM, compute_entitlement, is_heavy_arm,
                          JEDI_CLASS_FEATS, PROGRESSION_ITEM_RESREFS)

logger = logging.getLogger("Client")

# Real exptable.2da thresholds (confirmed via pykotor against the live
# install) -- level N's XP requirement, index 0 unused (level 1 = 0 XP).
# Used only by _level_for_xp() below, for the delevel reconciler's
# SetXP-gap detection.
_EXPTABLE = [
    0, 0, 1000, 3000, 6000, 10000, 15000, 21000, 28000, 36000, 45000,
    55000, 66000, 78000, 91000, 105000, 120000, 136000, 153000, 171000, 190000,
]


def _level_for_xp(xp: int) -> int:
    """Real character level for a given total XP, per exptable.2da.
    Clamps to [1, 20] -- KOTOR's own level cap, matching max_level's own
    GetHitDice()-based check elsewhere in this project."""
    level = 1
    for lvl, threshold in enumerate(_EXPTABLE):
        if lvl == 0:
            continue
        if xp >= threshold:
            level = lvl
        else:
            break
    return level

# arm_name -> reconciliation rule. Only additive, safely-repeatable arms are
# listed -- see module docstring for what's deliberately excluded and why.
# "xp" and "credits" have no fixed amount here -- see note_item_received(),
# they use the seed's configured experience_item/credit_item instead (only
# meaningful under their ap_gated mode -- ap_limited derives its expected
# total from the player's own checked-location count instead). XP's
# correction is handled separately (on_area_transition(), not the regular
# per-poll _reconcile()) since it clamps down as well as up; credits'
# clamp (see CreditMode's docstring) runs in the regular
# per-poll _reconcile() instead, since spending is granular enough that
# waiting for a transition would be too coarse.
ARM_EFFECT: typing.Dict[str, tuple] = {
    "computer_use": ("skill", "computeruse", 2),
    "demolitions": ("skill", "demolitions", 2),
    "stealth": ("skill", "stealth", 2),
    "awareness": ("skill", "awareness", 2),
    "persuade": ("skill", "persuade", 2),
    "repair": ("skill", "repair", 2),
    "security": ("skill", "security", 2),
    "treat_injury": ("skill", "treatinjury", 2),
    "companion_bastila": ("companion", 0),
    "companion_canderous": ("companion", 1),
    "companion_carth": ("companion", 2),
    # companion_hk47 (3) and companion_zaalbar (8) -- previously excluded
    # here over an unverified concern (HK-47 assumed to be a multi-step
    # purchase sequence, Zaalbar assumed to need Mission already in the
    # party first). Confirmed via direct read of generate_trampoline_
    # batch.py's own arms (20 and 25 respectively) that BOTH are the exact
    # same plain IsAvailableCreature-guarded AddAvailableNPCByTemplate +
    # CreateObject + AddPartyMember shape every other companion here
    # already uses -- no purchase sequence, no Mission-presence check.
    # Re-added now that the code itself shows nothing distinguishes them.
    "companion_hk47": ("companion", 3),
    "companion_jolee": ("companion", 4),
    "companion_juhani": ("companion", 5),
    "companion_mission": ("companion", 6),
    "companion_t3m4": ("companion", 7),
    "companion_zaalbar": ("companion", 8),
    # con IS tracked (real AP item "Ability: Constitution Increase")
    # despite no reduce_con trap existing -- see _ability_baseline's own
    # comment. cha has no AP item at all, so it's absent here entirely.
    "ability_strength": ("ability", "str", 1),
    "ability_dexterity": ("ability", "dex", 1),
    "ability_constitution": ("ability", "con", 1),
    "ability_intelligence": ("ability", "int", 1),
    "ability_wisdom": ("ability", "wis", 1),
}
_ABILITY_KEYS = ["str", "dex", "con", "int", "wis"]
# reduce_str/dex/int/wis/cha trap -> current_abilities/ARM_EFFECT's own
# key spelling (cha excluded -- see _ability_baseline's own comment).
_TRAP_ABILITY_TO_KEY = {"reduce_str": "str", "reduce_dex": "dex", "reduce_int": "int", "reduce_wis": "wis"}

_SKILLREPORT_RE = re.compile(
    r"computeruse=(\d+)\|demolitions=(\d+)\|stealth=(\d+)\|awareness=(\d+)\|"
    r"persuade=(\d+)\|repair=(\d+)\|security=(\d+)\|treatinjury=(\d+)"
)
_SKILL_FIELDS = ["computeruse", "demolitions", "stealth", "awareness", "persuade", "repair", "security", "treatinjury"]
# The eight TRUE skill ranks (KSE_FIELD_REPORT_SKILL_RANKS, logged by the
# extender just before each SKILLREPORT). SKILLREPORT above is GetSkillRank --
# rank + ability modifier + effects -- so it moves whenever abilities, gear or
# debuffs change; skill reconciliation runs on these true ranks instead.
# Signed because the engine stores ranks in a signed byte.
_SKILLBASE_RE = re.compile(
    r"AP\|SKILLBASEREPORT\|computeruse=(-?\d+)\|demolitions=(-?\d+)\|stealth=(-?\d+)\|awareness=(-?\d+)\|"
    r"persuade=(-?\d+)\|repair=(-?\d+)\|security=(-?\d+)\|treatinjury=(-?\d+)"
)

# Raw events are full kse.log lines (timestamp + `KSE DIAG: code=N msg="..."`
# wrapper, with a trailing close-quote after the value) -- these MUST use a
# digit-bounded regex, not tail string-slicing (event.split(...)[1] would
# capture the trailing '"' and make int() raise, silently killing the
# extender-bridge asyncio task with no visible error -- this is exactly what
# was happening every run, right after the first COMPANION event).
_CREDITS_RE = re.compile(r"AP\|CREDITSREPORT\|current=(\d+)")
_XP_RE = re.compile(r"AP\|XPREPORT\|current=(\d+)")
_COMPANION_RE = re.compile(r"AP\|CHECK\|COMPANION\|(\d+)")
_AREA_RE = re.compile(r"AP\|CHECK\|AREA\|(\d+)")
_DEATH_RE = re.compile(r"AP\|CHECK\|DEATH")
_CLASSREPORT_RE = re.compile(
    r"AP\|CLASSREPORT\|guardian=(\d+)\|consular=(\d+)\|sentinel=(\d+)"
    r"(?:\|baseclass=(-?\d+)\|baselevel=(\d+))?"
)
# LEVELREPORT is GetHitDice(oPC) -- real TOTAL character level, already
# correctly summed across a multiclass split by the engine itself (unlike
# baselevel/guardian/consular/sentinel above, which would double-count for
# a single-class Jedi PC under the raw-overwrite rewrite, since baseclass
# IS one of the Jedi types in that case). Used by the delevel reconciler
# -- see on_area_transition()'s xp-clamp branch.
# Companion class self-healing (see DEVELOPMENT_HISTORY.md section 13) --
# CheckCompanionClasses() (generate_poll_shared.py)
# reports the 7 non-droid companions' position-1 class every poll, -1 for
# a companion not currently recruited (IsNPCPartyMember false) rather than
# a real CLASS_TYPE_* value (including CLASS_TYPE_SOLDIER's own 0).
_COMPANION_CLASS_KEYS = ["bastila", "canderous", "carth", "jolee", "juhani", "mission", "zaalbar"]
_COMPANION_CLASSREPORT_RE = re.compile(
    r"AP\|COMPANIONCLASSREPORT\|bastila=(-?\d+)\|canderous=(-?\d+)\|carth=(-?\d+)\|"
    r"jolee=(-?\d+)\|juhani=(-?\d+)\|mission=(-?\d+)\|zaalbar=(-?\d+)"
)
# Roster cleanup (CheckRoster(), generate_poll_shared.py): which of the 9
# companions are AVAILABLE (on the roster, in the active party or not), plus
# busy=1 while a scripted scene has someone staged on purpose (the Leviathan
# sequence, a conversation, the Zaalbar/Jolee temporary-companion scenes).
# Anyone available whose entitlement marker (CREWREPORT) is not 10 is a leak and is purged after
# several settled reports across two area entries -- see ReconciliationTracker._roster_extras. Keys in the order the poll reports them; the index is the
# NPC_* slot (0 Bastila, 1 Canderous, 2 Carth, 3 HK-47, 4 Jolee, 5 Juhani,
# 6 Mission, 7 T3-M4, 8 Zaalbar).
_ROSTER_KEYS = ["bastila", "canderous", "carth", "hk47", "jolee", "juhani", "mission", "t3m4", "zaalbar"]
_ROSTER_NPC_IDX = {"bastila": 0, "canderous": 1, "carth": 2, "hk47": 3, "jolee": 4,
                   "juhani": 5, "mission": 6, "t3m4": 7, "zaalbar": 8}
_ROSTER_RE = re.compile(
    r"AP\|ROSTERREPORT\|busy=(\d)\|bastila=(\d)\|canderous=(\d)\|carth=(\d)\|hk47=(\d)\|"
    r"jolee=(\d)\|juhani=(\d)\|mission=(\d)\|t3m4=(\d)\|zaalbar=(\d)\|lev=(-?\d+)"
    r"\|sf=(\d)\|fc=(-?\d+)\|bp=(\d)(?:\|md=(\d))?(?:\|sel=([01]{9}))?(?:\|bz=(\d+))?(?:\|km=(\d+))?"
)
# Entitlement markers (CheckCrewMarkers(), generate_poll_shared.py): per companion the journal quest ap_ent_<key>, written by the
# companion grant arm (10 = entitled) and by the Remove a Companion trap (20 = trapped off for good). They live in the save, so
# they are the only entitlement the reconciler consults for a purge, the Star Forge pass and the selectability fix. Order = _ROSTER_KEYS.
_CREW_RE = re.compile(
    r"AP\|CREWREPORT\|bastila=(\d+)\|canderous=(\d+)\|carth=(\d+)\|hk47=(\d+)\|"
    r"jolee=(\d+)\|juhani=(\d+)\|mission=(\d+)\|t3m4=(\d+)\|zaalbar=(\d+)"
)
_CREW_ENTITLED = 10
# Most times the reconciler sends the same missing feat set for one character before it stops trying.
_FEATS_MAX_SENDS = 3
_CREW_TRAPPED = 20
# Leak purge: a companion on the roster whose marker is not 10 (never granted, or trapped off) is purged only after it has been seen
# across this many area entries (and a few settled reports) with nothing busy. Not applied once the Unknown World trip has begun
# (the story stage km=, K_KOTOR_MASTER, is 40 or more): the Unknown World finale stages the whole crew on purpose and the Star Forge
# pass cleans up after it.
_LEAK_AREA_ENTRIES = 2
_LEAK_STORY_STAGE_BLOCK = 40
# A busy source other than the Leviathan sequence, a conversation or an Unknown World module (bits 2, 4, 8, 16 of bz=) that stays set
# this long is almost certainly stuck (a dropped revert); it is logged, nothing is changed.
_BUSY_STUCK_SECONDS = 600
_BUSY_STUCK_BITS = {2: "PC boolean 78 (Jolee field scene)", 4: "forcefield Mission staging", 8: "Zaalbar Mission staging",
                    16: "Bastila+Carth party gate"}
# Star Forge pass: companions that nothing in the Star Forge needs (its Carth and
# Bastila scenes use stand-in creatures with their own tags), purged on arrival if
# the player is not entitled to them. Bastila is handled by path, see
# ReconciliationTracker._starforge_actions.
_STARFORGE_PURGE_KEYS = ["carth", "canderous", "hk47", "jolee", "juhani", "mission", "t3m4", "zaalbar"]
# lev_captured's final journal entry (global.jrl): the Leviathan has been
# escaped (reported as lev= and kept as roster_leviathan_done; the cleanup no longer depends on it).
_LEVIATHAN_DONE_ENTRY = 99
# Consecutive non-busy reports (5 s apart) an unentitled companion must be
# seen in before a purge is sent, and how long after the first report of a
# connection nothing is purged (the received-item replay and the delivery
# log must have had time to say who is entitled).
_ROSTER_STABLE_REPORTS = 3
_ROSTER_WARMUP_SECONDS = 45
# Same shape as _COMPANION_CLASSREPORT_RE, for the feats poll
# (CheckCompanionFeats(), generate_poll_shared.py) -- each segment is
# either "NONE" (not currently recruited), empty (recruited, holds none of
# ADDITIONAL_FEATS_POOL), or a comma-joined list of held feat.2da ids, so a
# generic capture handles all three shapes uniformly. MUST exclude '"' too,
# not just '|' -- confirmed: the raw kse.log line wraps the whole
# message in msg="...", so the LAST group (zaalbar, nothing bounding it on
# the right) greedily swallowed that trailing '"' (e.g. "NONE" arrived as
# NONE", which then failed the plain == "NONE" check and crashed int() on
# the comma-split). Same class of bug this project's own _CREDITS_RE/
# _NAMEREPORT_RE comments already document for exactly this reason --
# missed it here since this is the only OTHER variable-length-string
# regex added this session.
_COMPANION_FEATSREPORT_RE = re.compile(
    r'AP\|COMPANIONFEATSREPORT\|bastila=([^|"]*)\|canderous=([^|"]*)\|carth=([^|"]*)\|'
    r'jolee=([^|"]*)\|juhani=([^|"]*)\|mission=([^|"]*)\|zaalbar=([^|"]*)'
)
# CheckProgressionItems() (generate_poll_shared.py) -- 0/1 possession flag
# per tracked resref, same key order as entitlement.py's
# PROGRESSION_ITEM_RESREFS. A digit is self-terminating against the "|"
# separator, unlike the free-form COMPANIONFEATSREPORT fields above, so no
# quote-exclusion trick is needed here.
_PROGRESSIONITEMSREPORT_RE = re.compile(
    r"AP\|PROGRESSIONITEMSREPORT" + "".join(rf"\|{_k}=(\d)" for _k in PROGRESSION_ITEM_RESREFS)
)
_RESREF_TO_PROGRESSION_KEY: typing.Dict[str, str] = {v: k for k, v in PROGRESSION_ITEM_RESREFS.items()}
# ap_vs_reset.nss/ap_val_steal.nss (generate_ap_vendor.py) -- vendor
# actions that happen OUTSIDE the normal AP delivery pipeline entirely
# (player-triggered dialogue, never routed through note_item_received),
# so the reconciler only ever learns about them from their own KSE_Diag
# lines, same as any other extender EVENT.
_VENDOR_CREDIT_GAIN_RE = re.compile(r"AP\|APPLIED\|vendor_align_steal\|creditsAfter=(\d+)")
_VENDOR_RESET_RE = re.compile(r"AP\|APPLIED\|vendor_character_reset\|")
# CheckAPTrackerStage() (generate_poll_shared.py) -- the player's current
# "Archipelago Tracker" journal stage. 0 legitimately means "not added
# yet" (stage 0 is a reserved sentinel, never a real stage -- see
# build_ap_tracker_quest.py's STAGES comment).
_APTRACKERREPORT_RE = re.compile(r"AP\|APTRACKERREPORT\|stage=(\d+)")
# Emitted by every covered area's trampoline wrapper (generate_
# trampoline_batch.py) in the SAME script execution, unconditionally
# before the armed-batch-apply block runs -- confirmed by reading that
# generator's own wrapper template, not assumed. Arrival of this line is
# therefore a reliable proxy for "a covered area just had its one chance
# to flush whatever was armed," independent of which specific area it was.
# Used to gate the staged-arm "assume lost, retry" decisions below on an
# actual opportunity to apply having passed, not on wall-clock time alone
# -- a correction stuck behind an area the player hasn't left yet (the
# Endar Spire prologue, pre-fix, is the confirmed real case) is NOT lost,
# it's correctly queued and waiting; only a qualifying area entry with the
# deficit still unresolved afterward is real evidence of loss.
_AREA_CHECK_RE = re.compile(r"AP\|CHECK\|AREA\|(\d+)")
# (threshold percentage, stage id) pairs, highest first, so _reconcile()
# can pick "the highest stage the percentage qualifies for" with a simple
# first-match walk. Stage id 1 ("run has begun") is deliberately keyed on
# threshold 0, not 1 -- it must fire the moment total_location_count/
# current_ap_tracker_stage are known, at 0% progress, not only once the
# player has found at least 1% of checks. The last entry always matches
# (every percentage is >= 0), so the deficit check in _reconcile() never
# needs its own separate "just starting" special case.
_AP_TRACKER_STAGES = [(100, 100), (80, 80), (60, 60), (40, 40), (20, 20), (0, 1)]
_LEVEL_RE = re.compile(r"AP\|LEVELREPORT\|(\d+)")
# Same reconciler fix -- needed to compute the proportionally-scaled
# Force value a delevel correction should carry.
_FORCE_RE = re.compile(r"AP\|FORCEREPORT\|current=(\d+)\|max=(\d+)")
# Free-form string field (not a digit run), so bounded by the trailing '"'
# the kse.log wrapper adds instead -- same reasoning as the digit-bounded
# regexes above, just a different terminator since this isn't numeric.
_NAMEREPORT_RE = re.compile(r'AP\|NAMEREPORT\|([^"]+)')

# Traps (see Options.py's Traps): 3 report types, read-only --
# unlike credits/xp/skills, nothing here is ever reconciliation-corrected
# (no expected_ counterpart, no clamp), these just give the trap-delivery
# decision logic in KotorClient.py a live snapshot of state to compute
# "half of X" from. ABILITYREPORT was already broadcast every poll but
# completely unparsed before this; FEATREPORT/POWERREPORT are new
# additions to ap_poll_shared.nss (see generate_poll_shared.py's
# CheckFeats/CheckForcePowers).
#
# No INVENTORY/_INVENTORY_RE/_parse_inventory_report/current_inventory
# here: ap_poll_shared's old CheckInventory() built one giant concatenated
# string across the whole backpack every 5s, which silently truncates
# past NWScript's ~512-byte string limit for a large enough inventory.
# Rather than chunk that report to dodge the limit, the Remove Half
# Inventory trap does its own on-demand inventory walk + native
# single-pass random selection entirely in NWScript at delivery time (see
# generate_trampoline_batch.py's build_trap_block, remove_half_inventory
# branch) -- Python needs no live inventory snapshot for this at all, and
# skipping the poll removes a full inventory walk + string build from
# every heartbeat tick.
_ABILITY_RE = re.compile(
    r"AP\|ABILITYREPORT\|str=(\d+)\|dex=(\d+)\|con=(\d+)\|int=(\d+)\|wis=(\d+)\|cha=(\d+)"
)
# The six TRUE base ability scores (KSE_FIELD_REPORT_ABILITY_BASES, logged by
# the extender right after each ABILITYREPORT). ABILITYREPORT above is the
# EFFECTIVE score -- base + item bonuses + temporary effects such as combat
# debuffs -- so on its own a debuff reads as a lost point. The ability
# reconciliation below only ever consults these when the effective score has
# dropped below the baseline, to tell a temporary effect from a real loss.
_ABILITYBASE_RE = re.compile(
    r"AP\|ABILITYBASEREPORT\|str=(\d+)\|dex=(\d+)\|con=(\d+)\|int=(\d+)\|wis=(\d+)\|cha=(\d+)"
)
_FEATREPORT_RE = re.compile(r"AP\|FEATREPORT\|([\d,]*)")
# The full held-feat list (CheckFeatsFull(), about once a minute). FEATREPORT above now carries only
# the feats the reconciler and the Additional Feats picker care about; the Remove Half Known Feats
# trap needs everything the character holds.
_FEATFULL_RE = re.compile(r"AP\|FEATFULL\|([\d,]*)")
_POWERREPORT_RE = re.compile(r"AP\|POWERREPORT\|([\d,]*)")
# Trap confirmations (generate_trampoline_batch.py's build_trap_block) --
# both are a legitimate, intentional DECREASE, so on a match the
# corresponding expected_*/_ability_baseline floor gets lowered to match
# instead of leaving the old higher expectation in place for the deficit
# loop below to "heal" back -- same "a real punishment is not exempt"
# reasoning as Character Reset.
_TRAP_REDUCE_SKILL_RE = re.compile(r"AP\|APPLIED\|trap\|type=reduce_skill\|skill=(\w+)\|before=(\d+)\|after=(\d+)")
_TRAP_REDUCE_ABILITY_RE = re.compile(
    r"AP\|APPLIED\|trap\|type=(reduce_str|reduce_dex|reduce_int|reduce_wis|reduce_cha)\|before=(\d+)\|after=(\d+)"
)
# The generic "set_credits" apply-value action's own confirmation --
# fires both for the reconciler's own regular credit-clamp corrections
# (a harmless no-op re-affirmation when it does) AND for the
# "remove_credits" trap, which reuses this exact action directly rather
# than going through build_trap_block at all (see KotorClient.py's own
# comment on why). Listening to this directly closes a real race: without
# it, the reconciler only learns about a credit change from the next 5s
# CREDITSREPORT poll and infers legitimacy from the delta, which could
# race against its own in-flight clamp correction landing on stale data.
_SET_CREDITS_APPLIED_RE = re.compile(r"AP\|APPLIED\|set_credits\|before=(\d+)\|after=(\d+)")

# arm_name -> current_classes key, for the has_class() pre-send check.
CLASS_ARM_TO_KEY = {
    "class_guardian": "guardian",
    "class_consular": "consular",
    "class_sentinel": "sentinel",
}

# arm_name -> CLASS_TYPE_* constant, for note_item_received()'s
# expected_pc_class tracking -- reverse of entitlement.py's
# PC_CLASS_CONST_TO_ARM.
_ARM_TO_PC_CLASS_CONST = {arm: const for const, arm in PC_CLASS_CONST_TO_ARM.items()}

# Skills-only staleness timeout for in-flight correction tracking (see
# ReconciliationTracker.__init__) -- if a skill's in-flight count has sat
# unresolved this long with zero observed progress, treat it as a lost
# request and allow a fresh retry rather than waiting forever. Scoped to
# skills only (not companions): companions are boolean/one-shot with lower
# compounding risk and are already covered by the simpler set-based
# in-flight tracking, no timeout needed there.
_SKILL_INFLIGHT_TIMEOUT_SECONDS = 300

# Credits' own in-flight staleness timeout: shorter than skills' because
# a credits correction is a single direct set_credits call, not a
# multi-step grant, so it should land within a poll cycle or two if it's
# going to land at all. See _reconcile()'s credits section for why this
# exists at all -- without in-flight tracking, a deficit that takes more
# than one 5-second poll to actually reflect (common, since the
# correction has to round-trip through the extender/orchestrator/game
# before the NEXT poll can see it) triggers a fresh identical
# "set_credits:X" send every single cycle for as long as the mismatch
# persists.
_CREDITS_INFLIGHT_TIMEOUT_SECONDS = 30

# Staged-arm corrections' own in-flight timeout -- NOT credits' 30s. Class
# (PC and companion) and feats corrections are both staged through
# area-transition-gated queues (class via _heavy_queue; feats via
# arm_orchestrator.py's apply_armed_set, confirmed append-semantics same as
# credits/class) the same way this session's real credit incident
# confirmed set_credits is (see _credit_baseline's own comment) -- the
# write can take a while to actually land, not just a poll cycle or two.
# Matches _SKILL_INFLIGHT_TIMEOUT_SECONDS's own reasoning instead: a class
# correction is dispatched via send_heavy (see is_heavy_arm), which only
# enqueues into _heavy_queue -- it doesn't itself call wait_staged(), so
# _is_awaiting_confirmation's staged_at check never actually reflects a
# reconciler-issued send (see its own docstring -- it's scoped to the
# NORMAL delivery pipeline's in-flight state, not this one) until
# _process_heavy_queue eventually reaches this entry and _do_deliver calls
# wait_staged() itself. Feats corrections (send_feats) never touch
# _heavy_queue at all (light, no batching risk), but share the exact same
# "the actual field write is staged, not instant" timing, so the same
# generous timeout applies.
# Without this separate tracking, an unresolved mismatch would re-send the
# identical correction every single ~5s poll for as long as it takes to
# land.
_STAGED_ARM_INFLIGHT_TIMEOUT_SECONDS = 300

# How long after a covered-area entry the staged arms are still considered to
# be flushing. The area's trampoline runs `AP|CHECK|AREA` and the poll BEFORE
# its batch applies, so the poll of that same run reports pre-batch values;
# judging "the arms had their chance" from the AREA line alone made the
# reconciler resend every staged grant in the same instant the batch was
# landing (a whole connect-time burst doubled). The next heartbeat poll, one
# 5 s tick later, reflects the landed batch.
_AREA_FLUSH_GRACE_SECONDS = 12

# is_heavy_arm (entitlement.py) classifies every correction arm name that
# must be routed through send_heavy (KotorClient.py's _queue_heavy)
# instead of send_apply directly -- imported rather than duplicated here,
# so HEAVY_ARMS has exactly one definition across the whole codebase. Safe
# to import: entitlement.py's only reference back to this module is
# TYPE_CHECKING-only, so there's no runtime circularity even though
# KotorClient.py also imports from this module.


class ReconciliationTracker:
    """Owns both halves: what the player SHOULD have (fed by ReceivedItems)
    and what the game currently reports having (fed by extender EVENT
    lines), and decides what corrective APPLY calls to send."""

    def __init__(
        self,
        send_apply: typing.Callable[[str], typing.Awaitable[bool]],
        send_apply_value: typing.Callable[[str, int], typing.Awaitable[bool]],
        send_delevel: typing.Optional[typing.Callable[[int, int, int], typing.Awaitable[bool]]] = None,
        send_heavy: typing.Optional[typing.Callable[[str], None]] = None,
        send_feats: typing.Optional[typing.Callable[[str, typing.List[int]], typing.Awaitable[bool]]] = None,
        on_death: typing.Optional[typing.Callable[[], None]] = None,
        is_awaiting_confirmation: typing.Optional[typing.Callable[[str], bool]] = None,
        send_purge: typing.Optional[typing.Callable[[str], typing.Awaitable[bool]]] = None,
        send_unparty: typing.Optional[typing.Callable[[str], typing.Awaitable[bool]]] = None,
        send_roster_remove: typing.Optional[typing.Callable[[str], typing.Awaitable[bool]]] = None,
        send_select: typing.Optional[typing.Callable[[str], typing.Awaitable[bool]]] = None,
    ):
        self._send_apply = send_apply
        self._send_apply_value = send_apply_value
        # Optional so any other ReconciliationTracker construction site
        # (tests, etc.) doesn't need updating just to
        # keep constructing -- the delevel branch below no-ops with a log
        # if this wasn't wired up, same tolerant shape as a send returning
        # False.
        self._send_delevel = send_delevel
        # Every correction for a HEAVY_ARMS member or a companion_class:
        # send MUST go through this, not self._send_apply -- see
        # is_heavy_arm's own comment (entitlement.py) for why: KotorClient.py's
        # _queue_heavy() is the one serializing gate that keeps two heavy
        # sends (a real-item delivery and a reconciler correction, or two
        # reconciler corrections) from ever landing in the same trampoline
        # batch, which is the actual crash class HEAVY_ARMS exists to
        # prevent -- self._send_apply alone bypasses that gate entirely.
        # Optional for the same reason as send_delevel above (tests/other
        # construction sites); falls back to a log-only no-op, same
        # tolerant shape.
        self._send_heavy = send_heavy
        # Feats corrections are LIGHT (KSE_GrantFeatArrayA never touches
        # multiclass/party/level-up), so this is its own callback, not
        # routed through send_heavy -- always resends the exact
        # already-decided missing subset (expected_feats - current), never
        # a fresh random draw. Optional, same tolerant shape as
        # send_delevel/send_heavy above.
        self._send_feats = send_feats
        # Roster cleanup: send_purge(npc_key) removes a companion the player
        # is not entitled to (the purge_companion trap). Who is entitled comes only from the
        # entitlement markers in the save (current_crew, see _CREW_RE), never from the client's
        # delivery log. Optional, same tolerant shape as the callbacks above.
        self._send_purge = send_purge
        # Star Forge pass only: out of the active party + objects destroyed, roster kept
        # (an entitled Bastila on the light path), and roster-only removal (a non-entitled
        # Bastila on the dark path, after the game's own script has taken her out of the
        # party; her object keeps standing for the scene).
        self._send_unparty = send_unparty
        self._send_roster_remove = send_roster_remove
        self._send_select = send_select
        self._on_death = on_death
        # Optional, same reasoning as send_delevel/on_death above -- a
        # missing callable just means "nothing else knows about in-flight
        # sends," so the deficit check below falls back to its old
        # behavior (fire immediately) rather than crashing. See the
        # missing-companion deficit check's own comment for the real race
        # this closes when it IS wired up (see KotorClient.py's
        # _is_arm_awaiting_confirmation).
        self._is_awaiting_confirmation = is_awaiting_confirmation or (lambda arm_name: False)
        self.reset_for_new_connection()

    def reset_for_new_connection(self) -> None:
        """Every field this method sets must be reset on each new
        connection, not just set once in __init__: a single long-running
        KotorClient process that connects to a DIFFERENT slot (a
        second slot after the first) without restarting the process
        would otherwise keep every bit of the PREVIOUS slot's
        reconciliation state -- expected_scalar/_skill_baseline/
        expected_companions still reflecting the old slot's items,
        current_classes/current_character_name still the old slot's last
        reported values, in-flight dedup guards still armed from the old
        slot's unresolved corrections -- silently breaking delivery of
        anything whose index/state falls below the old slot's counts
        (missing starting Jedi class, traps, abilities, and XP all at
        once on a fresh slot connect, regardless of item). This is the
        same class of bug as KotorClient.py's `_delivered_count` reset,
        generalized to the reconciler's entire internal state.

        Called from __init__ (first construction) AND from
        KotorContext.on_package's Connected handler (every later
        connection, same slot or a different one) so both cases start
        from an identical, genuinely clean slate -- never assume "first
        connect" and "reconnect" need different handling, since that
        asymmetry is exactly what let this bug hide for so long.

        Deliberately does NOT touch the injected callables (_send_apply/
        _send_apply_value/_send_delevel/_on_death) -- those are wiring,
        set once at construction, not per-connection state."""
        # CheckDeath() (see generate_poll_shared.py) is stateless -- it
        # fires every poll for as long as GetIsDead(oPC) is true, no
        # edge-detection in-game. _cycle_saw_death is per-poll-cycle
        # (reset at every SKILLREPORT, same "end of cycle" marker the rest
        # of reconciliation uses); _was_dead tracks the death EPISODE so
        # only one DeathLink bounce fires per death, not one per poll.
        self._cycle_saw_death = False
        self._was_dead = False

        # Set from slot_data once connected (see KotorContext.on_package) --
        # these defaults match Options.py's own defaults so behavior is
        # sane even before a "Connected" package has arrived.
        self.experience_mode = 0  # 0=off (pure vanilla, no clamping), 1=ap_limited (own check count), 2=ap_gated (items)
        self.experience_limiter = 600
        self.experience_item = 4000
        self.credit_mode = 0  # same 0/1/2 shape as experience_mode
        self.credit_limiter = 100
        self.credit_item = 5000
        # Kept fresh by KotorContext on every extender event (own checked-
        # location count) -- only consulted when experience_mode/credit_mode
        # is ap_limited, see handle_event()'s _AREA_RE branch and
        # _reconcile()'s credits section below.
        self.checked_location_count = 0
        # Set once at Connect (KotorClient.py, from location_names' own
        # count) -- the denominator for the journal-tracker reconciliation
        # branch's percentage calc below. 0 until that first Connect
        # completes, same "don't act on an assumed-zero default" reasoning
        # as classes_known/current_level elsewhere -- the percentage
        # branch is gated on this being nonzero.
        self.total_location_count = 0

        # Credits authorization tracking (see CreditMode's docstring: both
        # modes must clamp vanilla credit GAINS down to an expected total,
        # not just cap the ceiling -- a player sitting under the cap from
        # ordinary vanilla play is exactly as wrong as one who's over it).
        # REPLACES an earlier "track cumulative lifetime spend, subtract it
        # from the raw formula" design -- confirmed via a real live
        # incident to be a fatal one-way ratchet: any
        # decrease it ever observed got treated as permanent spend with no
        # way to reset, INCLUDING a decrease caused by its own stale
        # set_credits correction landing late (corrections are staged
        # through the same area-transition-gated arm queue as one-shot
        # item grants -- see arm_orchestrator.py's apply_armed_set --
        # despite this module's own header claiming a continuous/every-
        # poll clamp; only the SEND is per-poll, the actual field write
        # still waits for a real transition). A stale, lower target landing
        # after the player's real credits had organically drifted higher
        # in the meantime read as a huge "spend," which lowered the next
        # target, which produced an even bigger apparent "spend" on the
        # NEXT transition -- a runaway feedback loop that pinned credits at
        # 0 permanently within about 45 minutes of real play, even though
        # the player never came close to spending that much.
        #
        # New design tracks _credit_baseline directly (what the player is
        # currently authorized to have) instead of a lifetime deduction:
        # - A real decrease (current_credits dropping since the last real
        #   CREDITSREPORT) is accepted as legitimate spend by subtracting
        #   that exact delta from the baseline -- never by adopting
        #   current_credits as the new baseline outright, which would wipe
        #   out a still-pending cap-increase grant that hasn't landed yet.
        #   max(current_credits, ...) guards the result so a stale
        #   correction landing (which LOOKS like a big decrease relative to
        #   organically-drifted-up real credits) can never drag baseline
        #   below where it already correctly settled.
        # - _last_committed_cap tracks how much of credit_mode's raw cap
        #   (checks x credit_limiter, or the ap_gated item accumulator)
        #   has already been granted -- only the INCREMENT since last seen
        #   gets added to baseline, so a later cap increase is never
        #   confused with "restoring" earlier spend.
        # - Any observed credits ABOVE baseline (vanilla loot/quest/vendor
        #   income we never authorized) gets corrected back down to
        #   baseline -- this is the piece that actually fulfills "clamp
        #   vanilla gains," which the ceiling-only version of this fix
        #   would have missed entirely.
        # None-until-first-real-report, same reasoning as the old
        # _last_real_credits: a fresh connection must never judge
        # pre-connection history as an unauthorized gain to suppress.
        self._credit_baseline: typing.Optional[int] = None
        self._last_observed_credits: typing.Optional[int] = None
        self._last_committed_cap = 0
        # Set on every _AREA_CHECK_RE arrival -- see that regex's own
        # comment for why this is the right signal to gate staged-arm
        # retry decisions on, instead of wall-clock time alone.
        self._last_covered_area_entry_time: typing.Optional[float] = None
        # Set by an empty AP|NAMEREPORT| line (see that check's own
        # comment) and consumed/cleared at the top of _reconcile() --
        # marks the CURRENT poll cycle's data as untrustworthy so
        # _reconcile() skips it entirely rather than acting on any of it.
        self._last_poll_garbage = False

        # Credits in-flight tracking (see
        # _CREDITS_INFLIGHT_TIMEOUT_SECONDS's own comment for why this
        # exists) -- same shape as skills' own _inflight_skill_count/
        # _inflight_skill_since, just for a single scalar target instead of
        # a per-key count: _credits_inflight_target is the expected_credits
        # value we last actually sent a correction for, so an unchanged
        # deficit doesn't get re-sent every poll while presumably still
        # landing; _credits_inflight_since is when we sent it, for the
        # staleness timeout.
        self._credits_inflight_target: typing.Optional[int] = None
        self._credits_inflight_since: typing.Optional[float] = None

        # Ability baseline tracking -- the same bootstrap-then-track-deltas
        # shape as _skill_baseline and _credit_baseline, not a pure AP-grant
        # count: ability scores start at a real natural value (8-18), so a
        # zero-floor count would almost never compare meaningfully against
        # the current score -- it would take that many AP grants alone to
        # ever exceed a typical starting score. None until the first real
        # ABILITYBASEREPORT (bootstrapped in _reconcile() from the TRUE base
        # score, trusting whatever's currently real rather than judging
        # pre-connection history), then moved only by a real "ability_X"
        # grant (+1, note_item_received) or a legitimate decrease
        # (reduce_str/dex/int/wis trap, or Character Reset -- both lower it
        # directly, same "a real punishment/respec is not exempt" reasoning
        # as expected_feats/_skill_baseline). con is tracked (has a real AP item,
        # "Ability: Constitution Increase") even though no reduce_con trap
        # exists to lower it; cha is NOT tracked -- no AP item grants it at
        # all (Items.py has no "Ability: Charisma Increase"), so there is
        # no entitlement to protect.
        self._ability_baseline: typing.Dict[str, typing.Optional[int]] = {k: None for k in _ABILITY_KEYS}
        self._ability_inflight_count: typing.Dict[str, int] = {k: 0 for k in _ABILITY_KEYS}
        self._ability_inflight_since: typing.Dict[str, float] = {}

        self.expected_scalar: typing.Dict[str, int] = {"credits": 0, "xp": 0}
        # Skill entitlement, on the TRUE RANK scale: the rank each skill must
        # not fall below. None until the first SKILLBASEREPORT of this
        # connection (bootstrapped in _reconcile() from the real rank, same
        # "don't judge pre-connection history" rule as _ability_baseline and
        # _credit_baseline), then moved only by a real skill grant (+amount,
        # note_item_received) or a legitimate decrease (reduce_skill trap, or
        # Character Reset). It deliberately is NOT compared against
        # GetSkillRank (SKILLREPORT): that value is rank + ability modifier +
        # effects, so a grant tally measured against it under-heals by the
        # modifier on a fresh character and never triggers on a trained one.
        self._skill_baseline: typing.Dict[str, typing.Optional[int]] = {f: None for f in _SKILL_FIELDS}
        self.expected_companions: set[int] = set()
        # Companion keys a Trap: Remove a Companion has permanently removed (set by the client at
        # Connect and when the trap lands). They are not entitled, are never re-added, and are
        # purged by the roster cleanup if one turns up on the roster -- except while a scene that
        # stages companions on purpose is running (the busy flag), which is unchanged.
        self.trapped_off_companions: typing.Set[str] = set()
        # Roster cleanup state (see _ROSTER_RE). current_roster None = no
        # ROSTERREPORT yet this connection (nothing is ever purged on an
        # unknown roster); current_crew None = no CREWREPORT yet (nobody is entitled
        # or leaked on unknown markers).
        self.current_roster: typing.Optional[typing.Dict[str, bool]] = None
        self.current_crew: typing.Optional[typing.Dict[str, int]] = None
        self.roster_busy_mask: typing.Optional[int] = None
        self.roster_story_stage: typing.Optional[int] = None
        self.roster_busy = True
        self.roster_leviathan_done = False
        self.roster_in_starforge = False
        self.roster_final_choice = 0
        self.roster_bastila_in_party = False
        self.roster_malak_dead = False
        self._sf_streak: typing.Dict[str, int] = {}
        # Selectability (ROSTERREPORT sel=): companion key -> can be picked on the party screen,
        # None until a report carrying it has arrived.
        self.current_selectable: typing.Optional[typing.Dict[str, bool]] = None
        self._unsel_streak: typing.Dict[str, int] = {}
        self._unsel_inflight_since: typing.Dict[str, float] = {}
        self._sf_inflight_since: typing.Dict[str, float] = {}
        # "on" acts, "log" only reports what it would do, "off" disables (KotorClient's
        # /ap_roster_cleanup). It governs the Star Forge pass and the selectability fix. Not reset per
        # connection: it is an operator choice, not live state.
        self.roster_cleanup_mode = "on"
        # The leak purge (a companion on the roster whose entitlement marker is not 10) has its own
        # switch, report-only by default (KotorClient's /ap_leak_purge).
        # "auto" (default): report only until the Leviathan has been escaped, purge from then on. "on" / "log" / "off" are explicit
        # choices (/ap_leak_purge) that hold in every phase.
        self.leak_purge_mode = "auto"
        self._roster_first_seen: typing.Optional[float] = None
        self._roster_extra_streak: typing.Dict[str, int] = {}
        self._leak_seen: typing.Set[str] = set()
        self._leak_area_count: typing.Dict[str, int] = {}
        self._busy_flag_since: typing.Optional[float] = None
        self._busy_warned_at: float = 0.0
        self._purge_inflight_since: typing.Dict[str, float] = {}
        # Marker repair: when the grant arm was last re-sent for a received companion whose entitlement marker was missing.
        self._marker_repair_since: typing.Dict[str, float] = {}
        # PC class self-healing (see entitlement.py's PC_CLASS_CONST_TO_ARM) --
        # tied to AP progress (the last class-switch item actually received),
        # not to any one running game process, same reasoning as
        # expected_scalar/_last_committed_cap surviving a mere reconnect.
        # -1 means no class item has been received this seed -- PC class
        # isn't AP-managed, so no correction should ever fire.
        self.expected_pc_class: int = -1
        # CompanionClass=no_jedi/randomize_all's fixed roll (npc_key ->
        # class name string, e.g. "sentinel") -- set from slot_data on
        # Connect (see KotorClient.py), same scope/lifetime as credit_mode
        # etc. above. Empty for off/jedi_companion.
        self.companion_class_rolls: typing.Dict[str, str] = {}
        # Class corrections' own in-flight tracking -- see
        # _STAGED_ARM_INFLIGHT_TIMEOUT_SECONDS's own comment for why this
        # exists at all. Same single-target-per-key shape as credits'
        # _credits_inflight_target/_since, just keyed per companion for the
        # companion half.
        self._pc_class_inflight_target: typing.Optional[int] = None
        self._pc_class_inflight_since: typing.Optional[float] = None
        self._companion_class_inflight: typing.Dict[str, int] = {}
        self._companion_class_inflight_since: typing.Dict[str, float] = {}
        # Feats entitlement (see DEVELOPMENT_HISTORY.md section 13) -- "pc" plus each companion key -> every feat_id
        # ever actually decided for them by a resolved Additional Feats
        # item (KotorClient.py's _resolve_additional_feats). UNLIKE
        # class/xp/credits, there is no formula to recompute this from
        # slot_data -- the random choice made at resolve time IS the
        # entitlement, so it's populated by note_feats_granted() below and
        # (after a process restart) rebuilt from the delivery log via
        # KotorClient.py's _load_granted_feats -- tied to AP progress, not
        # to any one running game process, same reasoning as expected_
        # scalar/expected_pc_class surviving a mere reconnect.
        self.expected_feats: typing.Dict[str, typing.Set[int]] = {}
        # Same in-flight shape as the class tracking above, keyed per
        # character ("pc" or npc_key) -- tracks the exact missing-subset
        # target last requested, so an unresolved gap doesn't re-send every
        # poll while the (staged, not instant -- see
        # _STAGED_ARM_INFLIGHT_TIMEOUT_SECONDS) grant is still landing.
        self._feats_inflight: typing.Dict[str, typing.FrozenSet[int]] = {}
        self._feats_inflight_since: typing.Dict[str, float] = {}
        # How many times the same missing set has been sent without it ever landing, and who the retries were given up for.
        self._feats_attempts: typing.Dict[str, typing.Tuple[typing.FrozenSet[int], int]] = {}
        self._feats_gave_up: typing.Set[str] = set()
        # Progression-item entitlement (see PROGRESSION_ITEM_RESREFS's own
        # comment, entitlement.py) -- which of the 8 tracked keys have
        # actually been sent via give_item: (note_item_received below),
        # same "no formula, just record what was decided" shape as
        # expected_feats. Tied to AP progress, not to any one running game
        # process, same reasoning as expected_scalar/expected_pc_class.
        self.expected_progression_items: typing.Set[str] = set()
        # Same in-flight shape as skills/feats above, keyed per tracked key.
        self._progression_item_inflight_since: typing.Dict[str, float] = {}
        # "Archipelago Tracker" journal stage in-flight tracking -- a
        # single target (not per-key like feats/progression items, since
        # there's only one quest) plus its own timeout, same shape as
        # credits'/class's own single-target in-flight fields.
        self._ap_tracker_inflight_target: typing.Optional[int] = None
        self._ap_tracker_inflight_since: typing.Optional[float] = None

        self.current_scalar: typing.Dict[str, int] = {"credits": 0, "xp": 0}
        # Guards the _AREA_RE-triggered XP clamp below against firing off
        # current_scalar["xp"]'s bare 0 default before a real XPREPORT has
        # actually landed -- unlike current_level (checked "is not None"
        # before any delevel decision), current_scalar has no such
        # sentinel, and the AREA-triggered clamp runs immediately off the
        # area transition itself rather than waiting for that poll cycle's
        # own reports the way _reconcile()'s credits check effectively
        # does (SKILLREPORT-triggered, always last in a cycle). REAL
        # CRASH CAUSED BY THIS: extender reconnected mid-
        # session, reset_live_state() zeroed current_scalar, and the very
        # next AREA check fired before that cycle's XPREPORT arrived --
        # clamped real XP 38105 to a bogus 0 -> 40000 while the player was
        # mid-dialogue. See reset_live_state()'s own docstring for the
        # sibling bug already fixed for current_level/delevel; this is the
        # same category of staleness bug for the plain xp-clamp path that
        # fix didn't cover.
        self._xp_seen_since_reset = False
        self.current_skills: typing.Dict[str, int] = {f: 0 for f in _SKILL_FIELDS}
        # From CLASSREPORT -- real in-game state, not delivery bookkeeping.
        # None until the first report arrives (distinguishes "don't know
        # yet" from "confirmed level 0"), so callers can choose to wait for
        # real data rather than act on an assumed-zero default.
        self.current_classes: typing.Dict[str, int] = {
            "guardian": 0, "consular": 0, "sentinel": 0,
            "baseclass": -1, "baselevel": 0,
        }
        self._classes_known = False
        # From COMPANIONCLASSREPORT -- real in-game state per companion,
        # -1 until first report OR not currently recruited (see
        # _COMPANION_CLASSREPORT_RE's own comment).
        self.current_companion_classes: typing.Dict[str, int] = {k: -1 for k in _COMPANION_CLASS_KEYS}
        # From COMPANIONFEATSREPORT -- real in-game state per companion,
        # None = not currently recruited (same concept as
        # current_companion_classes' -1, just typed for a set instead of
        # an int). PC's own feats reuse current_feats below -- no separate
        # PC entry needed here.
        self.current_companion_feats: typing.Dict[str, typing.Optional[typing.Set[int]]] = \
            {k: None for k in _COMPANION_CLASS_KEYS}
        # From PROGRESSIONITEMSREPORT -- real in-game possession, keyed the
        # same as expected_progression_items/PROGRESSION_ITEM_RESREFS.
        self.current_progression_items: typing.Dict[str, bool] = {k: False for k in PROGRESSION_ITEM_RESREFS}
        # From APTRACKERREPORT -- real in-game state, None until first
        # report (same "don't assume" distinction as current_level etc).
        self.current_ap_tracker_stage: typing.Optional[int] = None
        # From LEVELREPORT/FORCEREPORT (delevel reconciler) -- real
        # in-game state, same "None/-1 until first report" distinction as
        # current_classes above.
        self.current_level: typing.Optional[int] = None
        self.current_force: typing.Dict[str, int] = {"current": 0, "max": 0}
        # Traps: read-only state, no expected_/correction
        # counterpart -- see the report regexes' own comment above.
        self.current_abilities: typing.Dict[str, int] = {
            "str": 0, "dex": 0, "con": 0, "int": 0, "wis": 0, "cha": 0,
        }
        # True base scores from ABILITYBASEREPORT -- None until the first
        # report of this connection (and for good with an extender build that
        # predates the report). Tracked abilities only; cha has no AP item.
        self.current_ability_bases: typing.Dict[str, typing.Optional[int]] = {k: None for k in _ABILITY_KEYS}
        self._ability_base_missing_warned = False
        # True skill ranks from SKILLBASEREPORT (see _SKILLBASE_RE) -- None
        # until the first report of this connection, and for good with an
        # extender build that predates it. current_skills below stays the
        # effective GetSkillRank value.
        self.current_skill_bases: typing.Dict[str, typing.Optional[int]] = {f: None for f in _SKILL_FIELDS}
        self._skill_base_missing_warned = False
        self.current_feats: typing.Set[int] = set()
        # Full held-feat list from FEATFULL (None until one has arrived this connection).
        self.full_feats: typing.Optional[typing.Set[int]] = None
        self.current_powers: typing.Set[int] = set()
        # From NAMEREPORT -- the delivery log's other half (see
        # KotorClient.py) keys on this to tell a fresh character (deliberate
        # restart, should get everything re-granted) apart from reconnecting
        # to the same character (shouldn't replay history already sent).
        self.current_character_name: typing.Optional[str] = None
        self._cycle_companions: set[int] = set()
        self.last_seen_companions: set[int] = set()

        # In-flight tracking, skills/companions only (credits/xp are
        # replace-semantics via set_credits/set_xp so can't compound; the
        # numbered-arm queue skills/companions use has NO dedup, so without
        # this, _reconcile() re-requesting the same unresolved deficit every
        # ~5s poll while delivery is pending -- always true for a while,
        # since delivery is gated on the next area transition -- compounds
        # into a real over-grant (e.g. a single starting_persuade
        # boost firing 9 times instead of once during a pre-transition
        # wait after connecting). Cleared whenever current_skill_bases/
        # last_seen_companions shows real progress, so a lost/dropped
        # request still self-heals on the next cycle.
        self._inflight_skill_count: typing.Dict[str, int] = {f: 0 for f in _SKILL_FIELDS}
        self._inflight_skill_since: typing.Dict[str, float] = {}
        self._inflight_companions: set[int] = set()
        # Last TRUE rank seen per skill, for the in-flight reset in
        # _reconcile(). Keyed on the true rank, not GetSkillRank, so ability,
        # gear and debuff changes can't masquerade as a grant landing.
        self._prev_skill_bases: typing.Dict[str, typing.Optional[int]] = {f: None for f in _SKILL_FIELDS}

        self.last_corrections: typing.List[str] = []

    def reset_live_state(self) -> None:
        """Resets only the fields that reflect what the game currently
        reports (repopulated fresh by the next real poll) -- NOT
        expected_scalar/_skill_baseline/expected_companions (what the
        player is owed, tied to their AP progress, not to any one running
        game process) and NOT the experience_mode/credit_mode/etc option
        config (only ever set from slot_data, which isn't resent here).
        Only reset_for_new_connection() touches those, on a genuine new
        AP slot Connect.

        Needed because KotorContext's ExtenderBridge reconnects
        automatically whenever the LOCAL game process restarts,
        independent of the AP server's own Connected message -- the AP
        session itself usually stays open across a game crash/relaunch,
        so Connected never refires and reset_for_new_connection() never
        runs. Without this, an event like AP|CHECK|AREA that streams in
        before the fresh reports right behind it compares against
        leftover state from before the restart, not the newly-loaded
        save's real values. Real case this fixes: current_level held
        over from before a restart made a delevel correction's
        `target_level < self.current_level` check pass against a
        save that had already reset to level 1, computing a delevel
        target that didn't match the freshly-loaded character at all and
        crashed the game."""
        self.current_scalar = {"credits": 0, "xp": 0}
        self._xp_seen_since_reset = False
        self.current_skills = {f: 0 for f in _SKILL_FIELDS}
        self.current_classes = {
            "guardian": 0, "consular": 0, "sentinel": 0,
            "baseclass": -1, "baselevel": 0,
        }
        self._classes_known = False
        self.current_companion_classes = {k: -1 for k in _COMPANION_CLASS_KEYS}
        self.current_companion_feats = {k: None for k in _COMPANION_CLASS_KEYS}
        self.current_roster = None
        self.current_crew = None
        self.roster_busy_mask = None
        self.roster_story_stage = None
        self.roster_busy = True
        self.roster_leviathan_done = False
        self.roster_in_starforge = False
        self.roster_final_choice = 0
        self.roster_bastila_in_party = False
        self._sf_streak = {}
        self._sf_inflight_since = {}
        self.current_selectable = None
        self._unsel_streak = {}
        self._unsel_inflight_since = {}
        self._roster_first_seen = None
        self._roster_extra_streak = {}
        self._leak_seen = set()
        self._leak_area_count = {}
        self._busy_flag_since = None
        self._purge_inflight_since = {}
        self._marker_repair_since = {}
        self.current_progression_items = {k: False for k in PROGRESSION_ITEM_RESREFS}
        self.current_ap_tracker_stage = None
        self.current_level = None
        self.current_force = {"current": 0, "max": 0}
        self.current_abilities = {"str": 0, "dex": 0, "con": 0, "int": 0, "wis": 0, "cha": 0}
        self.current_ability_bases = {k: None for k in _ABILITY_KEYS}
        self.current_feats = set()
        self.full_feats = None
        self.current_powers = set()
        self.current_character_name = None
        self._cycle_companions = set()
        self.last_seen_companions = set()
        self.current_skill_bases = {f: None for f in _SKILL_FIELDS}
        self._prev_skill_bases = {f: None for f in _SKILL_FIELDS}
        # Same staleness risk as current_scalar/current_level above -- a
        # stale reference point here would misread the freshly-loaded
        # save's real credits as an unauthorized gain (or a spend) relative
        # to a baseline computed for the PREVIOUS process's state. Reset to
        # None so the next real CREDITSREPORT re-bootstraps cleanly (same
        # "don't judge history, adopt whatever's real right now" rule as a
        # fresh connection) -- _last_committed_cap deliberately NOT reset
        # here: it's tied to AP progress (how much of the cap has already
        # been granted), not to any one running game process, same
        # reasoning as expected_scalar surviving a mere reconnect.
        self._credit_baseline = None
        self._last_observed_credits = None
        self._credits_inflight_target = None
        self._credits_inflight_since = None
        self._pc_class_inflight_target = None
        self._pc_class_inflight_since = None
        self._companion_class_inflight = {}
        self._companion_class_inflight_since = {}
        self._feats_inflight = {}
        self._feats_inflight_since = {}
        self._feats_attempts = {}
        self._feats_gave_up = set()
        self._progression_item_inflight_since = {}
        self._ap_tracker_inflight_target = None
        self._ap_tracker_inflight_since = None
        self._inflight_skill_count = {f: 0 for f in _SKILL_FIELDS}
        self._inflight_skill_since = {}
        self._inflight_companions = set()

    @property
    def classes_known(self) -> bool:
        """False until the first CLASSREPORT poll arrives. Callers gating a
        class-switch send on has_class() should wait for this rather than
        act on the assumed-zero default -- acting too early on a fresh
        connection could send a class switch before we've actually heard
        back from the game about what the character already has."""
        return self._classes_known

    def has_class(self, arm_name: str) -> bool:
        """True if the character already has the Jedi class this arm_name
        would grant, per real reported game state (not delivery
        bookkeeping) -- see CLASS_ARM_TO_KEY and generate_poll_shared.py's
        CheckClasses(). Safe to call for non-class arm_names too (always
        False for those, harmless)."""
        key = CLASS_ARM_TO_KEY.get(arm_name)
        if key is None:
            return False
        return self.current_classes.get(key, 0) > 0

    def note_feats_granted(self, character_key: str, feat_ids: typing.List[int]) -> None:
        """Called by KotorClient.py's _resolve_additional_feats once a
        random Additional Feats draw actually sends -- NOT from
        note_item_received(), since the ids aren't known at raw-item-
        receipt time (they're chosen later, once recruited+class-finalized
        gates clear). character_key is "pc" or a companion npc_key.
        Unions into expected_feats rather than replacing it -- each
        resolve is a distinct, additive grant (a character can receive
        multiple Additional Feats items over a playthrough), and this is
        the one and only record of what was ever decided for them."""
        self.expected_feats.setdefault(character_key, set()).update(feat_ids)

#BK As noted elsewhere we should create native function to log the action taken by delivery arms.
    def note_item_received(self, arm_name: str) -> None:
        """Called for every AP item forwarded to the extender -- updates
        what the player is now expected to have, regardless of whether
        this specific grant is one we auto-correct (unmapped arms just
        aren't tracked here, no harm)."""
        if arm_name == "xp":
            # Amount comes from the seed's experience_item option, not a
            # fixed ARM_EFFECT entry -- only meaningful when experience_mode
            # is ap_gated (ap_limited derives its expected total from the
            # player's own checked-location count instead, and off doesn't
            # touch XP at all -- see handle_event()'s _AREA_RE branch).
            # Harmless to keep tracking this even when unused.
            self.expected_scalar["xp"] += self.experience_item
            return
        if arm_name.startswith("give_item:"):
            # Only the 8 tracked progression resrefs are recorded here --
            # the general gear pool deliberately gets no reconciliation
            # (see PROGRESSION_ITEM_RESREFS's own comment, entitlement.py).
            # A bare resref or resref:count both split cleanly on ":".
            resref = arm_name.split(":", 2)[1]
            key = _RESREF_TO_PROGRESSION_KEY.get(resref)
            if key is not None:
                self.expected_progression_items.add(key)
            return
        if arm_name == "credits":
            # Amount comes from the seed's credit_item option, not a fixed
            # ARM_EFFECT entry -- same reasoning as "xp" above. Only
            # meaningful under credit_mode's ap_gated (ap_limited derives
            # its expected total from checked_location_count instead, and
            # off doesn't touch credits at all -- see _reconcile()).
            self.expected_scalar["credits"] += self.credit_item
            return
        pc_class_const = _ARM_TO_PC_CLASS_CONST.get(arm_name)
        if pc_class_const is not None:
            # A real class-switch item is a full replace (raw CLASS0_TYPE
            # overwrite, not additive -- see generate_trampoline_batch.py's
            # class_guardian/pc_class_soldier blocks), so the LAST one
            # received always wins, same as set_xp/set_credits' own
            # replace semantics.
            self.expected_pc_class = pc_class_const
            return
        rule = ARM_EFFECT.get(arm_name)
        if rule is None:
            return
        kind = rule[0]
        if kind == "scalar":
            _, key, amount = rule
            self.expected_scalar[key] += amount
        elif kind == "skill":
            _, key, amount = rule
            # No-op if not yet bootstrapped (see _skill_baseline's own
            # comment) -- _reconcile()'s bootstrap adopts the true rank as
            # it stands, so nothing is lost by skipping the increment here.
            if self._skill_baseline.get(key) is not None:
                self._skill_baseline[key] += amount
                # Mark this amount in-flight too, not just in the baseline --
                # otherwise _reconcile() computes a deficit against the true
                # rank (which hasn't caught up to this real grant yet, since
                # delivery and the next poll cycle race independently) with
                # no visibility that a real delivery already covers it, and
                # sends a redundant correction for the exact same amount on
                # top.
                if self._inflight_skill_since.get(key) is None:
                    self._inflight_skill_since[key] = time.time()
                self._inflight_skill_count[key] += amount
        elif kind == "companion":
            _, npc_idx = rule
            self.expected_companions.add(npc_idx)
        elif kind == "ability":
            _, key, amount = rule
            # No-op if not yet bootstrapped (see _ability_baseline's own
            # comment) -- _reconcile()'s bootstrap adopts whatever's
            # currently real, which by then already reflects this grant's
            # own effect on the actual stat, so nothing is lost by
            # skipping the increment here.
            if self._ability_baseline.get(key) is not None:
                self._ability_baseline[key] += amount
                # Same in-flight bookkeeping as the skill branch above --
                # a real delivery's own effect on `current` hasn't landed
                # by the time this runs, so without marking it in-flight,
                # the next reconciliation pass sees a deficit a real
                # delivery already covers and sends a redundant
                # correction for the same amount. Charisma has no
                # ARM_EFFECT entry and therefore no reconciliation path at
                # all, which is why this specific race can only double
                # the 5 tracked abilities (str/dex/con/int/wis), never it.
                if self._ability_inflight_since.get(key) is None:
                    self._ability_inflight_since[key] = time.time()
                self._ability_inflight_count[key] += amount

    def handle_event(self, event: str) -> None:
        """Feed every extender EVENT line here. Parses the report types
        reconciliation cares about; SKILLREPORT is poll_shared's LAST
        report each cycle (see generate_poll_shared.py's main()), so its
        arrival is used as the "this poll's data is complete, reconcile
        now" trigger."""
        m = _VENDOR_CREDIT_GAIN_RE.search(event)
        if m:
            # Without this, credit_mode's own clamp (below) would read
            # this exactly like an unauthorized vanilla gain (loot/quest)
            # and silently correct it right back down on the very next
            # poll -- the same clamp that already treats a DECREASE as a
            # legitimate spend has no matching case for a legitimate
            # INCREASE. Fold it into the baseline directly (we know the
            # authoritative new total from the vendor script's own report)
            # and pre-seed _last_observed_credits so the delta-based
            # spend-detection above doesn't see a phantom decrease next
            # cycle either.
            new_credits = int(m.group(1))
            if self._credit_baseline is not None:
                self._credit_baseline = max(self._credit_baseline, new_credits)
            self._last_observed_credits = new_credits
            return
        if _VENDOR_RESET_RE.search(event):
            # Character Reset strips the PC's feats/skills/abilities in
            # the game -- without this, expected_feats["pc"]/
            # _skill_baseline/_ability_baseline (AP-side entitlement)
            # would see the very next poll as a deficit and silently
            # regrant everything back, undoing the respec within one
            # cycle. Explicit product decision: a respec is a real
            # respec -- AP-earned feats/skill points/ability scores are
            # not exempt. Powers aren't reconciled at all (no expected_*
            # counterpart exists -- there's no repeatable AP "add" item
            # for powers to reconcile against in the first place, unlike
            # feats/skills/abilities), so there's nothing to clear there
            # -- the vendor's own strip is all that ever touches them.
            self.expected_feats["pc"] = set()
            self._feats_inflight.pop("pc", None)
            self._feats_inflight_since.pop("pc", None)
            # ap_vs_reset.nss zeroes every skill rank.
            self._skill_baseline = {f: 0 for f in _SKILL_FIELDS}
            self._inflight_skill_count = {f: 0 for f in _SKILL_FIELDS}
            self._inflight_skill_since = {}
            # RESET_ABILITY_FLOOR (generate_ap_vendor.py) -- the exact
            # value ap_vs_reset.nss hard-resets all 6 abilities to.
            self._ability_baseline = {k: 10 for k in _ABILITY_KEYS}
            self._ability_inflight_count = {k: 0 for k in _ABILITY_KEYS}
            self._ability_inflight_since = {}
            return
        m = _TRAP_REDUCE_SKILL_RE.search(event)
        if m:
            # before/after are GetSkillRank values read in the same script
            # run, and the ability modifier doesn't change across the call, so
            # their difference is exactly how far the trap moved the true
            # rank. Lower the baseline by that amount (it lives on the rank
            # scale); a baseline that hasn't bootstrapped yet adopts the
            # already-lowered rank when it does.
            skill_key = m.group(1)
            drop = max(0, int(m.group(2)) - int(m.group(3)))
            current_baseline = self._skill_baseline.get(skill_key)
            if current_baseline is not None:
                self._skill_baseline[skill_key] = max(0, current_baseline - drop)
            return
        m = _TRAP_REDUCE_ABILITY_RE.search(event)
        if m:
            key = _TRAP_ABILITY_TO_KEY.get(m.group(1))
            if key is None:
                # reduce_cha: charisma has no AP grant, so there is no
                # baseline for it to lower.
                return
            # before/after are EFFECTIVE scores read in the same script run,
            # so their difference is exactly how far the trap moved the true
            # base. The baseline lives on the base scale, so lower it by that
            # amount rather than adopting an effective score (which would
            # carry any item bonus into the baseline). Subtracting keeps
            # several traps landing before the next poll cumulative. A
            # baseline that hasn't bootstrapped yet adopts the already-lowered
            # base when it does.
            drop = max(0, int(m.group(2)) - int(m.group(3)))
            current_baseline = self._ability_baseline.get(key)
            if current_baseline is not None:
                self._ability_baseline[key] = max(0, current_baseline - drop)
            return
        m = _SET_CREDITS_APPLIED_RE.search(event)
        if m:
            before_credits = int(m.group(1))
            new_credits = int(m.group(2))
            if new_credits >= before_credits:
                # The reconciler's own correction landing (a top-up, or a
                # confirmation that's already equal) -- new_credits IS the
                # authoritative target here, safe to sync immediately.
                self._credit_baseline = new_credits
                self._last_observed_credits = new_credits
            # A real decrease (remove_credits, or any other direct
            # credits-lowering action) is deliberately NOT synced here.
            # Setting baseline straight to new_credits (the old behavior)
            # made the drop permanent: expected_scalar["credits"]/
            # _last_committed_cap (the player's actual entitled cap) is
            # untouched by a trap, but baseline was, so every future
            # check/grant only ever added its own delta on top of the
            # trap's floor instead of restoring the player toward what
            # they'd already earned -- a trap should cost credits once,
            # the same as a real spend, not permanently forfeit past
            # entitlement. Leaving this branch a no-op lets the ordinary
            # CREDITSREPORT-driven delta logic below (current_credits,
            # _last_observed_credits) pick up the exact same drop on its
            # own very next poll and apply the identical floor-only
            # treatment ("baseline follows current down, cap untouched")
            # a normal spend already gets -- not a special case, the same
            # path. The player then only grows back via the usual
            # mechanisms: the cap genuinely rising (a new credit_item
            # grant under ap_gated, a new check under ap_limited), or an
            # explicit vendor credit gain (_VENDOR_CREDIT_GAIN_RE) -- never
            # an automatic bounce back to the pre-trap total with zero new
            # progress.
            return
        m = _CREDITS_RE.search(event)
        if m:
            self.current_scalar["credits"] = int(m.group(1))
            return
        m = _XP_RE.search(event)
        if m:
            self.current_scalar["xp"] = int(m.group(1))
            self._xp_seen_since_reset = True
            return
        m = _COMPANION_RE.search(event)
        if m:
            self._cycle_companions.add(int(m.group(1)))
            return
        m = _CLASSREPORT_RE.search(event)
        if m:
            self.current_classes["guardian"] = int(m.group(1))
            self.current_classes["consular"] = int(m.group(2))
            self.current_classes["sentinel"] = int(m.group(3))
            # baseclass/baselevel are only present once the DLL carrying
            # the current ap_poll_shared.nss is deployed -- older builds
            # still match (the whole suffix is optional), just without them.
            if m.group(4) is not None:
                self.current_classes["baseclass"] = int(m.group(4))
                self.current_classes["baselevel"] = int(m.group(5))
            self._classes_known = True
            return
        m = _ROSTER_RE.search(event)
        if m:
            values = [int(x) for x in m.groups()[:15] if x is not None]
            sel_bits = m.group(16)
            self.current_selectable = ({k: b == "1" for k, b in zip(_ROSTER_KEYS, sel_bits)}
                                       if sel_bits else None)
            self.roster_busy = bool(values[0])
            self.current_roster = {k: bool(v) for k, v in zip(_ROSTER_KEYS, values[1:10])}
            self.roster_leviathan_done = values[10] >= _LEVIATHAN_DONE_ENTRY
            self.roster_in_starforge = bool(values[11])
            self.roster_final_choice = values[12]
            self.roster_bastila_in_party = bool(values[13])
            self.roster_malak_dead = bool(values[14]) if len(values) > 14 else False
            self.roster_busy_mask = int(m.group(17)) if m.group(17) else None
            self.roster_story_stage = int(m.group(18)) if m.group(18) else None
            if self._roster_first_seen is None:
                self._roster_first_seen = time.time()
            self._watch_busy_sources()
            extras = set(self._roster_extras())
            leak_ok = self._leak_rule_applies()
            unsel = self._unselectable_entitled()
            for key in _ROSTER_KEYS:
                if key in unsel and not self.roster_busy and not self.roster_in_starforge:
                    self._unsel_streak[key] = self._unsel_streak.get(key, 0) + 1
                else:
                    self._unsel_streak[key] = 0
                    if key not in unsel:
                        self._unsel_inflight_since.pop(key, None)
            sf_actions = self._starforge_actions()
            for key in set(_STARFORGE_PURGE_KEYS) | {"bastila"}:
                if key in sf_actions and not self.roster_busy:
                    self._sf_streak[key] = self._sf_streak.get(key, 0) + 1
                else:
                    self._sf_streak[key] = 0
                    if key not in sf_actions:
                        self._sf_inflight_since.pop(key, None)
            self._leak_seen = set()
            for key in _ROSTER_KEYS:
                if key in extras and leak_ok:
                    self._roster_extra_streak[key] = self._roster_extra_streak.get(key, 0) + 1
                    self._leak_seen.add(key)
                else:
                    self._roster_extra_streak[key] = 0
                    self._leak_area_count[key] = 0
                    if key not in extras:
                        self._purge_inflight_since.pop(key, None)
                        self._marker_repair_since.pop(key, None)
            return
        m = _CREW_RE.search(event)
        if m:
            self.current_crew = {k: int(v) for k, v in zip(_ROSTER_KEYS, m.groups())}
            return
        m = _COMPANION_CLASSREPORT_RE.search(event)
        if m:
            for key, value in zip(_COMPANION_CLASS_KEYS, m.groups()):
                self.current_companion_classes[key] = int(value)
            return
        m = _COMPANION_FEATSREPORT_RE.search(event)
        if m:
            for key, value in zip(_COMPANION_CLASS_KEYS, m.groups()):
                self.current_companion_feats[key] = None if value == "NONE" else {int(x) for x in value.split(",") if x}
            return
        m = _PROGRESSIONITEMSREPORT_RE.search(event)
        if m:
            for key, value in zip(PROGRESSION_ITEM_RESREFS, m.groups()):
                self.current_progression_items[key] = value == "1"
            return
        m = _APTRACKERREPORT_RE.search(event)
        if m:
            self.current_ap_tracker_stage = int(m.group(1))
            return
        if _AREA_CHECK_RE.search(event):
            # No return: _AREA_RE below matches this same event and drives
            # the XP clamp. The branches in between match other report
            # types, so falling through is safe.
            self._last_covered_area_entry_time = time.time()
            # Leak purge: every area entry while a companion stays on the roster without an entitlement marker counts as one transition.
            for key in self._leak_seen:
                self._leak_area_count[key] = self._leak_area_count.get(key, 0) + 1
        m = _LEVEL_RE.search(event)
        if m:
            self.current_level = int(m.group(1))
            return
        m = _FORCE_RE.search(event)
        if m:
            self.current_force["current"] = int(m.group(1))
            self.current_force["max"] = int(m.group(2))
            return
        if "AP|NAMEREPORT|" in event and not _NAMEREPORT_RE.search(event):
            # Empty name -- the PC object was momentarily invalid this poll
            # tick (a loading screen/area transition catching the poll
            # mid-flight), not real state: every other field reports as a
            # sentinel/zero default in the same tick (abilities all 0,
            # skills all -1, baselevel 0, XP 0). generate_poll_shared.py's
            # main() calls CheckCharacterName() immediately before
            # CheckSkills() every cycle, so this flag is set in time for
            # _reconcile() (triggered by SKILLREPORT right after) to see
            # it and skip the whole cycle rather than trust any of it --
            # see _reconcile()'s own check for why skipping the whole
            # cycle, not just credits, is the right scope.
            self._last_poll_garbage = True
            return
        m = _NAMEREPORT_RE.search(event)
        if m:
            self.current_character_name = m.group(1)
            return
        m = _ABILITY_RE.search(event)
        if m:
            self.current_abilities["str"] = int(m.group(1))
            self.current_abilities["dex"] = int(m.group(2))
            self.current_abilities["con"] = int(m.group(3))
            self.current_abilities["int"] = int(m.group(4))
            self.current_abilities["wis"] = int(m.group(5))
            self.current_abilities["cha"] = int(m.group(6))
            return
        m = _ABILITYBASE_RE.search(event)
        if m:
            # Groups 1-5 are str/dex/con/int/wis, matching _ABILITY_KEYS; the
            # sixth (cha) isn't tracked, so zip drops it.
            for key, value in zip(_ABILITY_KEYS, m.groups()):
                self.current_ability_bases[key] = int(value)
            return
        m = _SKILLBASE_RE.search(event)
        if m:
            for key, value in zip(_SKILL_FIELDS, m.groups()):
                self.current_skill_bases[key] = int(value)
            return
        m = _FEATFULL_RE.search(event)
        if m:
            self.full_feats = {int(x) for x in m.group(1).split(",") if x}
            return
        m = _FEATREPORT_RE.search(event)
        if m:
            self.current_feats = {int(x) for x in m.group(1).split(",") if x}
            return
        m = _POWERREPORT_RE.search(event)
        if m:
            self.current_powers = {int(x) for x in m.group(1).split(",") if x}
            return
        if _AREA_RE.search(event):
            # AP|CHECK|AREA|<idx> fires directly from the area's native
            # OnEnter handler (see generate_area_trampolines.py) -- a true
            # one-shot transition edge, not a poll-cycle repeat, so no extra
            # dedup is needed here. This is the ONLY place XP gets corrected
            # when experience_mode isn't off: once per real area entry,
            # clamped to the exact expected total (both directions -- this
            # is what eliminates vanilla combat/quest XP, unlike credits
            # which can only ever be topped up), fired as a priority action
            # ahead of whatever else that area's trampoline batch applies.
            # experience_mode picks WHERE the expected total comes from:
            # ap_gated sums received Experience Points items (accumulated in
            # expected_scalar via note_item_received); ap_limited derives it
            # directly from the player's own progress (checked_location_count
            # x experience_limiter) instead, independent of anyone's item
            # sends. off entirely means don't touch XP at all -- pure
            # vanilla.
            if self.experience_mode != 0 and self._xp_seen_since_reset:  # off, or no real report yet
                if self.experience_mode == 2:  # ap_gated
                    expected = self.expected_scalar.get("xp", 0)
                else:  # ap_limited
                    expected = self.checked_location_count * self.experience_limiter
                current = self.current_scalar.get("xp", 0)
                if expected != current:
                    # Native SetXP() silently no-ops on any decrease, even
                    # within the same level -- always use the raw
                    # KSE_SetCreatureField write (build_delevel_block) for
                    # a downward correction instead. Upward stays plain
                    # set_xp.
                    target_level = _level_for_xp(expected)
                    needs_delevel = (
                        expected < current
                        and self.current_level is not None
                    )
                    if needs_delevel:
                        # Proportional Force scaling, not an exact
                        # per-class formula -- Force-per-level does NOT
                        # generalize across Jedi classes via forcedie
                        # (Sentinel +14/level, Consular +11/level despite
                        # Consular's BIGGER forcedie), so a per-class exact
                        # table isn't worth chasing for a correction that
                        # just needs to be reasonable. -1 sentinel means
                        # "don't touch Force" for a non-Jedi PC.
                        has_jedi = bool(
                            self.current_classes["guardian"]
                            or self.current_classes["consular"]
                            or self.current_classes["sentinel"]
                        )
                        # The level written is never HIGHER than the player's current level. A player can hold more XP
                        # than their level reflects (XP past the next threshold, level-up not taken yet), and the
                        # expected XP can still map to a level above the current one; raising the class level with a
                        # raw field write skips the level-up (HP, feats, skill points) and was followed by a crash at
                        # the next area load. In that case only the XP is written and the player's own level-up stands.
                        write_level = min(target_level, self.current_level) if self.current_level else target_level
                        new_force = -1
                        if has_jedi and self.current_level:
                            new_force = round(
                                self.current_force["current"] * write_level / self.current_level
                            )
                        logger.info(
                            f"[reconcile] downward XP correction (level {self.current_level} -> "
                            f"{write_level}, xp {current} -> {expected}) -- raw field write "
                            f"instead of plain set_xp, since SetXP silently refuses any decrease "
                            f"(force -> {new_force})"
                        )
                        import asyncio
                        if self._send_delevel is not None:
                            asyncio.create_task(self._send_delevel(write_level, expected, new_force))
                        else:
                            logger.warning("[reconcile] delevel needed but no send_delevel callback wired up")
                    else:
                        logger.info(f"[reconcile] area-transition xp clamp: {current} -> {expected}")
                        import asyncio
                        asyncio.create_task(self._send_apply_value("set_xp", expected))
            return
        if _DEATH_RE.search(event):
            self._cycle_saw_death = True
            return
        if "AP|SKILLREPORT|" in event:
            if self._last_poll_garbage:
                # Don't touch current_skills/companion-cycle rotation/death
                # detection or call _reconcile() at all this cycle -- none
                # of this tick's data is trustworthy (see the empty-
                # NAMEREPORT check above). Leaves _cycle_saw_death/
                # _cycle_companions accumulated rather than clearing them,
                # so anything genuinely captured during this tick (unlikely
                # given the PC object was invalid, but not impossible) is
                # still picked up by the next real cycle instead of lost.
                self._last_poll_garbage = False
                logger.warning("[reconcile] skipping poll cycle -- PC object was momentarily "
                                "invalid (empty NAMEREPORT this tick), not acting on any of it.")
                return
            m = _SKILLREPORT_RE.search(event)
            if m:
                for field, value in zip(_SKILL_FIELDS, m.groups()):
                    self.current_skills[field] = int(value)
            self.last_seen_companions = set(self._cycle_companions)
            self._cycle_companions = set()

            if self._cycle_saw_death and not self._was_dead:
                self._was_dead = True
                logger.info("[reconcile] local death detected -- reporting DeathLink")
                if self._on_death is not None:
                    self._on_death()
            elif not self._cycle_saw_death:
                self._was_dead = False
            self._cycle_saw_death = False

            self._reconcile()

    def _entitled_keys(self) -> typing.Optional[typing.Set[str]]:
        """Companion keys the player is entitled to: the ones whose journal marker ap_ent_<key> reads 10 (written by
        the grant arm in the same script that adds the companion). None while no CREWREPORT has arrived (treat the
        roster as unknown). A companion trapped off (20) is not entitled."""
        if self.current_crew is None:
            return None
        return {k for k, v in self.current_crew.items() if v == _CREW_ENTITLED}

    def _trapped_keys(self) -> typing.Set[str]:
        """Companions trapped off for good: the marker says 20, or the client's own record says so (only ever used to
        stop a re-grant, never to decide a purge)."""
        marked = {k for k, v in (self.current_crew or {}).items() if v >= _CREW_TRAPPED}
        return marked | set(self.trapped_off_companions)

    def _leak_rule_applies(self) -> bool:
        """True when the leak rule may count this report: markers known, nothing busy, not in the Star Forge (its own pass
        handles that) and the Unknown World trip has not begun (story stage km= below _LEAK_STORY_STAGE_BLOCK)."""
        if self.current_roster is None or self.current_crew is None or self.roster_busy or self.roster_in_starforge:
            return False
        if self.roster_story_stage is not None and self.roster_story_stage >= _LEAK_STORY_STAGE_BLOCK:
            return False
        return True

    def _watch_busy_sources(self) -> None:
        """Diagnostics only: logs when a busy source that should be short-lived (see _BUSY_STUCK_BITS) has been set for
        _BUSY_STUCK_SECONDS in a row. Nothing is cleared or changed."""
        mask = self.roster_busy_mask
        stuck = (mask & sum(_BUSY_STUCK_BITS)) if mask else 0
        if not stuck:
            self._busy_flag_since = None
            return
        now = time.time()
        if self._busy_flag_since is None:
            self._busy_flag_since = now
            return
        if now - self._busy_flag_since >= _BUSY_STUCK_SECONDS and now - self._busy_warned_at >= 3 * _BUSY_STUCK_SECONDS:
            names = ", ".join(name for bit, name in _BUSY_STUCK_BITS.items() if stuck & bit)
            logger.warning(f"[watchdog] the roster report has been busy for {int((now - self._busy_flag_since) // 60)} minutes "
                           f"because of: {names} -- roster corrections are paused while it lasts")
            self._busy_warned_at = now

    def _unselectable_entitled(self) -> typing.Set[str]:
        """Entitled companions who are on the roster but cannot be picked on the party screen
        (the report's sel= bit is off). Vanilla scenes switch selectability off (the Dantooine
        Enclave load script does it for Bastila and Carth) and the script that switches it back
        on may be skipped or suppressed by the companion modes, which leaves a companion listed
        and greyed out. Empty when the report carries no selectability or the entitlement is
        unknown. Only entitled companions are touched: an unentitled one is the roster cleanup's
        business, and a vanilla-unselectable companion we have no claim on stays as it is."""
        if self.current_roster is None or self.current_selectable is None:
            return set()
        entitled = self._entitled_keys()
        if entitled is None:
            return set()
        return {k for k in entitled
                if self.current_roster.get(k) and not self.current_selectable.get(k, True)}

    def _starforge_actions(self) -> typing.Dict[str, str]:
        """What the Star Forge pass wants done, {companion key: action}: "purge" (roster +
        party + objects), "unparty" (party + objects, roster kept) or "roster_remove"
        (roster only). Empty unless the player is in a Star Forge module with a known
        roster. Everything in _STARFORGE_PURGE_KEYS that is available and not entitled is
        purged. Bastila, by G_FinalChoice:
          2 light: the boss is a stand-in (sta_bastila), created only if no creature tagged
            Bastila is near, so a companion Bastila must go before that area: purged if not
            entitled, taken out of the party (roster kept) if entitled and in the party.
          1 dark: the real Bastila fights beside the player and speaks in the Star Forge
            scenes until the game's own script (k_psta_pc_j) takes her out of the party,
            so nothing happens until she is out of the party; then a non-entitled one
            leaves the roster (her object keeps standing for the scene)."""
        if not self.roster_in_starforge or not self.current_roster:
            return {}
        # Once Malak is dead the Star Forge pass is over: the epilogue and the ending cutscenes
        # use the party and the game's own Carth stand-in, and nothing is gained by removing
        # anyone then.
        if self.roster_malak_dead:
            return {}
        entitled = self._entitled_keys()
        if entitled is None:
            return {}
        actions: typing.Dict[str, str] = {}
        for key in _STARFORGE_PURGE_KEYS:
            if self.current_roster.get(key) and key not in entitled:
                actions[key] = "purge"
        if self.current_roster.get("bastila"):
            is_entitled = "bastila" in entitled
            if self.roster_final_choice == 2:
                if not is_entitled:
                    actions["bastila"] = "purge"
                elif self.roster_bastila_in_party:
                    actions["bastila"] = "unparty"
            elif self.roster_final_choice == 1:
                if not is_entitled and not self.roster_bastila_in_party:
                    actions["bastila"] = "roster_remove"
        return actions

    def effective_leak_purge_mode(self) -> str:
        """The mode the leak purge acts on right now: "auto" means purge once the Leviathan has been escaped, report only before."""
        if self.leak_purge_mode == "auto":
            return "on" if self.roster_leviathan_done else "log"
        return self.leak_purge_mode

    def _roster_extras(self) -> typing.List[str]:
        """Companions the last ROSTERREPORT shows as available whose entitlement marker is not 10 (never granted by a
        grant arm, or trapped off): the leaks. Empty while the roster or the markers are unknown."""
        if not self.current_roster or self.current_crew is None:
            return []
        return [k for k in _ROSTER_KEYS
                if self.current_roster.get(k) and self.current_crew.get(k, 0) != _CREW_ENTITLED]

    def _staged_arm_stale(self, since: typing.Optional[float]) -> bool:
        """Replaces a pure time.time() - since > TIMEOUT check for every
        staged-arm correction type (ability, skill, PC class, companion
        class, feats, progression items, AP tracker) -- see
        _AREA_CHECK_RE's own comment for why. `since` is None (never sent,
        nothing to go stale) returns False; otherwise a correction only
        counts as possibly lost once a covered area has actually been
        entered AFTER it was sent, giving the orchestrator a real chance
        to flush it. credits deliberately does NOT use this -- its own
        30s timeout and replace (not additive) semantics make a premature
        retry harmless there, unlike every arm this gates."""
        if since is None:
            return False
        entered = self._last_covered_area_entry_time
        return (entered is not None and entered > since
                and time.time() - entered >= _AREA_FLUSH_GRACE_SECONDS)

    def _reconcile(self) -> None:
        import asyncio
        corrections: typing.List[str] = []
        value_corrections: typing.List[typing.Tuple[str, int]] = []
        # Separate from corrections -- a feats correction is a
        # (character_key, feat_ids) pair dispatched via send_feats, not a
        # bare arm_name string like every other correction here.
        feats_corrections: typing.List[typing.Tuple[str, typing.List[int]]] = []

        # Credits (see CreditMode's docstring, and _credit_baseline's own
        # __init__ comment for the full incident writeup this replaced).
        # Full bidirectional clamp under ap_limited/ap_gated, mirroring
        # XP's clamp-down design -- but every poll cycle here (the SEND
        # side, at least -- the actual field write is still area-
        # transition-gated, same as XP would be if it weren't fired
        # directly off the real transition event instead), not gated to a
        # transition itself, since spending is granular enough (shop
        # purchases especially) that waiting for one would be too coarse.
        # xp is deliberately NOT handled here -- see handle_event()'s
        # _AREA_RE branch instead.
        #
        # Baseline tracking runs regardless of credit_mode (even "off"
        # keeps it current, harmless since it's never consulted there).
        current_credits = self.current_scalar.get("credits", 0)
        if self._credit_baseline is None:
            # Bootstrap: trust whatever the game currently reports rather
            # than judging pre-connection/pre-reset history.
            self._credit_baseline = current_credits
        if self._last_observed_credits is not None:
            delta = current_credits - self._last_observed_credits
            if delta < 0:
                # A real decrease -- apply it to baseline directly (not
                # "adopt current_credits as the new baseline" outright),
                # so a cap-increase grant that's still staged waiting on an
                # area transition doesn't get wiped out by an unrelated
                # spend happening in the meantime. The max(...) guard is
                # what makes this safe against the OLD bug's exact failure
                # mode: if the decrease is actually our own stale
                # correction finally landing (current_credits dropping
                # toward baseline from an organically-inflated high, not a
                # real spend at all), current_credits itself is already the
                # correct floor -- applying the raw delta on top of the
                # OLD baseline would otherwise drag it below that floor.
                self._credit_baseline = max(current_credits, self._credit_baseline + delta)
        self._last_observed_credits = current_credits

        if self.credit_mode != 0:  # off means don't touch credits at all
            if self.credit_mode == 2:  # ap_gated
                current_cap = self.expected_scalar.get("credits", 0)
            else:  # ap_limited
                current_cap = self.checked_location_count * self.credit_limiter
            # Grant exactly the NEW headroom since we last accounted for
            # the cap, added on top of the current baseline -- never a
            # fresh "cap minus lifetime spend" recompute, so a later cap
            # increase can never look like it's "restoring" earlier spend.
            cap_increase = max(0, current_cap - self._last_committed_cap)
            if cap_increase > 0:
                self._credit_baseline += cap_increase
                self._last_committed_cap = current_cap

            # Clamp toward baseline in EITHER direction: below it is a
            # deficit to top up, above it is an unauthorized vanilla gain
            # (loot/quest/vendor income) to suppress -- this second half is
            # what actually fulfills CreditMode's "clamp vanilla gains down
            # to an expected total," not just cap the ceiling.
            target = self._credit_baseline
            if target != current_credits:
                # Only (re)send if this is a genuinely NEW target we haven't
                # already requested, or the previous request has gone
                # stale with zero observed progress -- see
                # _CREDITS_INFLIGHT_TIMEOUT_SECONDS's own comment. Without
                # this, an unchanged deficit would re-send the identical
                # "set_credits:X" correction every single 5-second poll for
                # as long as it takes to land.
                stale = (self._credits_inflight_since is not None
                         and time.time() - self._credits_inflight_since > _CREDITS_INFLIGHT_TIMEOUT_SECONDS)
                if self._credits_inflight_target != target or stale:
                    value_corrections.append(("set_credits", target))
                    self._credits_inflight_target = target
                    self._credits_inflight_since = time.time()
            else:
                # Landed (or never diverged) -- clear in-flight tracking so
                # a genuinely NEW future deficit is free to send immediately
                # rather than waiting out a timeout that no longer applies.
                self._credits_inflight_target = None
                self._credits_inflight_since = None

        # Skill reconciliation runs on the TRUE ranks (SKILLBASEREPORT), never
        # on GetSkillRank: that value is rank + ability modifier + effects, so
        # it shifts whenever abilities, gear or combat debuffs change. Against
        # it, a grant tally under-heals a fresh character by the modifier and
        # can never trigger on a trained one, and its constant movement kept
        # clearing the in-flight guard below.
        for key in _SKILL_FIELDS:
            current = self.current_skill_bases.get(key)
            if current is None:
                # No rank report (an extender build that predates it, or the
                # PC object was unresolvable). Fail closed -- there is no safe
                # way to size a correction from the effective value.
                if not self._skill_base_missing_warned and any(self.current_skills.values()):
                    self._skill_base_missing_warned = True
                    logger.warning("[reconcile] skill reconciliation paused -- SKILLREPORT arrived without a "
                                   "SKILLBASEREPORT, so a grant can't be sized against the true rank. Is the "
                                   "installed binkw32.dll the current build?")
                continue
            expected = self._skill_baseline.get(key)
            # Any real movement of the TRUE rank since last cycle means
            # something we dispatched actually landed (or the player naturally
            # trained it) -- either way, stop assuming our old in-flight
            # requests are still outstanding and let the fresh deficit (if
            # any) below decide what's still needed.
            if current != self._prev_skill_bases.get(key):
                self._inflight_skill_count[key] = 0
                self._inflight_skill_since.pop(key, None)
            self._prev_skill_bases[key] = current

            if expected is None:
                # First real rank for this key this connection -- adopt it as
                # the floor, same "don't judge pre-connection history" reasoning
                # as _ability_baseline's own bootstrap.
                self._skill_baseline[key] = current
                continue

            # Staleness, skills only: a request with zero progress is only
            # presumed lost once a covered area has actually been entered
            # since it was sent (see _staged_arm_stale's own comment) --
            # treat it as gone so the deficit below gets a fresh retry.
            since = self._inflight_skill_since.get(key)
            if self._staged_arm_stale(since):
                logger.info(f"[reconcile] {key} in-flight request stale after an area transition with no progress, retrying")
                self._inflight_skill_count[key] = 0
                self._inflight_skill_since.pop(key, None)

            deficit = expected - current
            if deficit > 0:
                arm_name = next(name for name, v in ARM_EFFECT.items() if v[0] == "skill" and v[1] == key)
                amount = next(v[2] for v in ARM_EFFECT.values() if v[0] == "skill" and v[1] == key)
                total_needed = -(-deficit // amount)
                already_inflight = self._inflight_skill_count[key]
                new_needed = total_needed - already_inflight
                if new_needed > 0:
                    for _ in range(new_needed):
                        corrections.append(arm_name)
                    if already_inflight == 0:
                        self._inflight_skill_since[key] = time.time()
                self._inflight_skill_count[key] = max(already_inflight, total_needed)
            else:
                self._inflight_skill_count[key] = 0
                self._inflight_skill_since.pop(key, None)

        # Ability reconciliation -- see _ability_baseline's own comment
        # (__init__) for why this is a bootstrap-then-track-deltas design
        # (like credits), not the zero-floor design skills use above.
        #
        # The baseline lives on the TRUE BASE scale. The poll's effective
        # score (ABILITYREPORT) also moves with item bonuses and temporary
        # effects -- combat debuffs especially -- so a deficit measured
        # against it queues permanent +1 grants for points that were never
        # lost, and every queued grant lands later. The effective score is
        # only the trigger: the true base (ABILITYBASEREPORT) is consulted
        # once the effective score has dropped below the baseline, and the
        # correction is sized from the base.
        for key in _ABILITY_KEYS:
            current = self.current_abilities.get(key, 0)
            base = self.current_ability_bases.get(key)
            if base is None:
                # No base report (an extender build that predates it, or the
                # PC object was unresolvable). Fail closed: without it, a
                # temporary debuff is indistinguishable from a real loss.
                if not self._ability_base_missing_warned and any(self.current_abilities.values()):
                    self._ability_base_missing_warned = True
                    logger.warning("[reconcile] ability reconciliation paused -- ABILITYREPORT arrived "
                                   "without an ABILITYBASEREPORT, so a temporary debuff can't be told "
                                   "from a real loss. Is the installed binkw32.dll the current build?")
                continue
            if self._ability_baseline.get(key) is None:
                # First real report for this key this connection -- adopt
                # the true base as the floor, same "don't judge
                # pre-connection history" reasoning as _credit_baseline's
                # own bootstrap.
                self._ability_baseline[key] = base
                continue
            expected = self._ability_baseline[key]

            base_deficit = expected - base
            if base_deficit <= 0:
                self._ability_inflight_count[key] = 0
                self._ability_inflight_since.pop(key, None)
                continue
            if current >= expected:
                # The base is short but item bonuses cover it, so the
                # effective score hasn't dropped. Nothing to act on yet; if
                # the bonus goes away the effective score drops below the
                # baseline and the check below takes over. In-flight
                # bookkeeping is left alone.
                continue
            deficit = base_deficit

            since = self._ability_inflight_since.get(key)
            if self._staged_arm_stale(since):
                logger.info(f"[reconcile] ability_{key} in-flight request stale after an area transition with no progress, retrying")
                self._ability_inflight_count[key] = 0
                self._ability_inflight_since.pop(key, None)

            arm_name = next(name for name, v in ARM_EFFECT.items() if v[0] == "ability" and v[1] == key)
            already_inflight = self._ability_inflight_count[key]
            new_needed = deficit - already_inflight
            if new_needed > 0:
                for _ in range(new_needed):
                    corrections.append(arm_name)
                if already_inflight == 0:
                    self._ability_inflight_since[key] = time.time()
            self._ability_inflight_count[key] = max(already_inflight, deficit)

        # A companion actually showing up in last_seen_companions means the
        # grant landed -- drop it from in-flight so a LATER genuine deficit
        # (e.g. losing party access somehow) could re-request it.

        # BK Notes Need to test what happens when granting companions when already two in party. Does one get dropped automatically
        # if not dropping a random companion this could cause this to continue to refire.
        # If we can update our delivery system in order to log the deliveries by the game client with a new function This will bypass the need for this and
        # have more authoritative record to rely on then "what is current party" since that could change.
        #
        # Re: the refire-forever concern above -- last_seen_companions is
        # fed by AP|CHECK|COMPANION|<idx> (_COMPANION_RE above), which
        # ap_poll_shared.nss generates from IsAvailableCreature(idx) -- the
        # persistent ROSTER/availability flag, NOT active 3-slot
        # field-party membership. Every companion recruit arm
        # (generate_trampoline_batch.py) calls
        # AddAvailableNPCByTemplate(nNPC, sTemplate) -- which sets that
        # availability flag -- as a SEPARATE, EARLIER statement than
        # AddPartyMember(nNPC, oNPC), the actual active-slot placement
        # attempt. So even if the field party is already full (PC + 2) and
        # AddPartyMember silently fails/no-ops (KOTOR's own vanilla
        # behavior when the 3-slot cap is hit -- it doesn't auto-drop
        # anyone, the player manages swaps via Manage Party), the
        # availability flag is already true regardless, and
        # last_seen_companions correctly shows them as "seen." The tracked
        # signal isn't "who's standing in my active party right now"
        # (which could fluctuate) but "has this companion ever been made
        # available" (which, once true, stays true), so this design should
        # be safe against the refire risk described above.
        # last_seen_companions only gets an entry from a recruit scene or a saved recruit marker, so a companion that
        # arrived through an item arm (no scene) never appears in it. The roster report names who is available right
        # now by slot, so a companion already on the roster counts as present.
        roster_present = ({_ROSTER_NPC_IDX[k] for k, here in self.current_roster.items() if here}
                          if self.current_roster is not None else set())
        self._inflight_companions &= self.expected_companions - self.last_seen_companions - roster_present
        missing_companions = self.expected_companions - self.last_seen_companions - roster_present
        # A trapped-off companion is meant to stay gone: never re-grant them.
        trapped_now = self._trapped_keys()
        missing_companions = {i for i in missing_companions
                              if not any(_ROSTER_NPC_IDX.get(k) == i for k in trapped_now)}
        for npc_idx in missing_companions:
            if npc_idx in self._inflight_companions:
                continue
            arm_name = next(name for name, v in ARM_EFFECT.items() if v[0] == "companion" and v[1] == npc_idx)
            # expected_companions gains this npc_idx the moment the normal
            # delivery pipeline STAGES the send (note_item_received, called
            # right after send_apply/wait_staged succeed) -- well before
            # the game confirms it, which can take up to one area
            # transition. Without this check, a reconciler poll landing in
            # that gap sees "expected but not yet seen" and fires this SAME
            # arm again. Both sends now funnel through send_heavy (see
            # is_heavy_arm/__init__'s own comment) -- KotorClient.
            # py's _queue_heavy serializes them so a duplicate can never
            # land in the same trampoline batch as the original (the actual
            # crash risk), but this check still matters to avoid the waste
            # of queuing a genuinely redundant second recruit at all.
            # Deliberately NOT added to _inflight_companions here (unlike
            # the real send below): once is_awaiting_confirmation's own
            # timeout elapses with the companion still missing, this loop
            # needs to try again on its own next cycle, not stay suppressed
            # forever.
            if self._is_awaiting_confirmation(arm_name):
                continue
            corrections.append(arm_name)
            self._inflight_companions.add(npc_idx)

        # Marker repair: a companion the server says was received (expected_companions) who is on the roster but whose entitlement
        # marker is not 10. That happens when the save is older than the grant (a reload without reconnecting) or something wrote the
        # roster without the marker. The grant arm is idempotent for a companion already on the roster: it writes the marker and
        # makes her selectable without adding anyone, so it is simply re-sent (a correction, so no companion_class follow-up).
        # Same settle rules as the leak purge (not busy, _ROSTER_STABLE_REPORTS consecutive reports), once per area load. A
        # trapped-off companion (marker 20) is never re-granted.
        if (self.current_roster is not None and self.current_crew is not None and not self.roster_busy
                and not self.roster_in_starforge):
            for key in _ROSTER_KEYS:
                npc_idx = _ROSTER_NPC_IDX.get(key)
                if npc_idx not in self.expected_companions or key in trapped_now:
                    continue
                if not self.current_roster.get(key) or self.current_crew.get(key, 0) >= _CREW_ENTITLED:
                    continue
                if self._roster_extra_streak.get(key, 0) < _ROSTER_STABLE_REPORTS:
                    continue
                since = self._marker_repair_since.get(key)
                if (since is not None and not self._staged_arm_stale(since)
                        and time.time() - since < _STAGED_ARM_INFLIGHT_TIMEOUT_SECONDS):
                    continue
                arm_name = next((name for name, v in ARM_EFFECT.items() if v[0] == "companion" and v[1] == npc_idx), None)
                if arm_name is None or self._is_awaiting_confirmation(arm_name):
                    continue
                self._marker_repair_since[key] = time.time()
                logger.warning(f"[reconcile] {key} was received but has no entitlement marker in this save, "
                               f"re-sending her grant to write it")
                corrections.append(arm_name)

        # Leak purge: a companion who is on the roster but whose entitlement marker is not 10 (a scene's temporary staging that was
        # left behind, a vanilla leak, or a companion trapped off) is purged once it has been seen across _LEAK_AREA_ENTRIES area
        # entries and _ROSTER_STABLE_REPORTS settled reports (not busy, not in the Star Forge, Unknown World trip not begun: see
        # _leak_rule_applies). No warm-up and no "after the Leviathan" condition: the Leviathan modules are busy, the Unknown World
        # onwards is skipped, and the markers live in the save so nothing depends on this connection's history. One purge per
        # cycle; a purge already sent is not repeated until a covered area has been entered since (the staged-arm rule) or the
        # staged-arm timeout has passed. Report-only unless the effective mode is "on" (see effective_leak_purge_mode).
        if (self.effective_leak_purge_mode() != "off" and self._send_purge is not None and self._leak_rule_applies()):
            for key in self._roster_extras():
                if self._roster_extra_streak.get(key, 0) < _ROSTER_STABLE_REPORTS:
                    continue
                if self._leak_area_count.get(key, 0) < _LEAK_AREA_ENTRIES:
                    continue
                if _ROSTER_NPC_IDX.get(key) in self.expected_companions and key not in trapped_now:
                    continue  # received from the server: the marker repair above rewrites her marker, she is not a leak
                since = self._purge_inflight_since.get(key)
                if (since is not None and not self._staged_arm_stale(since)
                        and time.time() - since < _STAGED_ARM_INFLIGHT_TIMEOUT_SECONDS):
                    continue
                self._purge_inflight_since[key] = time.time()
                marker = (self.current_crew or {}).get(key, 0)
                why = "a trapped-off marker" if marker >= _CREW_TRAPPED else "no entitlement marker"
                if self.effective_leak_purge_mode() == "log":
                    logger.warning(f"[reconcile] {key} is on the roster with {why} after "
                                   f"{self._leak_area_count.get(key, 0)} area entries (leak purge is log-only, not purging)")
                    continue
                logger.warning(f"[reconcile] {key} is on the roster with {why}, purging")
                asyncio.create_task(self._send_purge(key))
                break

        # Selectability fix: an entitled companion who is listed but unselectable gets the
        # select_companion trap (SetNPCSelectability TRUE). Same settle rules as the cleanup
        # (not busy, 3 consecutive reports, warm-up), one per cycle, no repeat until a covered
        # area has been entered since or the staged-arm timeout has passed.
        if (self.roster_cleanup_mode != "off" and self._send_select is not None
                and self.current_roster is not None and not self.roster_busy
                and not self.roster_in_starforge and self._roster_first_seen is not None
                and time.time() - self._roster_first_seen >= _ROSTER_WARMUP_SECONDS):
            for key in _ROSTER_KEYS:
                if self._unsel_streak.get(key, 0) < _ROSTER_STABLE_REPORTS:
                    continue
                since = self._unsel_inflight_since.get(key)
                if (since is not None and not self._staged_arm_stale(since)
                        and time.time() - since < _STAGED_ARM_INFLIGHT_TIMEOUT_SECONDS):
                    continue
                self._unsel_inflight_since[key] = time.time()
                if self.roster_cleanup_mode == "log":
                    logger.warning(f"[reconcile] {key} is entitled and listed but not selectable "
                                   f"(roster cleanup is log-only, not fixing)")
                    continue
                logger.warning(f"[reconcile] {key} is entitled and listed but not selectable, making selectable")
                asyncio.create_task(self._send_select(key))
                break

        # Star Forge pass (see _starforge_actions): the same settle rules as above (not busy,
        # 3 consecutive reports, warm-up), one action per cycle, and a sent action is not
        # repeated until a covered area has been entered since or the staged-arm timeout
        # has passed. Not one-shot: it only acts while something is wrong, so a later
        # re-add (the epilogue's Carth backfill) is reconciled too.
        if (self.roster_cleanup_mode != "off" and self.current_roster is not None
                and self.roster_in_starforge and not self.roster_busy
                and self._roster_first_seen is not None
                and time.time() - self._roster_first_seen >= _ROSTER_WARMUP_SECONDS):
            sf_actions = self._starforge_actions()
            for key, action in sf_actions.items():
                if self._sf_streak.get(key, 0) < _ROSTER_STABLE_REPORTS:
                    continue
                since = self._sf_inflight_since.get(key)
                if (since is not None and not self._staged_arm_stale(since)
                        and time.time() - since < _STAGED_ARM_INFLIGHT_TIMEOUT_SECONDS):
                    continue
                sender = {"purge": self._send_purge, "unparty": self._send_unparty,
                          "roster_remove": self._send_roster_remove}.get(action)
                if sender is None:
                    continue
                self._sf_inflight_since[key] = time.time()
                if self.roster_cleanup_mode == "log":
                    logger.warning(f"[reconcile] Star Forge: {key} would get {action} "
                                   f"(roster cleanup is log-only, not sending)")
                    continue
                logger.warning(f"[reconcile] Star Forge: {key} is on the roster/party without entitlement "
                               f"or in the way, {action}")
                asyncio.create_task(sender(key))
                break

        # Class self-healing -- PC and companions (DEVELOPMENT_HISTORY.md section 13).
        # Both share the shape
        # already proven above for missing companions: only acts once real
        # state is actually known (classes_known for the PC; a real,
        # non-sentinel COMPANIONCLASSREPORT value for a companion, meaning
        # currently recruited), and defers to _is_awaiting_confirmation so
        # a still-settling send from the NORMAL delivery pipeline (a
        # class_X item just delivered, or companion_class queued right
        # after a recruit) never gets double-sent. This is what makes class
        # correction "settled but the player doesn't have access" self-
        # healing (crash/reload landing on a save from before a class
        # change took) rather than the old one-shot "verify once at
        # delivery time, never again" check has_class() still does for the
        # pre-send guard above.
        if self.classes_known:
            snapshot = compute_entitlement(self)
            if snapshot.pc_class != -1 and self.current_classes.get("baseclass", -1) != snapshot.pc_class:
                target = snapshot.pc_class
                stale = self._staged_arm_stale(self._pc_class_inflight_since)
                if self._pc_class_inflight_target != target or stale:
                    pc_arm = PC_CLASS_CONST_TO_ARM.get(target)
                    if pc_arm is not None and not self._is_awaiting_confirmation(pc_arm):
                        corrections.append(pc_arm)
                        self._pc_class_inflight_target = target
                        self._pc_class_inflight_since = time.time()
            else:
                self._pc_class_inflight_target = None
                self._pc_class_inflight_since = None

            for npc_key, expected_const in snapshot.companion_classes.items():
                current_const = self.current_companion_classes.get(npc_key, -1)
                if current_const == -1:
                    continue  # not currently recruited -- nothing to correct yet
                if current_const == expected_const:
                    self._companion_class_inflight.pop(npc_key, None)
                    self._companion_class_inflight_since.pop(npc_key, None)
                    continue
                since = self._companion_class_inflight_since.get(npc_key)
                stale = self._staged_arm_stale(since)
                if self._companion_class_inflight.get(npc_key) == expected_const and not stale:
                    continue
                class_name = self.companion_class_rolls.get(npc_key)
                if class_name is None:
                    continue
                comp_arm = f"companion_class:{npc_key}:{class_name}"
                if self._is_awaiting_confirmation(comp_arm):
                    continue
                corrections.append(comp_arm)
                self._companion_class_inflight[npc_key] = expected_const
                self._companion_class_inflight_since[npc_key] = time.time()

            # Feats self-healing -- PC and companions (DEVELOPMENT_HISTORY.md section 13).
            # Two independent sources
            # feed "expected" here: expected_feats (recorded, randomized
            # Additional Feats draws -- see note_feats_granted, no formula,
            # it's just the union of every id ever actually decided) and,
            # for anyone CONFIRMED to already be a Jedi class,
            # entitlement.py's JEDI_CLASS_FEATS -- the bundle a class
            # conversion is SUPPOSED to grant alongside the class write
            # itself. Real incident this second source exists for: a
            # companion's class-conversion feat grant is DelayCommand-based
            # (see build_companion_class_block) and can be lost to a crash
            # in that 1s window, and once the class FIELD itself already
            # reads correct, nothing else would ever notice or retry the
            # missing feats -- this closes that gap. Gated on the
            # character's CURRENT class already matching their target (not
            # just classes_known) -- granting Jedi feats to someone who
            # hasn't actually converted yet would be premature.
            for character_key in ["pc"] + _COMPANION_CLASS_KEYS:
                if character_key == "pc":
                    current = self.current_feats
                    confirmed_class = self.current_classes.get("baseclass", -1)
                    target_class = snapshot.pc_class
                else:
                    current = self.current_companion_feats.get(character_key)
                    if current is None:
                        continue  # not currently recruited -- nothing to correct yet
                    confirmed_class = self.current_companion_classes.get(character_key, -1)
                    target_class = snapshot.companion_classes.get(character_key)
                expected = set(self.expected_feats.get(character_key, ()))
                if target_class is not None and target_class != -1 and confirmed_class == target_class:
                    expected |= JEDI_CLASS_FEATS.get(target_class, set())
                if not expected:
                    continue
                missing = expected - current
                if not missing:
                    self._feats_inflight.pop(character_key, None)
                    self._feats_inflight_since.pop(character_key, None)
                    self._feats_attempts.pop(character_key, None)
                    self._feats_gave_up.discard(character_key)
                    continue
                target = frozenset(missing)
                since = self._feats_inflight_since.get(character_key)
                stale = self._staged_arm_stale(since)
                if self._feats_inflight.get(character_key) == target and not stale:
                    continue
                # A grant that never changes what the character holds (the companion is not really there when it runs) would be
                # re-sent on every area load for good. Stop after a few sends of the same set; a different missing set starts over.
                tried, sends = self._feats_attempts.get(character_key, (None, 0))
                if tried != target:
                    sends = 0
                    self._feats_gave_up.discard(character_key)
                if sends >= _FEATS_MAX_SENDS:
                    if character_key not in self._feats_gave_up:
                        self._feats_gave_up.add(character_key)
                        logger.warning(f"[reconcile] {character_key} is still missing feats {sorted(target)} after {sends} sends; "
                                       f"not sending them again unless the missing set changes or the client reconnects")
                    continue
                feats_corrections.append((character_key, sorted(missing)))
                self._feats_attempts[character_key] = (target, sends + 1)
                self._feats_inflight[character_key] = target
                self._feats_inflight_since[character_key] = time.time()

        # Progression-item possession self-healing (see PROGRESSION_ITEM_
        # RESREFS's own comment, entitlement.py) -- narrow, deficit-only:
        # a tracked key is only ever re-granted once it's been sent at
        # least once (expected_progression_items, via note_item_received)
        # AND the current poll confirms it's genuinely missing right now.
        # Independent of classes_known -- these are ordinary inventory
        # items, not gated on any class-conversion state. Light arm (a
        # give_item: send never touches multiclass/party/level-up), so it
        # goes straight into `corrections` alongside skill grants -- no
        # dedicated send callback needed.
        for key in self.expected_progression_items:
            if self.current_progression_items.get(key, False):
                self._progression_item_inflight_since.pop(key, None)
                continue
            since = self._progression_item_inflight_since.get(key)
            stale = self._staged_arm_stale(since)
            if since is not None and not stale:
                continue
            corrections.append(f"give_item:{PROGRESSION_ITEM_RESREFS[key]}")
            self._progression_item_inflight_since[key] = time.time()

        # "Archipelago Tracker" journal quest -- replaces the cosmetic
        # "Connected to..." send_notify messages (removed). Gated on both
        # total_location_count (set once at Connect) and a real poll
        # report already having arrived, so this never acts on an
        # assumed-zero default. Light arm, same as skills/progression
        # items -- goes straight into `corrections`.
        if self.total_location_count > 0 and self.current_ap_tracker_stage is not None:
            percentage = (self.checked_location_count / self.total_location_count) * 100
            expected_stage = next((stage for threshold, stage in _AP_TRACKER_STAGES if percentage >= threshold), 0)
            if expected_stage > self.current_ap_tracker_stage:
                stale = self._staged_arm_stale(self._ap_tracker_inflight_since)
                if self._ap_tracker_inflight_target != expected_stage or stale:
                    corrections.append(f"journal_tracker_{expected_stage}")
                    self._ap_tracker_inflight_target = expected_stage
                    self._ap_tracker_inflight_since = time.time()
            else:
                self._ap_tracker_inflight_target = None
                self._ap_tracker_inflight_since = None

        if corrections or value_corrections or feats_corrections:
            logger.info(f"[reconcile] deficit found -- grants: {corrections}, exact-value: {value_corrections}, "
                        f"feats: {feats_corrections}")
            self.last_corrections = (corrections + [f"{a}={v}" for a, v in value_corrections]
                                      + [f"additional_feats:{k}={ids}" for k, ids in feats_corrections])
            for arm_name in corrections:
                # HEAVY_ARMS/companion_class: corrections (companion
                # recruit, companion class, PC class) MUST go through
                # send_heavy -- see its own __init__ comment. Only skills
                # (the one other kind of correction this loop ever
                # produces) are safe to send directly: they never touch
                # multiclassing/level-up GUI/party membership, so they
                # have no batching-crash risk to serialize against.
                if is_heavy_arm(arm_name):
                    if self._send_heavy is not None:
                        self._send_heavy(arm_name)
                    else:
                        logger.warning(f"[reconcile] heavy correction needed ({arm_name}) but no send_heavy callback wired up")
                else:
                    asyncio.create_task(self._send_apply(arm_name))
            for action, value in value_corrections:
                asyncio.create_task(self._send_apply_value(action, value))
            for character_key, feat_ids in feats_corrections:
                # Light, not heavy -- see send_feats's own __init__
                # comment. Always the exact already-decided missing subset
                # computed above, never a fresh random draw.
                if self._send_feats is not None:
                    asyncio.create_task(self._send_feats(character_key, feat_ids))
                else:
                    logger.warning(f"[reconcile] feats correction needed ({character_key}:{feat_ids}) but no send_feats callback wired up")
