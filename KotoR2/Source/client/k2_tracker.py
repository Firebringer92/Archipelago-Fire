"""Turns the game's report lines (outbox) into location checks, and records the run for later analysis.

Report lines the game sends (absolute truth each time; the client decides what is new):
  Q|<tag>=<stage>,<tag>=<stage>,...   journal digest: every quest that is past stage 0
  V|<module>                          the player entered an area
  R|<slot>                            a companion slot is available (recruited)
  L|<level>                           character level
  A|<alignment>                       alignment 0-100 (100 = light)
  I|<slot>=<value>,...                influence per AVAILABLE companion slot only (GetInfluence reads 0 for an unavailable one)
  O|<tag>,<tag>,...                   quest items currently held
  B|<purchases>|<exchanges>           Bazaar receipt and token counts
  BC|<count>                          Bounty Datapads held (bounty_cards); the nth check fires when the count reaches n
  X|victory                           the story goal was reached (goal defeat_kreia)
Goals: kreia and nihilus come from the game (X|victory, the DefeatDarthNihilus journal quest at 99); level, influence and cult are decided here.
The spec of each location comes from the seed (slot_data["locations"]): its type and what to compare.
"""
import csv
import json
import os
import time
import typing


# The opening: the prologue, Peragus and the Harbinger. When the player lands on Telos (the first area that is neither part of the opening nor the Ebon Hawk), every
# check of the opening is given out, whichever route was taken (what a condensed Peragus skips, or what a player walks past, is not lost). Always on, not an option.
OPENING_MODULES = {"001EBO", "002EBO"}
OPENING_PLANETS = ("Peragus", "Harbinger")
OPENING_RECRUIT_SLOTS = (0, 6, 8)                  # Atton, Kreia, T3-M4: the three story joins of the opening


def in_opening(module: str) -> bool:
    module = module.strip().upper()
    return module in OPENING_MODULES or module[3:] in ("PER", "HAR")


def left_opening(module: str) -> bool:
    """An area after the opening: not the opening itself and not the Ebon Hawk (003-007EBO, where the player waits between scenes)."""
    module = module.strip().upper()
    return bool(module) and not in_opening(module) and module[3:] != "EBO"


