"""
kotor_location_tracker.py -- auto-detects AP location checks from the raw
CHECK|JOURNAL / CHECK|COMPANION / CHECK|AREA events the extender pushes
every poll, replacing manual /ap_check.

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
  quest_item: fires once the player holds the quest item (matched by tag), or once the alternate journal value is reached
  bazaar_purchase / loot_exchange: fire by count, like the bounty cards (receipt items the Archipelago Bazaar's Jawa gives)
"""
from __future__ import annotations

import re
import typing

from worlds.kotor.Locations import COMPANION_SUBPLOT_LOCATIONS, location_table
from worlds.kotor.StoryGates import location_planet

_JOURNAL_RE = re.compile(r"AP\|CHECK\|JOURNAL\|([^|]+)\|value=(-?\d+)")
_COMPANION_RE = re.compile(r"AP\|CHECK\|COMPANION\|(\d+)")
# Reported by the poll (generate_poll_shared.py's CheckSithArmor) while the Sith armor is held and the quest tar_party has not started.
_SITH_ARMOR_RE = re.compile(r"AP\|SITHARMOR\|1")
# The poll's plot report (ap_poll_shared.nss CheckPlot, printed when the value changes). DAN_JUHANI_PLOT is 3 when Juhani is redeemed and
# 2 when she died in the Dantooine confrontation; Vandar's recruit line (the only thing that reports her recruit check) never plays then.
JUHANI_KILLED_RE = re.compile(r"AP\|CHECK\|PLOT\|DAN_JUHANI_PLOT\|value=2(?!\d)")

# Leaving Taris: stage 99 of the journal quest of the Ebon Hawk's escape ("You've managed to escape Taris just in time") is written when the
# Hawk takes off, and the player can never come back to Taris or the Endar Spire. Every check there that has not been reached by then is
# completed (the world lets those checks hold any progression item because of this). It is read from the journal, which lives in the save,
# so a client that was not connected at takeoff still releases them when it next sees the quest.
_TARIS_LEAVE_LOCATION = "Taris: Escaping Taris"
_RELEASED_PLANETS = ("Taris", "Endar Spire")

# Companion key -> the item name COMPANION_SUBPLOT_LOCATIONS lists their personal Ebon Hawk checks under.
_COMPANION_SUBPLOT_ITEM = {
    "bastila": "Companion: Bastila Shan", "canderous": "Companion: Canderous Ordo", "carth": "Companion: Carth Onasi",
    "hk47": "Companion: HK-47", "jolee": "Companion: Jolee Bindo", "juhani": "Companion: Juhani", "mission": "Companion: Mission Vao",
}
_AREA_RE = re.compile(r"AP\|CHECK\|AREA\|(\d+)")
# CheckQuestItems() (generate_poll_shared.py): one line per quest item the player holds, keyed by the item's tag.
_QUESTITEM_RE = re.compile(r"AP\|QUESTITEM\|(\w+)")
# CheckBazaar() (generate_poll_shared.py): the purchase receipts and the exchange receipts the player holds.
_BAZAAR_RE = re.compile(r"AP\|BAZAAR\|(\d+)\|(\d+)")

# Visited-area checks for a module the game never lets a player walk into. The second Black Vulkar Base module has no way in
# (no door or trigger leads to it), so its check is completed once the other two modules of that base have been visited.
# Keyed by the unreachable check -> the checks that must all be done first.
_IMPLIED_AREA_CHECKS = {
    "Visited: Taris - Black Vulkar Base (tar_m10ab)": (
        "Visited: Taris - Black Vulkar Base (tar_m10aa)",
        "Visited: Taris - Black Vulkar Base (tar_m10ac)",
    ),
}
_ALIGNMENT_RE = re.compile(r"AP\|ALIGNMENT\|(\d+)")
_LEVEL_RE = re.compile(r"AP\|LEVELREPORT\|(\d+)")
_MALAK_RE = re.compile(r"AP\|CHECK\|GOAL\|MALAK_DEAD")
# Dedicated single-purpose bounty-count event, replacing an
# AP|INVENTORY|... parse. ap_poll_shared's old CheckInventory() built one
# giant concatenated string across the whole backpack, which silently
# truncates past NWScript's ~512-byte string limit for a large enough
# inventory, cutting ap_bounty_card off mid-word before it ever reached
# kse.log. CheckBountyCount() (see generate_poll_shared.py) scans for
# exactly one
# tag and emits a bounded integer directly, never a per-item string build,
# so it can't hit that limit regardless of backpack size.
_BOUNTY_COUNT_RE = re.compile(r"AP\|BOUNTY\|COUNT\|(\d+)")
# CheckBossDatapads() (generate_poll_shared.py): one line per boss datapad the player holds.
_DATAPAD_RE = re.compile(r"AP\|DATAPAD\|(\w+)")
# CheckVisitedMarkers() (generate_poll_shared.py): the area indexes whose "Location:" marker item the player
# holds, comma separated. Each area's entry script gives the player its marker once, so this credits areas
# entered while the client was not connected.
_AREASVISITED_RE = re.compile(r"AP\|AREASVISITED\|([\d,]+)")

