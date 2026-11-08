"""What the companions' classes should be, and which class orders bring them there (the companion_class, multiclass_companion and level rules).

The game reports every companion who is in the party as "CC|<slot>:<class 1>:<level 1>:<class 2>:<level 2>,..." (class 255 or -1 = no such class). This module compares that
with the plan in the seed's slot data and says what to order; the context sends each order as a dispatcher job "compclass" and reports back by the next CC line.
Nothing is stored: the plan is recomputed from the game's own report, so a loaded older save, a restart or a repeated order all end in the same place.

Rules (user decisions 2026-11-07):
  * a companion with a class assignment (companion_class not default) is brought to the assigned class at the player's level (so there are no pending level-ups);
  * with no assignment, a companion is raised to the player's level only when the experience mode is on (ap_limited or ap_gated); otherwise they level as in the game;
  * multiclass_companion random_class: once the companion has 15 character levels, the second class of the seed is added with one level (skipped when it equals the first);
  * multiclass_companion prestige: the companion's item adds the prestige class of the seed's pair for that companion, once they have 15 levels; the side follows the
    alignment (a neutral alignment picks a random side).
"""
import random
import typing

PRESTIGE_LEVEL = 15
NO_CLASS = (-1, 255)
PRESTIGE_CLASSES = (11, 12, 13, 14, 15, 16)
JEDI_BASE = (3, 4, 5)
# classes whose content is the Force: converting away from them needs the strip mode
NON_FORCE = (0, 1, 2, 6, 7, 9)

Info = typing.Tuple[int, int, int, int]            # class 1, level 1, class 2, level 2


def parse_cc(payload: str) -> typing.Dict[int, Info]:
    """'0:3:5:255:0,6:4:7:255:0' -> {0: (3, 5, 255, 0), 6: (4, 7, 255, 0)}."""
    out: typing.Dict[int, Info] = {}
    for item in payload.split(","):
        parts = item.split(":")
        if len(parts) == 5:
            try:
                slot, c1, l1, c2, l2 = (int(p) for p in parts)
            except ValueError:
                continue
            out[slot] = (c1, l1, c2, l2)
    return out


class CompanionPlanner:
    def __init__(self, slot_data: dict, prestige_slots: typing.Iterable[int] = (), rng: typing.Optional[random.Random] = None):
        self.slot_data = slot_data
        self.options = slot_data.get("options", {})
        self.assigned: typing.Dict[int, dict] = {int(k): v for k, v in (slot_data.get("companion_classes") or {}).items()}
        self.second: typing.Dict[int, int] = {int(k): v for k, v in (slot_data.get("companion_second_class") or {}).items()}
        self.pairs: typing.Dict[int, typing.List[int]] = {int(k): v for k, v in (slot_data.get("companion_prestige_pairs") or {}).items()}
        self.prestige_slots: typing.Set[int] = set(prestige_slots)       # slots whose Companion Prestige item has arrived
        self.rng = rng or random.Random()
        self.extra_slots: typing.Set[int] = {int(e["slot"]) for e in (slot_data.get("extras") or [])}

    def experience_on(self) -> bool:
        return int(self.options.get("experience_mode", 0)) in (1, 2)

    def active(self) -> bool:
        return bool(self.assigned or self.second or self.prestige_slots or self.experience_on() or self.extra_slots)

    def target_level(self, info: Info, player_level: int) -> int:
        """The level the first class should have: the player's level when the plan raises companions, else the level they have."""
        return max(info[1], player_level) if player_level > 0 else info[1]

    def orders(self, party: typing.Dict[int, Info], player_level: int, alignment: int) -> typing.List[typing.Tuple[int, str]]:
        """[(slot, dispatcher arguments)] for the companions in `party`, in the argument shape 'slot:kind:class:level:mode:race:position'."""
        out: typing.List[typing.Tuple[int, str]] = []
        for slot, info in sorted(party.items()):
            c1, l1, c2, l2 = info
            order = self._order_for(slot, info, player_level, alignment)
            if order:
                out.append((slot, order))
        return out

    def _order_for(self, slot: int, info: Info, player_level: int, alignment: int) -> typing.Optional[str]:
        c1, l1, c2, l2 = info
        total = l1 + (l2 if c2 not in NO_CLASS else 0)
        # 0. an extra companion is a level-one shell: raised to the player's level (their class stays)
        if slot in self.extra_slots:
            want = self.target_level(info, player_level)
            return "%d:0:%d:%d:0:0:0" % (slot, c1, want) if l1 < want else None
        # 1. the assigned class (and the player's level), or the level alone
        plan = self.assigned.get(slot)
        want_level = self.target_level(info, player_level)
        if plan is not None:
            if c1 != plan["class"] or l1 < want_level:
                return "%d:0:%d:%d:%d:%d:0" % (slot, plan["class"], want_level, plan.get("mode", 0), plan.get("race", 0))
        elif self.experience_on() and l1 < want_level:
            return "%d:0:%d:%d:0:0:0" % (slot, c1, want_level)
        # 2. the prestige class of the companion's item
        if slot in self.prestige_slots and slot in self.pairs and total >= PRESTIGE_LEVEL and not self._has_prestige(info):
            light, dark = self.pairs[slot]
            side_dark = alignment < 50 or (alignment == 50 and self.rng.random() < 0.5)
            return "%d:1:%d:1:0:0:0" % (slot, dark if side_dark else light)
        # 3. the random second class
        second = self.second.get(slot)
        if second is not None and total >= PRESTIGE_LEVEL and c2 in NO_CLASS and second != c1:
            return "%d:1:%d:1:0:0:0" % (slot, second)
        return None

    @staticmethod
    def _has_prestige(info: Info) -> bool:
        return info[0] in PRESTIGE_CLASSES or info[2] in PRESTIGE_CLASSES