class Tracker:
    def __init__(self, locations: typing.Dict[int, dict], checked: typing.Iterable[int] = (), goal: typing.Optional[dict] = None, opening_sweep: bool = True):
        self.goal = goal or {"type": "kreia"}
        self.opening_sweep = opening_sweep
        self.opening_ids: typing.Set[int] = set()
        self.held: typing.Dict[str, int] = {}              # companion items received so far (for the cult_leader goal)
        self.locations = {int(k): v for k, v in locations.items()}
        self.checked: typing.Set[int] = set(int(c) for c in checked)
        self.quest_by_tag: typing.Dict[str, typing.List[int]] = {}
        self.area_by_module: typing.Dict[str, int] = {}
        self.recruit_by_slot: typing.Dict[int, int] = {}
        self.influence_by_slot: typing.Dict[int, int] = {}
        self.level_ids: typing.Dict[int, int] = {}
        self.alignment_ids: typing.Dict[int, int] = {}
        self.bonus_ids: typing.Dict[str, int] = {}
        self.item_by_tag: typing.Dict[str, int] = {}
        self.purchase_ids: typing.Dict[int, int] = {}
        self.exchange_ids: typing.Dict[int, int] = {}
        self.bounty_ids: typing.Dict[int, int] = {}
        self.ever_high = False
        self.ever_low = False
        self.victory = False
        for lid, spec in self.locations.items():
            t = spec["type"]
            if t in ("quest", "questextra"):                   # an additional quest check is finished by the same journal stage as its quest
                self.quest_by_tag.setdefault(str(spec["journal_tag"]), []).append(lid)
            elif t == "area":
                self.area_by_module[spec["module"].upper()] = lid
            elif t == "recruit":
                self.recruit_by_slot[spec["slot"]] = lid
            elif t == "influence":
                self.influence_by_slot[spec["slot"]] = lid
            elif t == "level":
                self.level_ids[spec["level"]] = lid
            elif t == "alignment":
                if "bonus" in spec:
                    self.bonus_ids[spec["bonus"]] = lid
                else:
                    self.alignment_ids[spec["value"]] = lid
            elif t == "bounty":
                self.bounty_ids[spec["count"]] = lid
            elif t == "bazaar":
                (self.purchase_ids if "Purchase" in spec["name"] else self.exchange_ids)[spec["count"]] = lid
        for lid, spec in self.locations.items():          # what leaving the opening gives out: its areas, the quests that live only in it, the three recruits
            t = spec["type"]
            modules = [m for m in str(spec.get("module") or spec.get("modules") or "").split(";") if m]
            if t == "area" and spec.get("planet") in OPENING_PLANETS:
                self.opening_ids.add(lid)
            elif t in ("quest", "questextra") and modules and spec.get("planet") in OPENING_PLANETS and all(in_opening(m) or m == "003EBO" for m in modules):
                self.opening_ids.add(lid)
            elif t == "recruit" and spec.get("slot") in OPENING_RECRUIT_SLOTS:
                self.opening_ids.add(lid)
        # history flags survive a restart through the checked locations
        if self.alignment_ids.get(80) in self.checked:
            self.ever_high = True
        if self.alignment_ids.get(20) in self.checked:
            self.ever_low = True

    def _hit(self, out: typing.Set[int], lid: typing.Optional[int]) -> None:
        if lid is not None and lid not in self.checked:
            out.add(lid)

    def handle(self, line: str) -> typing.Set[int]:
        """New location ids reached by one game line (also marks them checked)."""
        parts = line.split("|")
        kind = parts[0]
        out: typing.Set[int] = set()
        try:
            if kind == "Q":
                for item in parts[1].split(","):
                    tag, _, stage = item.partition("=")
                    stage_n = int(stage)
                    for lid in self.quest_by_tag.get(tag.strip(), ()):
                        spec = self.locations[lid]
                        ends = spec.get("end_values") or []
                        if stage_n >= spec["target"] > 0 or stage_n in ends:
                            self._hit(out, lid)
            elif kind == "V":
                self._hit(out, self.area_by_module.get(parts[1].strip().upper()))
                if self.opening_sweep and left_opening(parts[1]):
                    for lid in self.opening_ids:                # the player has left the opening: everything in it counts
                        self._hit(out, lid)
            elif kind == "R":
                slot = int(parts[1])
                lid = self.recruit_by_slot.get(slot)
                self._hit(out, lid)
                partner = self.locations[lid].get("exclusive_with") if lid is not None else None
                if partner is not None:
                    # policy auto_on_choice: the unchosen side of an exclusive pair fires together with the chosen side
                    self._hit(out, self.recruit_by_slot.get(partner))
            elif kind == "L":
                level = int(parts[1])
                for lv, lid in self.level_ids.items():
                    if level >= lv:
                        self._hit(out, lid)
            elif kind == "A":
                value = int(parts[1])
                for v, lid in self.alignment_ids.items():
                    if (v < 50 and value <= v) or (v > 50 and value >= v):
                        self._hit(out, lid)
                if value >= 80:
                    self.ever_high = True
                if value <= 20:
                    self.ever_low = True
                if self.ever_high and value <= 20:
                    self._hit(out, self.bonus_ids.get("fallen_jedi"))
                if self.ever_low and value >= 80:
                    self._hit(out, self.bonus_ids.get("redeemed_sith"))
            elif kind == "I":
                for item in parts[1].split(","):
                    slot, _, val = item.partition("=")
                    lid = self.influence_by_slot.get(int(slot))
                    if lid is not None:
                        spec = self.locations[lid]
                        v = int(val)
                        if v >= spec["high"] or (0 <= v <= spec["low"]):
                            self._hit(out, lid)
                            partner = spec.get("exclusive_with")
                            if partner is not None:
                                self._hit(out, self.influence_by_slot.get(partner))
            elif kind == "O":
                for tag in parts[1].split(","):
                    self._hit(out, self.item_by_tag.get(tag.strip().lower()))
            elif kind == "B":
                purchases, exchanges = int(parts[1]), int(parts[2])
                for n, lid in self.purchase_ids.items():
                    if purchases >= n:
                        self._hit(out, lid)
                for n, lid in self.exchange_ids.items():
                    if exchanges >= n:
                        self._hit(out, lid)
            elif kind == "BC":
                held = int(parts[1])
                for n, lid in self.bounty_ids.items():
                    if held >= n:
                        self._hit(out, lid)
            elif kind == "X" and len(parts) > 1 and parts[1] == "victory" and self.goal["type"] == "kreia":
                self.victory = True
            if kind == "Q" and self.goal["type"] == "nihilus":
                for item in parts[1].split(","):
                    tag, _, stage = item.partition("=")
                    if tag.strip().lower() == "defeatdarthnihilus" and int(stage) >= 99:
                        self.victory = True
        except (ValueError, IndexError, KeyError):
            pass
        self.checked |= out
        self._check_goal()
        return out

    def note_item(self, name: str) -> None:
        self.held[name] = self.held.get(name, 0) + 1
        self._check_goal()

    def _check_goal(self) -> None:
        """Goals decided from the checks and items the client already knows (the game only reports the story goals)."""
        kind = self.goal["type"]
        if kind == "level":
            lid = self.level_ids.get(self.goal["level"])
            if lid is not None and lid in self.checked:
                self.victory = True
        elif kind == "influence":
            if sum(1 for lid in self.influence_by_slot.values() if lid in self.checked) >= self.goal["count"]:
                self.victory = True
        elif kind == "cult":
            if self.recruit_by_slot and all(lid in self.checked for lid in self.recruit_by_slot.values()):
                need: typing.Dict[str, int] = {}
                for n in self.goal.get("items", []):
                    need[n] = need.get(n, 0) + 1
                if all(self.held.get(n, 0) >= c for n, c in need.items()):
                    self.victory = True


