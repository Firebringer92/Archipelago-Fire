"""
kotor_location_tracker.py -- auto-detects AP location checks from the raw
CHECK|JOURNAL / CHECK|COMPANION / CHECK|AREA events the extender pushes
every poll, replacing manual !ap_check.

Same philosophy as kotor_reconciliation.py: the game just reports honest
raw state every poll (it doesn't know or care what's "already been
checked"), and the CLIENT is the stateful, authoritative side. Rather than
inventing a second "seen" set here, this reads directly off
ctx.checked_locations (CommonContext's own server-confirmed state) so
there's exactly one source of truth for "has this location already fired,"
not two that could drift out of sync.

  journal: fires once GetJournalEntry(tag) reaches journal_target
  companion: fires the first time IsAvailableCreature(idx) is seen true
             (i.e. the moment a companion would first become available --
             recruitment point reached, independent of whether AP has
             actually granted access to them yet)
  area: fires the first time the player enters that specific covered area
"""
from __future__ import annotations

import re
import typing

from worlds.kotor.Locations import location_table

_JOURNAL_RE = re.compile(r"AP\|CHECK\|JOURNAL\|([^|]+)\|value=(-?\d+)")
_COMPANION_RE = re.compile(r"AP\|CHECK\|COMPANION\|(\d+)")
_AREA_RE = re.compile(r"AP\|CHECK\|AREA\|(\d+)")
_ALIGNMENT_RE = re.compile(r"AP\|ALIGNMENT\|(\d+)")
_LEVEL_RE = re.compile(r"AP\|LEVELREPORT\|(\d+)")
_MALAK_RE = re.compile(r"AP\|CHECK\|GOAL\|MALAK_DEAD")

# The 10 real threshold checks -- 50 itself doesn't count (see Options.py-
# adjacent design notes / project memory for the full discussion).
ALIGNMENT_THRESHOLDS = [0, 10, 20, 30, 40, 60, 70, 80, 90, 100]

# Character level 2-20 -- 1 (starting level) doesn't count, same "starting
# value isn't an accomplishment" convention as alignment excluding 50.
LEVEL_THRESHOLDS = list(range(2, 21))


class LocationTracker:
    def __init__(self):
        self._journal_index: typing.Dict[str, typing.Tuple[int, str]] = {}
        self._companion_index: typing.Dict[int, str] = {}
        self._area_index: typing.Dict[int, str] = {}
        self._alignment_index: typing.Dict[int, str] = {}
        self._alignment_bonus_index: typing.Dict[str, str] = {}
        self._level_index: typing.Dict[int, str] = {}
        self._malak_location_name: typing.Optional[str] = None
        for name, data in location_table.items():
            if data.location_type == "journal":
                self._journal_index[data.journal_tag] = (data.journal_target, name)
            elif data.location_type == "companion":
                self._companion_index[data.companion_idx] = name
            elif data.location_type == "area":
                self._area_index[data.area_idx] = name
            elif data.location_type == "alignment":
                self._alignment_index[data.alignment_value] = name
            elif data.location_type == "alignment_bonus":
                self._alignment_bonus_index[data.alignment_bonus] = name
            elif data.location_type == "level":
                self._level_index[data.level_value] = name
            elif data.location_type == "malak_defeated":
                self._malak_location_name = name

        # Alignment crossing state -- unlike the other three location types
        # above (which are pure functions of one event line), this needs
        # memory of the last-seen value across polls. Lost on client
        # restart, same "one process's worth of history" limitation as
        # everything else client-tracked in this project; see
        # _handle_alignment's bootstrap comment for how a reconnect is
        # handled without inventing false crossing-count history.
        self._last_alignment: typing.Optional[int] = None
        self._alignment_reached: typing.Set[int] = set()
        self._alignment_crossings = 0
        self._alignment_ever_high = False  # ever reached 80-100
        self._alignment_ever_low = False  # ever reached 0-20

        # Level crossing state -- same "remember last value across polls"
        # shape as alignment, but simpler: character level only ever
        # increases in this engine (no de-level mechanic), so there's no
        # direction to track, just a high-water mark. Still needs a
        # bootstrap for the same reconnect-mid-playthrough reason alignment
        # does -- a player already at level 10 on first read should
        # immediately get credit for levels 2-10, not have to "re-earn"
        # them by leveling further.
        self._last_level: typing.Optional[int] = None



        # BK Notes -- Need to adjust this so that this is updated based on checks noted on completion
        #If server says has the 80 and 20 checks then this should fire. It shouldn't be in same client session due to disconnects
        #Suggest we log alignment changes in cahracter log same we do with what they have in checks. Our log file needs to help reconcile us
        #
        # Claude reply (2026-09-02): traced this and you're right, it's a
        # real bug, not just a theoretical one. _alignment_ever_high/_low
        # (set above in __init__, flipped true in check_event/
        # _handle_alignment as thresholds are crossed) are plain in-memory
        # instance state on THIS LocationTracker object -- a fresh
        # KotorClient.py process creates a brand-new instance with both
        # False again, with no step anywhere that re-seeds them from
        # already_checked_ids. Concretely: reach Light 100 in session 1
        # (sets _ever_high=True, and the real AP location for it gets
        # checked/persisted server-side correctly), disconnect/restart,
        # reach Dark 0 in session 2 (_ever_low=True, but _ever_high is back
        # to False in the new instance) -- true_balance_reached() returns
        # False forever even though the player legitimately hit both
        # extremes, just in different sessions. This also directly
        # contradicts this file's own stated design philosophy at the top
        # ("reads directly off ctx.checked_locations... so there's exactly
        # one source of truth" -- true_balance_reached() is the one place
        # that doesn't follow that rule. Your fix idea is exactly right:
        # since each alignment extreme already corresponds to a real
        # location id (the 80/90/100 and 0/10/20 threshold locations,
        # already in location_table), true_balance_reached() should check
        # for those ids in already_checked_ids/ctx.checked_locations
        # instead of these two bespoke flags -- that's server-persisted
        # and reconnect-safe by construction, no separate logging
        # mechanism needed. Not fixed here since you asked for notes, not
        # changes -- flagging this as a real, confirmed goal-detection bug
        # for `goal: true_balance` specifically, worth a FutureDesign.md
        # entry and a real fix before that goal option ships to testers.
    def true_balance_reached(self) -> bool:
        """True once the player has reached BOTH alignment extremes at some
        point during this tracked session -- not simultaneously, just each
        at some point (same 80-100/0-20 "extreme" definition already used
        for the fallen_jedi/redeemed_sith bonus checks, not literally exact
        0/100). Used by the true_balance Goal option -- see
        KotorContext._check_goal in KotorClient.py."""
        return self._alignment_ever_high and self._alignment_ever_low