# The 10 real threshold checks -- 50 itself doesn't count as a crossing
# (see Locations.py's alignment location comment).
# Every alignment location: the 10 original thresholds plus the inner 35/45/55/65.
ALIGNMENT_THRESHOLDS = [0, 10, 20, 30, 35, 40, 45, 55, 60, 65, 70, 80, 90, 100]

# Character level 2-20 -- 1 (starting level) doesn't count, same "starting
# value isn't an accomplishment" convention as alignment excluding 50.
LEVEL_THRESHOLDS = list(range(2, 21))

# Additional Enemies bounty cards, 1-40 -- one location per card the
# player is carrying. Plot=1 quest items can't be sold/dropped/destroyed,
# so (like character level) this count only ever goes up -- same
# monotonic high-water-mark shape as _handle_level, just fed from the
# inventory report instead of a level report.
BOUNTY_THRESHOLDS = list(range(1, 41))


def _bounty_card_count(event: str) -> typing.Optional[int]:
    """Returns the current bounty-card count from an AP|BOUNTY|COUNT|<n>
    line, or None if this event isn't a bounty-count report at all (as
    opposed to 0, a real count of zero). See _BOUNTY_COUNT_RE's comment for
    why this replaced the old AP|INVENTORY|... parse."""
    m = _BOUNTY_COUNT_RE.search(event)
    if not m:
        return None
    return int(m.group(1))


