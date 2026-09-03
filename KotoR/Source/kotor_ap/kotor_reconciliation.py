"""
kotor_reconciliation.py -- the client-authoritative half of the design:
the game reports its honest current state every poll (XP, credits, skill
ranks, companion availability -- via ap_poll_shared, already flowing
through the extender bridge as EVENT: lines), and the CLIENT decides
whether that matches what the player should have based on AP items
received so far, re-sending grants to close any deficit.

Scope (deliberately not everything): only arm types whose effect is a
plain, repeatable ADDITIVE increment are auto-corrected here -- credits,
xp, and the 8 skill ranks (each grant is a fixed +N, safe to re-fire to
close an exact gap), and the two companion adds (idempotent: re-adding an
already-present companion is a safe no-op via IsAvailableCreature/
AddPartyMember). Class switches and ability increases are NOT
auto-corrected -- those are closer to one-shot state transitions than
repeatable increments (unlike skills, which have no AP item cap and are
meant to be received many times), and blindly
re-firing them on a mismatch risks doing something the player didn't ask
for (e.g. re-running AddMultiClass) rather than fixing a real deficit.

Deficit-only, by design (see kotor_engine_constraints session decision):
if the game reports MORE than expected (e.g. vanilla XP/credits from
normal play), that's left alone -- no correction fires, since our arms
are all fixed-increment grants, not "set to exact value" (that would need
a parameterized action our current arm system doesn't support).
"""
from __future__ import annotations

import logging
import re
import time
import typing

logger = logging.getLogger("Client")

