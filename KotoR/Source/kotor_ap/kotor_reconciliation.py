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
}

_SKILLREPORT_RE = re.compile(
    r"computeruse=(\d+)\|demolitions=(\d+)\|stealth=(\d+)\|awareness=(\d+)\|"
    r"persuade=(\d+)\|repair=(\d+)\|security=(\d+)\|treatinjury=(\d+)"
)
_SKILL_FIELDS = ["computeruse", "demolitions", "stealth", "awareness", "persuade", "repair", "security", "treatinjury"]

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
_FEATREPORT_RE = re.compile(r"AP\|FEATREPORT\|([\d,]*)")
_POWERREPORT_RE = re.compile(r"AP\|POWERREPORT\|([\d,]*)")

# arm_name -> current_classes key, for the has_class() pre-send check.
CLASS_ARM_TO_KEY = {
    "class_guardian": "guardian",
    "class_consular": "consular",
    "class_sentinel": "sentinel",
}

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


class ReconciliationTracker:
    """Owns both halves: what the player SHOULD have (fed by ReceivedItems)
    and what the game currently reports having (fed by extender EVENT
    lines), and decides what corrective APPLY calls to send."""

    def __init__(
        self,
        send_apply: typing.Callable[[str], typing.Awaitable[bool]],
        send_apply_value: typing.Callable[[str, int], typing.Awaitable[bool]],
        send_delevel: typing.Optional[typing.Callable[[int, int, int], typing.Awaitable[bool]]] = None,
        on_death: typing.Optional[typing.Callable[[], None]] = None,
    ):
        self._send_apply = send_apply
        self._send_apply_value = send_apply_value
        # Optional so any other ReconciliationTracker construction site
        # (tests, etc.) doesn't need updating just to
        # keep constructing -- the delevel branch below no-ops with a log
        # if this wasn't wired up, same tolerant shape as a send returning
        # False.
        self._send_delevel = send_delevel
        self._on_death = on_death
        self.reset_for_new_connection()

    def reset_for_new_connection(self) -> None:
        """Every field this method sets must be reset on each new
        connection, not just set once in __init__: a single long-running
        KotorClient process that connects to a DIFFERENT slot (e.g.
        WaterKnight after FireKnight) without restarting the process
        would otherwise keep every bit of the PREVIOUS slot's
        reconciliation state -- expected_scalar/expected_skills/
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

        # Credits purchase-detection (see CreditMode's docstring):
        # _last_real_credits is None until the first real
        # CREDITSREPORT arrives, so a fresh connection never computes a
        # false "decrease" against a stale 0 default. Any REAL decrease
        # between polls is treated as a legitimate spend (shops are the
        # only way credits go down in vanilla KOTOR) and accumulated here,
        # permanently, rather than fought -- _reconcile() subtracts this
        # total from whatever credit_mode's raw formula says you should
        # have, so a purchase is never "restored." Mode-agnostic by
        # design: works the same whether the raw expected total comes from
        # an accumulating item count (ap_gated) or a pure function of
        # checked_location_count (ap_limited, which has no accumulator of
        # its own to adjust).
        self._last_real_credits: typing.Optional[int] = None
        self._cumulative_credit_spend = 0

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

        self.expected_scalar: typing.Dict[str, int] = {"credits": 0, "xp": 0}
        self.expected_skills: typing.Dict[str, int] = {f: 0 for f in _SKILL_FIELDS}
        self.expected_companions: set[int] = set()

        self.current_scalar: typing.Dict[str, int] = {"credits": 0, "xp": 0}
        # Guards the _AREA_RE-triggered XP clamp below against firing off
        # current_scalar["xp"]'s bare 0 default before a real XPREPORT has
        # actually landed -- unlike current_level (checked "is not None"
        # before any delevel decision), current_scalar has no such
        # sentinel, and the AREA-triggered clamp runs immediately off the
        # area transition itself rather than waiting for that poll cycle's
        # own reports the way _reconcile()'s credits check effectively
        # does (SKILLREPORT-triggered, always last in a cycle). REAL
        # CRASH CAUSED BY THIS (2026-09-17): extender reconnected mid-
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
        self.current_feats: typing.Set[int] = set()
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
        # wait after connecting). Cleared whenever current_skills/
        # last_seen_companions shows real progress, so a lost/dropped
        # request still self-heals on the next cycle.
        self._inflight_skill_count: typing.Dict[str, int] = {f: 0 for f in _SKILL_FIELDS}
        self._inflight_skill_since: typing.Dict[str, float] = {}
        self._inflight_companions: set[int] = set()
        self._prev_current_skills: typing.Dict[str, int] = {f: 0 for f in _SKILL_FIELDS}

        self.last_corrections: typing.List[str] = []

    def reset_live_state(self) -> None:
        """Resets only the fields that reflect what the game currently
        reports (repopulated fresh by the next real poll) -- NOT
        expected_scalar/expected_skills/expected_companions (what the
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
        self.current_level = None
        self.current_force = {"current": 0, "max": 0}
        self.current_abilities = {"str": 0, "dex": 0, "con": 0, "int": 0, "wis": 0, "cha": 0}
        self.current_feats = set()
        self.current_powers = set()
        self.current_character_name = None
        self._cycle_companions = set()
        self.last_seen_companions = set()
        self._prev_current_skills = {f: 0 for f in _SKILL_FIELDS}
        # Same staleness risk as current_scalar/current_level above --
        # a stale reference point here would misread the freshly-loaded
        # save's real credits as a "spend" (or the reverse), permanently
        # miscounting _cumulative_credit_spend. Re-seeds cleanly on the
        # next real CREDITSREPORT, same as a fresh connection.
        self._last_real_credits = None
        self._credits_inflight_target = None
        self._credits_inflight_since = None
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
        if arm_name == "credits":
            # Amount comes from the seed's credit_item option, not a fixed
            # ARM_EFFECT entry -- same reasoning as "xp" above. Only
            # meaningful under credit_mode's ap_gated (ap_limited derives
            # its expected total from checked_location_count instead, and
            # off doesn't touch credits at all -- see _reconcile()).
            self.expected_scalar["credits"] += self.credit_item
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
            self.expected_skills[key] += amount
        elif kind == "companion":
            _, npc_idx = rule
            self.expected_companions.add(npc_idx)

    def handle_event(self, event: str) -> None:
        """Feed every extender EVENT line here. Parses the report types
        reconciliation cares about; SKILLREPORT is poll_shared's LAST
        report each cycle (see generate_poll_shared.py's main()), so its
        arrival is used as the "this poll's data is complete, reconcile
        now" trigger."""
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
        m = _LEVEL_RE.search(event)
        if m:
            self.current_level = int(m.group(1))
            return
        m = _FORCE_RE.search(event)
        if m:
            self.current_force["current"] = int(m.group(1))
            self.current_force["max"] = int(m.group(2))
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
                    # Native SetXP() silently no-ops if `expected` maps to
                    # a lower level than the player's real current level
                    # -- it refuses to lower XP below the current level's
                    # already-banked threshold. Only possible going DOWN;
                    # an upward correction never
                    # crosses this native limitation, so it's still a
                    # plain set_xp. current_level is None until the first
                    # LEVELREPORT poll arrives -- falls back to plain
                    # set_xp until then rather than guessing.
                    target_level = _level_for_xp(expected)
                    needs_delevel = (
                        expected < current
                        and self.current_level is not None
                        and target_level < self.current_level
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
                        new_force = -1
                        if has_jedi and self.current_level:
                            new_force = round(
                                self.current_force["current"] * target_level / self.current_level
                            )
                        logger.info(
                            f"[reconcile] SetXP gap detected (level {self.current_level} -> "
                            f"{target_level}, xp {current} -> {expected}) -- delevel correction "
                            f"instead of plain set_xp (force -> {new_force})"
                        )
                        import asyncio
                        if self._send_delevel is not None:
                            asyncio.create_task(self._send_delevel(target_level, expected, new_force))
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

    def _reconcile(self) -> None:
        import asyncio
        corrections: typing.List[str] = []
        value_corrections: typing.List[typing.Tuple[str, int]] = []

        # Credits (see CreditMode's docstring): full
        # bidirectional clamp under ap_limited/ap_gated, mirroring XP's
        # clamp-down design -- but every poll cycle here, not gated to an
        # area transition, since spending is granular enough (shop
        # purchases especially) that waiting for a transition would be too
        # coarse. xp is deliberately NOT handled here -- see
        # handle_event()'s _AREA_RE branch instead.
        #
        # Purchase detection runs regardless of credit_mode (even "off"
        # keeps the spend tracker current, harmless since it's never
        # consulted there): a REAL decrease since the last poll is
        # credits going down, which only happens via spending in vanilla
        # KOTOR -- accumulate it into _cumulative_credit_spend rather than
        # letting the clamp below try to "restore" money just spent.
        current_credits = self.current_scalar.get("credits", 0)
        if self._last_real_credits is not None:
            real_delta = current_credits - self._last_real_credits
            if real_delta < 0:
                self._cumulative_credit_spend += -real_delta
        self._last_real_credits = current_credits

        if self.credit_mode != 0:  # off means don't touch credits at all
            if self.credit_mode == 2:  # ap_gated
                raw_expected_credits = self.expected_scalar.get("credits", 0)
            else:  # ap_limited
                raw_expected_credits = self.checked_location_count * self.credit_limiter
            # Subtracting total lifetime spend (not just this cycle's
            # delta) keeps this correct under EITHER mode: ap_gated's raw
            # total is a persistent accumulator that would otherwise
            # "remember" pre-spend money forever, and ap_limited's raw
            # total is a pure function of progress with no accumulator of
            # its own to adjust -- both need the same permanent deduction.
            expected_credits = max(0, raw_expected_credits - self._cumulative_credit_spend)
            if expected_credits != current_credits:
                # Only (re)send if this is a genuinely NEW target we haven't
                # already requested, or the previous request has gone
                # stale with zero observed progress -- see
                # _CREDITS_INFLIGHT_TIMEOUT_SECONDS's own comment. Without
                # this, an unchanged deficit would re-send the identical
                # "set_credits:X" correction every single 5-second poll for
                # as long as it takes to land.
                stale = (self._credits_inflight_since is not None
                         and time.time() - self._credits_inflight_since > _CREDITS_INFLIGHT_TIMEOUT_SECONDS)
                if self._credits_inflight_target != expected_credits or stale:
                    value_corrections.append(("set_credits", expected_credits))
                    self._credits_inflight_target = expected_credits
                    self._credits_inflight_since = time.time()
            else:
                # Landed (or never diverged) -- clear in-flight tracking so
                # a genuinely NEW future deficit is free to send immediately
                # rather than waiting out a timeout that no longer applies.
                self._credits_inflight_target = None
                self._credits_inflight_since = None

        for key, expected in self.expected_skills.items():
            current = self.current_skills.get(key, 0)
            # Any real movement since last cycle means something we
            # dispatched actually landed (or the player naturally trained
            # it) -- either way, stop assuming our old in-flight requests
            # are still outstanding and let the fresh deficit (if any)
            # below decide what's still needed.
            if current != self._prev_current_skills.get(key, 0):
                self._inflight_skill_count[key] = 0
                self._inflight_skill_since.pop(key, None)
            self._prev_current_skills[key] = current

            # Staleness timeout, skills only: a request that's been
            # in-flight this long with zero progress is presumed lost --
            # treat it as gone so the deficit below gets a fresh retry
            # instead of waiting forever.
            since = self._inflight_skill_since.get(key)
            if since is not None and time.time() - since > _SKILL_INFLIGHT_TIMEOUT_SECONDS:
                logger.info(f"[reconcile] {key} in-flight request timed out with no progress, retrying")
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
        self._inflight_companions &= self.expected_companions - self.last_seen_companions
        missing_companions = self.expected_companions - self.last_seen_companions
        for npc_idx in missing_companions:
            if npc_idx in self._inflight_companions:
                continue
            arm_name = next(name for name, v in ARM_EFFECT.items() if v[0] == "companion" and v[1] == npc_idx)
            corrections.append(arm_name)
            self._inflight_companions.add(npc_idx)

        if corrections or value_corrections:
            logger.info(f"[reconcile] deficit found -- grants: {corrections}, exact-value: {value_corrections}")
            self.last_corrections = corrections + [f"{a}={v}" for a, v in value_corrections]
            for arm_name in corrections:
                asyncio.create_task(self._send_apply(arm_name))
            for action, value in value_corrections:
                asyncio.create_task(self._send_apply_value(action, value))