class LocationTracker:
    def __init__(self):
        self._journal_index: typing.Dict[str, typing.Tuple[int, str]] = {}
        self._companion_index: typing.Dict[int, str] = {}
        self._area_index: typing.Dict[int, str] = {}
        self._alignment_index: typing.Dict[int, str] = {}
        self._alignment_bonus_index: typing.Dict[str, str] = {}
        self._level_index: typing.Dict[int, str] = {}
        self._malak_location_name: typing.Optional[str] = None
        self._bounty_index: typing.Dict[int, str] = {}
        self._datapad_index: typing.Dict[str, str] = {}
        self._quest_item_index: typing.Dict[str, str] = {}
        self._alt_journal_index: typing.Dict[str, typing.List[typing.Tuple[int, str]]] = {}
        self._bazaar_purchase_index: typing.Dict[int, str] = {}
        self._loot_exchange_index: typing.Dict[int, str] = {}
        # Alternate completions: another journal value that also completes a check (quests the player can make impossible to finish,
        # and the quest item checks whose quest can end without the item).
        for name, data in location_table.items():
            if data.alt_journal_tag:
                self._alt_journal_index.setdefault(data.alt_journal_tag, []).append((data.alt_journal_target, name))
        leave = location_table.get(_TARIS_LEAVE_LOCATION)
        self._taris_leave: typing.Optional[typing.Tuple[str, int]] = (leave.journal_tag, leave.journal_target) if leave else None
        self._taris_release_ids = [data.id for name, data in location_table.items()
                                   if location_planet(name, data) in _RELEASED_PLANETS]
        # The checks the last check_event call added because the player left Taris (not the quest's own check).
        self.last_release_ids: typing.Set[int] = set()
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
            elif data.location_type == "bounty":
                self._bounty_index[data.bounty_value] = name
            elif data.location_type == "datapad":
                self._datapad_index[data.datapad_key] = name
            elif data.location_type == "quest_item":
                for tag in data.quest_item_tags:
                    self._quest_item_index[tag] = name
            elif data.location_type == "bazaar_purchase":
                self._bazaar_purchase_index[data.count_value] = name
            elif data.location_type == "loot_exchange":
                self._loot_exchange_index[data.count_value] = name

        # Alignment crossing state -- unlike the other three location types
        # above (which are pure functions of one event line), this needs
        # memory of the last-seen value across polls. The last value is saved per
        # playthrough by the client (alignment_state()/restore_alignment_state()),
        # so movement made while the client was closed still counts; the high/low
        # extreme flags are read from the server-persisted location checks
        # instead (see _handle_alignment).
        self._last_alignment: typing.Optional[int] = None
        self._alignment_reached: typing.Set[int] = set()
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

        # Bounty-card count state -- same "remember last value across
        # polls, high-water mark only" shape as level, fed from the
        # dedicated AP|BOUNTY|COUNT|<n> event instead of LEVELREPORT (see
        # _bounty_card_count).
        self._last_bounty_count: typing.Optional[int] = None

        # Bazaar receipt counts: the same high-water-mark shape (a receipt is a plot item, so the count only goes up).
        self._last_purchase_count: typing.Optional[int] = None
        self._last_exchange_count: typing.Optional[int] = None

        # BK Notes -- Need to adjust this so that this is updated based on checks noted on completion
        #If server says has the 80 and 20 checks then this should fire. It shouldn't be in same client session due to disconnects
        #Suggest we log alignment changes in cahracter log same we do with what they have in checks. Our log file needs to help reconcile us
        #
        # Confirmed real bug, not persisted across reconnects -- see
        # docs/MODE_DEPENDENCIES.md's "true_balance Goal option" open item
        # for the full failure mode and the fix direction.

    def alignment_state(self) -> dict:
        """What must survive a client restart: the last alignment value seen."""
        return {"last": self._last_alignment}

    def restore_alignment_state(self, state: typing.Optional[dict]) -> None:
        """Called on Connect with this playthrough's saved state (None for a playthrough never seen before, which also wipes any
        state left over from a previously connected one). The next reading is then compared against the saved last value, so
        movement made while the client was closed still counts as crossings along a straight path."""
        self._alignment_reached = set()
        self._alignment_ever_high = False
        self._alignment_ever_low = False
        if state:
            last = state.get("last")  # older saves also hold a "crossings" count, now unused
            self._last_alignment = int(last) if last is not None else None
        else:
            self._last_alignment = None

    def true_balance_reached(self, already_checked_ids: typing.Set[int]) -> bool:
        """True once the player has reached BOTH alignment extremes at some
        point -- not simultaneously, just each at some point (same
        80-100/0-20 "extreme" definition already used for the
        fallen_jedi/redeemed_sith bonus checks, not literally exact
        0/100). Used by the true_balance Goal option -- see
        KotorContext._check_goal in KotorClient.py.

        Checks the real, server-persisted "Alignment: Light Side 80"/
        "Alignment: Dark Side 20" location ids in already_checked_ids
        (same ctx.checked_locations | ctx.locations_checked convention as
        check_event()'s own parameter) rather than
        self._alignment_ever_high/_low -- those are plain in-memory flags
        with no persistence, so a reconnect/restart between reaching one
        extreme and the other used to silently forget the first one,
        making this goal unable to ever complete. Crossing further into
        either extreme (90/100 or 10/0) always also crosses this nearer
        threshold first (see ALIGNMENT_THRESHOLDS), so checking just these
        two ids is equivalent to "ever reached that extreme," not a
        narrower condition."""
        high_id = location_table["Alignment: Light Side 80"].id
        low_id = location_table["Alignment: Dark Side 20"].id
        return high_id in already_checked_ids and low_id in already_checked_ids