class Recorder:
    """Writes every game line with a timestamp, so a playthrough can be studied afterwards (time per area, where a gate held the player)."""

    def __init__(self, directory: str, name: str):
        os.makedirs(directory, exist_ok=True)
        self.path = os.path.join(directory, name + ".jsonl")
        self.started = time.time()

    def write(self, kind: str, **fields) -> None:
        rec = {"t": round(time.time() - self.started, 1), "wall": time.strftime("%Y-%m-%d %H:%M:%S"), "kind": kind, **fields}
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")
        except OSError:
            pass


class ItemLog:
    """A csv of the plot-flagged items the player has held (the game reports them as IT|tag~name,... when ap_item_log=1), for building the quest-item
    list from play: where each first appeared, whether it is still held, and where it vanished (consumed, handed over, destroyed)."""

    FIELDS = ["tag", "name", "first_module", "first_time", "held", "lost_module", "lost_time"]

    def __init__(self, path: str):
        self.path = path
        self.rows: typing.Dict[str, dict] = {}
        try:
            with open(path, newline="", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    self.rows[r["tag"]] = r
        except (OSError, KeyError):
            self.rows = {}

    @staticmethod
    def parse(payload: str) -> typing.Dict[str, str]:
        out = {}
        for item in payload.split(","):
            tag, _, name = item.partition("~")
            if tag.strip():
                out[tag.strip()] = name.strip()
        return out

    def update(self, held: typing.Dict[str, str], module: str) -> bool:
        """Apply one report. Returns True when the csv changed."""
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        changed = False
        for tag, name in held.items():
            row = self.rows.get(tag)
            if row is None:
                self.rows[tag] = {"tag": tag, "name": name, "first_module": module, "first_time": now, "held": "1", "lost_module": "", "lost_time": ""}
                changed = True
            elif row["held"] != "1":
                row.update(held="1", lost_module="", lost_time="")         # held again
                changed = True
        for tag, row in self.rows.items():
            if tag not in held and row["held"] == "1":
                row.update(held="0", lost_module=module, lost_time=now)
                changed = True
        if changed:
            self.save()
        return changed

    def save(self) -> None:
        try:
            with open(self.path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=self.FIELDS)
                w.writeheader()
                w.writerows(self.rows.values())
        except OSError:
            pass