#BK Notes: Future updates should include some inferernce to locations based on mapping of locations. If we know character is in location Y, and we have a log of this character
#Then on reconnect a check by the areas is performed to see what areas would the character had to have gone to get to that location. Then provide them those checks.
#Essentially KotorClient disconnects from game the user keeps playing and is now in says area X they would have had to pass areas A and B which they dont have checks for to get there
#Grant them the check. Note even this methodology isn't perfect. If we can simploy tell the game client to write a log file regardless that we read from constantly (not rely on TCP connection
#This removes need for this brute force mapping
#
# Claude reply (2026-09-02): confirmed this gap is real too -- the AREA
# branch in check_event above only fires on a live AP|CHECK|AREA|<idx>
# event; there's no backfill of any kind, so any area entered while the
# client was disconnected (game kept running, KotorClient.py wasn't) is
# silently never checked, permanently, unless the player happens to
# physically re-enter that same area again later. Your graph-inference
# idea is plausible and there's a real head start for it already in the
# codebase: scripts/build_area_graph.py already produces
# extender/area_trampolines/_graph.json (area adjacency, currently used
# only for arming neighbors in arm_orchestrator.py), so the raw
# connectivity data this would need isn't a from-scratch build. The hard
# part you flagged ("even this methodology isn't perfect") is real,
# though: KOTOR's map isn't a simple tree, so "must have passed through"
# is only unambiguous where there's exactly one path between two covered
# areas -- anywhere with multiple routes, backfilling would have to pick
# a specific path or grant a whole reachable set, either of which can
# over-grant checks the player didn't actually earn. Your alternative (a
# persistent log the game itself writes continuously, independent of the
# TCP connection being up) sidesteps the ambiguity entirely and is the
# more robust fix if it's buildable -- KSE_Diag already writes to kse.log
# unconditionally regardless of client connection state, so the raw data
# to reconcile against on reconnect may already exist without building
# anything new; the question is whether replaying/diffing kse.log's own
# history on reconnect is feasible, which hasn't been investigated. Worth
# a FutureDesign.md entry rather than a quick fix -- this is a real
# architecture decision (graph inference vs. log replay), not a small
# patch.

    def check_event(self, event: str, already_checked_ids: typing.Set[int]) -> typing.List[int]:
        """Returns AP ids for every location this event just newly reached
        (usually 0 or 1, but an alignment jump can cross several 10-point
        lines in one poll). already_checked_ids should be
        ctx.checked_locations (or ctx.locations_checked, for locally-
        queued-but-unconfirmed too)."""
        m = _JOURNAL_RE.search(event)
        if m:
            tag, value = m.group(1), int(m.group(2))
            entry = self._journal_index.get(tag)
            if entry is not None:
                target, name = entry
                if value >= target:
                    loc_id = location_table[name].id
                    if loc_id not in already_checked_ids:
                        return [loc_id]
            return []

        m = _COMPANION_RE.search(event)
        if m:
            idx = int(m.group(1))
            name = self._companion_index.get(idx)
            if name is not None:
                loc_id = location_table[name].id
                if loc_id not in already_checked_ids:
                    return [loc_id]
            return []

        m = _AREA_RE.search(event)
        if m:
            idx = int(m.group(1))
            name = self._area_index.get(idx)
            if name is not None:
                loc_id = location_table[name].id
                if loc_id not in already_checked_ids:
                    return [loc_id]
            return []

        m = _ALIGNMENT_RE.search(event)
        if m:
            return self._handle_alignment(int(m.group(1)), already_checked_ids)

        m = _LEVEL_RE.search(event)
        if m:
            return self._handle_level(int(m.group(1)), already_checked_ids)

        if _MALAK_RE.search(event):
            if self._malak_location_name is not None:
                loc_id = location_table[self._malak_location_name].id
                if loc_id not in already_checked_ids:
                    return [loc_id]
            return []

        return []

    def _handle_level(self, value: int, already_checked_ids: typing.Set[int]) -> typing.List[int]:
        if self._last_level is None:
            # First reading this process -- bootstrap by crediting every
            # threshold up to and including the current level, same
            # reconnect-mid-playthrough reasoning as alignment's bootstrap.
            # Unlike alignment, level only ever increases, so this is just
            # "everything at or below the current value," no range/midpoint
            # needed.
            self._last_level = value
            crossed = [t for t in LEVEL_THRESHOLDS if t <= value]
        else:
            old = self._last_level
            self._last_level = value
            crossed = [t for t in LEVEL_THRESHOLDS if old < t <= value] if value > old else []

        newly_reached_ids = []
        for t in crossed:
            name = self._level_index.get(t)
            if name is not None:
                loc_id = location_table[name].id
                if loc_id not in already_checked_ids:
                    newly_reached_ids.append(loc_id)
        return newly_reached_ids

    def _handle_alignment(self, value: int, already_checked_ids: typing.Set[int]) -> typing.List[int]:
        if self._last_alignment is None:
            # First reading this process -- bootstrap by assuming a
            # monotonic path from neutral (50) to wherever we are now, so a
            # reconnect mid-playthrough doesn't need to re-observe every
            # step to unlock thresholds already passed. Deliberately does
            # NOT add to _alignment_crossings: that counter is about
            # observed oscillation during this tracked session (for the
            # True Neutral bonus), not inferred historical position.
            self._last_alignment = value
            lo, hi = min(50, value), max(50, value)
            crossed = [t for t in ALIGNMENT_THRESHOLDS if lo <= t <= hi]
        else:
            old = self._last_alignment
            self._last_alignment = value
            if value == old:
                crossed = []
            else:
                lo, hi = min(old, value), max(old, value)
                if value > old:
                    crossed = [t for t in ALIGNMENT_THRESHOLDS if lo < t <= hi]
                else:
                    crossed = [t for t in ALIGNMENT_THRESHOLDS if lo <= t < hi]
                self._alignment_crossings += len(crossed)

        newly_reached_ids = []
        for t in crossed:
            self._alignment_reached.add(t)
            name = self._alignment_index.get(t)
            if name is not None:
                loc_id = location_table[name].id
                if loc_id not in already_checked_ids:
                    newly_reached_ids.append(loc_id)

        if any(t in self._alignment_reached for t in (80, 90, 100)):
            self._alignment_ever_high = True
        if any(t in self._alignment_reached for t in (0, 10, 20)):
            self._alignment_ever_low = True

        def _add_bonus(key: str, condition: bool):
            if not condition:
                return
            name = self._alignment_bonus_index.get(key)
            if name is None:
                return
            loc_id = location_table[name].id
            if loc_id not in already_checked_ids and loc_id not in newly_reached_ids:
                newly_reached_ids.append(loc_id)

        _add_bonus("true_neutral", self._alignment_crossings >= 6 and 40 <= value <= 60)
        _add_bonus("fallen_jedi", self._alignment_ever_high and value <= 20)
        _add_bonus("redeemed_sith", self._alignment_ever_low and value >= 80)

        return newly_reached_ids