# Visited-area checks do not depend on the client being connected: the game creates a marker item per area on first entry, the poll reports
# them (AP|AREASVISITED|...), and the tracker credits every reported area on connect, so areas entered while the client was closed are caught up.

    def checks_for_removed_companion(self, npc_key: str, already_checked_ids: typing.Set[int]) -> typing.List[int]:
        """The personal-subplot checks of a companion who has been trapped off for good (Remove a Companion): they can never be
        reached again, so they are completed instead of holding their items forever. Only checks that exist in this seed and are
        not already done."""
        item = _COMPANION_SUBPLOT_ITEM.get(npc_key)
        if item is None:
            return []
        out = []
        for name, needs in COMPANION_SUBPLOT_LOCATIONS.items():
            if needs != item:
                continue
            data = location_table.get(name)
            if data is None or self._journal_index.get(data.journal_tag, (None, None))[1] != name:
                continue  # not an active check in this seed
            if data.id not in already_checked_ids:
                out.append(data.id)
        return out

    def _with_implied_area_checks(self, new_ids: typing.List[int], already_checked_ids: typing.Set[int]) -> typing.List[int]:
        """Adds each unreachable-area check (see _IMPLIED_AREA_CHECKS) whose required checks are all done, counting the
        ones this same event just reached."""
        done = set(already_checked_ids) | set(new_ids)
        out = list(new_ids)
        for name, required in _IMPLIED_AREA_CHECKS.items():
            data = location_table.get(name)
            if data is None or data.id in done:
                continue
            if all(r in location_table and location_table[r].id in done for r in required):
                out.append(data.id)
                done.add(data.id)
        return out

    def check_event(self, event: str, already_checked_ids: typing.Set[int]) -> typing.List[int]:
        """Returns AP ids for every location this event just newly reached
        (usually 0 or 1, but an alignment jump can cross several 10-point
        lines in one poll). already_checked_ids should be
        ctx.checked_locations (or ctx.locations_checked, for locally-
        queued-but-unconfirmed too)."""
        self.last_release_ids = set()
        if JUHANI_KILLED_RE.search(event):
            # She can never be recruited, so her recruit check and her personal Ebon Hawk checks are completed instead of holding their items.
            out = []
            recruit = location_table["Companion Recruited: Juhani"].id
            if recruit not in already_checked_ids:
                out.append(recruit)
            out.extend(i for i in self.checks_for_removed_companion("juhani", already_checked_ids) if i not in out)
            return out

        if _SITH_ARMOR_RE.search(event):
            # Armor taken before the party invitation: that quest can no longer start, so its check is completed here.
            entry = self._journal_index.get("tar_party")
            if entry is not None:
                loc_id = location_table[entry[1]].id
                if loc_id not in already_checked_ids:
                    return [loc_id]
            return []

        m = _JOURNAL_RE.search(event)
        if m:
            tag, value = m.group(1), int(m.group(2))
            out = []
            entry = self._journal_index.get(tag)
            if entry is not None:
                target, name = entry
                if value >= target:
                    loc_id = location_table[name].id
                    if loc_id not in already_checked_ids:
                        out.append(loc_id)
            for target, name in self._alt_journal_index.get(tag, ()):
                if value >= target:
                    loc_id = location_table[name].id
                    if loc_id not in already_checked_ids and loc_id not in out:
                        out.append(loc_id)
            if self._taris_leave is not None and tag == self._taris_leave[0] and value >= self._taris_leave[1]:
                for loc_id in self._taris_release_ids:
                    if loc_id not in already_checked_ids and loc_id not in out:
                        out.append(loc_id)
                        self.last_release_ids.add(loc_id)
            return out

        m = _COMPANION_RE.search(event)
        if m:
            idx = int(m.group(1))
            name = self._companion_index.get(idx)
            if name is not None:
                loc_id = location_table[name].id
                if loc_id not in already_checked_ids:
                    return [loc_id]
            return []

        m = _AREASVISITED_RE.search(event)
        if m:
            loc_ids = []
            for part in m.group(1).split(","):
                if not part:
                    continue
                name = self._area_index.get(int(part))
                if name is None:
                    continue
                loc_id = location_table[name].id
                if loc_id not in already_checked_ids and loc_id not in loc_ids:
                    loc_ids.append(loc_id)
            return self._with_implied_area_checks(loc_ids, already_checked_ids)

        m = _AREA_RE.search(event)
        if m:
            idx = int(m.group(1))
            name = self._area_index.get(idx)
            new = []
            if name is not None:
                loc_id = location_table[name].id
                if loc_id not in already_checked_ids:
                    new.append(loc_id)
            return self._with_implied_area_checks(new, already_checked_ids)

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

        m = _DATAPAD_RE.search(event)
        if m:
            name = self._datapad_index.get(m.group(1))
            if name is not None:
                loc_id = location_table[name].id
                if loc_id not in already_checked_ids:
                    return [loc_id]
            return []

        m = _QUESTITEM_RE.search(event)
        if m:
            name = self._quest_item_index.get(m.group(1))
            if name is not None:
                loc_id = location_table[name].id
                if loc_id not in already_checked_ids:
                    return [loc_id]
            return []

        m = _BAZAAR_RE.search(event)
        if m:
            return (self._handle_receipt_count("_last_purchase_count", self._bazaar_purchase_index, int(m.group(1)), already_checked_ids)
                    + self._handle_receipt_count("_last_exchange_count", self._loot_exchange_index, int(m.group(2)), already_checked_ids))

        count = _bounty_card_count(event)
        if count is not None:
            return self._handle_bounty_count(count, already_checked_ids)

        return []

    def _handle_receipt_count(self, last_attr: str, index: typing.Dict[int, str], value: int,
                              already_checked_ids: typing.Set[int]) -> typing.List[int]:
        """The Bazaar receipts are plot items, so each count only goes up: the same high-water mark as the bounty cards. A
        reconnect mid-playthrough credits every number up to the current count; the mark never moves down when an earlier save
        is loaded (a reloaded save simply holds fewer receipts)."""
        old = getattr(self, last_attr)
        if old is None:
            crossed = [n for n in index if n <= value]
            setattr(self, last_attr, value)
        else:
            crossed = [n for n in index if old < n <= value] if value > old else []
            if value > old:
                setattr(self, last_attr, value)
        out = []
        for n in sorted(crossed):
            loc_id = location_table[index[n]].id
            if loc_id not in already_checked_ids:
                out.append(loc_id)
        return out

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
            # _last_level must never regress: it's a permanent high-water
            # mark, but reloading an earlier save legitimately drops the
            # real in-game level back down (the comment above's "level
            # only ever increases" is about the CURRENT value across a
            # single continuous playthrough, not across a reload). Letting
            # a decrease overwrite the mark would let re-leveling back up
            # past it recompute the SAME thresholds as "crossed" again.
            # The already_checked_ids guard below catches most of these
            # anyway, but there's no reason to let the mark itself regress
            # at all -- only update it on a genuine new high, exactly like
            # a real high-water mark should behave.
            crossed = [t for t in LEVEL_THRESHOLDS if old < t <= value] if value > old else []
            if value > old:
                self._last_level = value

        newly_reached_ids = []
        for t in crossed:
            name = self._level_index.get(t)
            if name is not None:
                loc_id = location_table[name].id
                if loc_id not in already_checked_ids:
                    newly_reached_ids.append(loc_id)
        return newly_reached_ids

    def _handle_bounty_count(self, value: int, already_checked_ids: typing.Set[int]) -> typing.List[int]:
        """Identical shape to _handle_level -- a plain monotonic high-water
        mark, just counting bounty cards instead of character levels. A
        reconnect mid-playthrough immediately credits every threshold up
        to the current count, same reasoning as level's own bootstrap.
        Same fix as _handle_level applied here too (only advance the mark
        on a genuine new high, never regress it) -- bounty cards can't
        really decrease in practice (Plot=1, can't be sold/dropped/
        destroyed), but there's no reason to trust that guarantee blindly
        when the identical unconditional-overwrite shape just turned out
        to be a real, live bug for level."""
        if self._last_bounty_count is None:
            self._last_bounty_count = value
            crossed = [t for t in BOUNTY_THRESHOLDS if t <= value]
        else:
            old = self._last_bounty_count
            crossed = [t for t in BOUNTY_THRESHOLDS if old < t <= value] if value > old else []
            if value > old:
                self._last_bounty_count = value

        newly_reached_ids = []
        for t in crossed:
            name = self._bounty_index.get(t)
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
            # step to unlock thresholds already passed.
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

        newly_reached_ids = []
        for t in crossed:
            self._alignment_reached.add(t)
            name = self._alignment_index.get(t)
            if name is not None:
                loc_id = location_table[name].id
                if loc_id not in already_checked_ids:
                    newly_reached_ids.append(loc_id)

        # "Ever reached an extreme" comes from the server-persisted location checks (the same ids true_balance_reached() uses), so
        # it survives a client restart; the in-memory flags only cover what was crossed this session.
        high_id = location_table["Alignment: Light Side 80"].id
        low_id = location_table["Alignment: Dark Side 20"].id
        if any(t in self._alignment_reached for t in (80, 90, 100)) or high_id in already_checked_ids:
            self._alignment_ever_high = True
        if any(t in self._alignment_reached for t in (0, 10, 20)) or low_id in already_checked_ids:
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

        _add_bonus("fallen_jedi", self._alignment_ever_high and value <= 20)
        _add_bonus("redeemed_sith", self._alignment_ever_low and value >= 80)

        return newly_reached_ids