# arm_name -> reconciliation rule. Only additive, safely-repeatable arms are
# listed -- see module docstring for what's deliberately excluded and why.
# "xp" has no fixed amount here -- see note_item_received(), it uses the
# seed's configured experience_item instead (when experience_mode is
# ap_gated -- ap_limited doesn't use items at all, see handle_event()'s
# _AREA_RE branch), and its correction is handled separately
# (on_area_transition(), not the regular per-poll _reconcile()) since it
# clamps down as well as up.
ARM_EFFECT: typing.Dict[str, tuple] = {
    "credits": ("scalar", "credits", 5000),
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
_CLASSREPORT_RE = re.compile(r"AP\|CLASSREPORT\|guardian=(\d+)\|consular=(\d+)\|sentinel=(\d+)")
# Free-form string field (not a digit run), so bounded by the trailing '"'
# the kse.log wrapper adds instead -- same reasoning as the digit-bounded
# regexes above, just a different terminator since this isn't numeric.
_NAMEREPORT_RE = re.compile(r'AP\|NAMEREPORT\|([^"]+)')

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


class ReconciliationTracker:
    """Owns both halves: what the player SHOULD have (fed by ReceivedItems)
    and what the game currently reports having (fed by extender EVENT
    lines), and decides what corrective APPLY calls to send."""

    def __init__(
        self,
        send_apply: typing.Callable[[str], typing.Awaitable[bool]],
        send_apply_value: typing.Callable[[str, int], typing.Awaitable[bool]],
        on_death: typing.Optional[typing.Callable[[], None]] = None,
    ):
        self._send_apply = send_apply
        self._send_apply_value = send_apply_value
        self._on_death = on_death
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
        self.receive_exp_granting = False  # master switch -- False = pure vanilla XP, no clamping at all
        self.experience_mode = 0  # 0=ap_gated (items), 1=ap_limited (own check count)
        self.experience_limiter = 600
        self.experience_item = 4000
        # Kept fresh by KotorContext on every extender event (own checked-
        # location count) -- only consulted when experience_mode is
        # ap_limited, see handle_event()'s _AREA_RE branch below.
        self.checked_location_count = 0

        self.expected_scalar: typing.Dict[str, int] = {"credits": 0, "xp": 0}
        self.expected_skills: typing.Dict[str, int] = {f: 0 for f in _SKILL_FIELDS}
        self.expected_companions: set[int] = set()

        self.current_scalar: typing.Dict[str, int] = {"credits": 0, "xp": 0}
        self.current_skills: typing.Dict[str, int] = {f: 0 for f in _SKILL_FIELDS}
        # From CLASSREPORT -- real in-game state, not delivery bookkeeping.
        # None until the first report arrives (distinguishes "don't know
        # yet" from "confirmed level 0"), so callers can choose to wait for
        # real data rather than act on an assumed-zero default.
        self.current_classes: typing.Dict[str, int] = {"guardian": 0, "consular": 0, "sentinel": 0}
        self._classes_known = False
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
        # into a real over-grant. Confirmed live: a single starting_persuade
        # boost fired 9 times instead of once during a ~40s pre-transition
        # wait after connecting. Cleared whenever current_skills/
        # last_seen_companions shows real progress, so a lost/dropped
        # request still self-heals on the next cycle.
        self._inflight_skill_count: typing.Dict[str, int] = {f: 0 for f in _SKILL_FIELDS}
        self._inflight_skill_since: typing.Dict[str, float] = {}
        self._inflight_companions: set[int] = set()
        self._prev_current_skills: typing.Dict[str, int] = {f: 0 for f in _SKILL_FIELDS}

        self.last_corrections: typing.List[str] = []

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
            # player's own checked-location count instead, see
            # handle_event()'s _AREA_RE branch). Harmless to keep tracking
            # this even in ap_limited mode -- it's just never read there.
            self.expected_scalar["xp"] += self.experience_item
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
            self._classes_known = True
            return
        m = _NAMEREPORT_RE.search(event)
        if m:
            self.current_character_name = m.group(1)
            return
        if _AREA_RE.search(event):
            # AP|CHECK|AREA|<idx> fires directly from the area's native
            # OnEnter handler (see generate_area_trampolines.py) -- a true
            # one-shot transition edge, not a poll-cycle repeat, so no extra
            # dedup is needed here. This is the ONLY place XP gets corrected
            # when receive_exp_granting is On: once per real area entry,
            # clamped to the exact expected total (both directions -- this
            # is what eliminates vanilla combat/quest XP, unlike credits
            # which can only ever be topped up), fired as a priority action
            # ahead of whatever else that area's trampoline batch applies.
            # experience_mode picks WHERE the expected total comes from:
            # ap_gated sums received Experience Points items (accumulated in
            # expected_scalar via note_item_received); ap_limited derives it
            # directly from the player's own progress (checked_location_count
            # x experience_limiter) instead, independent of anyone's item
            # sends. receive_exp_granting off entirely means don't touch XP
            # at all -- pure vanilla, matching the old "vanilla" mode.
            if self.receive_exp_granting:
                if self.experience_mode == 0:  # ap_gated
                    expected = self.expected_scalar.get("xp", 0)
                else:  # ap_limited
                    expected = self.checked_location_count * self.experience_limiter
                current = self.current_scalar.get("xp", 0)
                if expected != current:
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

        # Credits: exact-value top-up (never reduced -- TakeGoldFromCreature
        # is a confirmed no-op). xp is deliberately NOT handled here -- see
        # handle_event()'s _AREA_RE branch, which corrects it once per real
        # area transition instead of every poll cycle.
        expected_credits = self.expected_scalar.get("credits", 0)
        current_credits = self.current_scalar.get("credits", 0)
        if expected_credits > current_credits:
            value_corrections.append(("set_credits", expected_credits))

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
        # Claude reply (2026-09-02): traced this rather than guessing --
        # last_seen_companions is fed by AP|CHECK|COMPANION|<idx>
        # (_COMPANION_RE above), which ap_poll_shared.nss generates from
        # IsAvailableCreature(idx) -- the persistent ROSTER/availability
        # flag, NOT active 3-slot field-party membership. And every
        # companion recruit arm (generate_trampoline_batch.py) calls
        # AddAvailableNPCByTemplate(nNPC, sTemplate) -- which sets that
        # availability flag -- as a SEPARATE, EARLIER statement than
        # AddPartyMember(nNPC, oNPC) -- the actual active-slot placement
        # attempt. So even if the field party is already full (PC + 2) and
        # AddPartyMember silently fails/no-ops (KOTOR's own vanilla
        # behavior when the 3-slot cap is hit -- it doesn't auto-drop
        # anyone, the player manages swaps via Manage Party), the
        # availability flag is already true regardless, and
        # last_seen_companions correctly shows them as "seen." The specific
        # refire-forever risk described above shouldn't actually occur,
        # since the tracked signal isn't "who's standing in my active
        # party right now" (which could fluctuate) but "has this companion
        # ever been made available" (which, once true, stays true). Worth
        # a live test to confirm this reasoning against real engine
        # behavior rather than just the code path, but the design already
        # looks safe against the failure mode described. The "authoritative
        # delivery log via a new game-client function" idea is reasonable
        # as a future improvement regardless, just not urgent given this.
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
