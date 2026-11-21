"""Builds data/locations.json: every location of the KOTOR 2 world with a stable id, how the game reports it, what it needs and whether it may hold progression.

Reads the tables made by tools/build_gate_tables.py (run that first) and the research files. The apworld loads this file, so a change to a gate or a
check family is a change to the data, not to the world code. Draft: ids are assigned by order within each family and must be frozen before any release.

  python tools/build_world_data.py
"""
import csv
import json
import os

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
BASE_ID = 2_600_000          # world id base for KOTOR 2 (K1 uses its own base); every location id is BASE_ID + offset
LEVEL_MAX = 50
ALIGN_CROSSINGS = [0, 10, 20, 30, 35, 40, 45, 55, 60, 65, 70, 80, 90, 100]   # K1 values, never 50
# Companions: (display name, slot, slot of the exclusive partner or None). One recruit check and one influence check per companion (12 each).
# Mira/Hanharr and Handmaiden/Disciple cannot both be recruited in the vanilla story (a choice, or the player's gender), so in a seed where the story decides
# only one side of a pair can fire; see unreachable_policy below.
COMPANIONS = [
    ("Atton Rand", 0, None), ("Bao-Dur", 1, None), ("Mandalore", 2, None), ("G0-T0", 3, None), ("Handmaiden", 4, 11), ("HK-47", 5, None),
    ("Kreia", 6, None), ("Mira", 7, 10), ("T3-M4", 8, None), ("Visas Marr", 9, None), ("Hanharr", 10, 7), ("Disciple", 11, 4),
]
BOUNTY_TOTAL = 40
UNREACHABLE_POLICY = "auto_on_choice"   # when a pair's other side was chosen, the unchosen side's checks fire by themselves (to be confirmed)
OFFSETS = {"quest": 0, "area": 200, "recruit": 300, "level": 320, "alignment": 400, "influence": 420, "bazaar": 440, "bounty": 560, "questextra": 600}
# Additional quest checks: up to three more checks for every quest, fired by the same finish as the quest itself. The player's option says how many of the three a seed uses.
EXTRA_MAX = 3


def clean(text):
    return " ".join(text.replace("<", "").replace(">", "").split())


def main():
    locs = []

    def add(kind, index, name, **fields):
        locs.append({"id": BASE_ID + OFFSETS[kind] + index, "name": name, "type": kind, **fields})

    with open(os.path.join(ROOT, "research", "quests", "quest_review.csv"), newline="", encoding="utf-8") as f:
        review = {r["tag"]: r for r in csv.DictReader(f)}
    with open(os.path.join(ROOT, "data", "location_gate_requirements.csv"), newline="", encoding="utf-8") as f:
        qrows = [r for r in csv.DictReader(f) if r["token_ok"] == "yes"]
    for i, r in enumerate(qrows):
        q = review[r["tag"]]
        add("quest", i, "Quest: " + clean(r["name"]), journal_tag=q["tag"], target=int(q["chosen_completion"] or 0),
            end_values=[int(v) for v in q["all_end_values"].split() if v.strip().lstrip("-").isdigit()],
            planet=r["planet"], modules=r["modules"], requires=r["requires"], missable=r["missable"] == "yes",
            companion_dependent=r["companion_dependent"],
            # Only a quest the story forces, whoever is in the party, may hold a progression item: a missable quest that is missed, or one that needs a companion who has not
            # arrived, would lose the item for good (docs/GATES_AND_TOKEN_PLACEMENT.md, "Where progression may be placed")
            progression=r["missable"] != "yes" and not r["companion_dependent"])

    with open(os.path.join(ROOT, "data", "area_locations.csv"), newline="", encoding="utf-8") as f:
        arows = [r for r in csv.DictReader(f) if r["used"] == "yes"]
    for i, r in enumerate(arows):
        add("area", i, "Visited: " + clean(r["name"]), module=r["module"], planet=r["planet"], requires=r["requires"], progression="Endgame>=" not in r["requires"])   # an end-game area never holds a progression item

    for i, (name, slot, partner) in enumerate(COMPANIONS):
        add("recruit", i, "Companion Recruited: " + name, slot=slot, exclusive_with=partner, unreachable_policy=UNREACHABLE_POLICY if partner is not None else "",
            progression=partner is None, only_if_option="companions != none")       # one of an exclusive pair is never recruited, so neither may hold a progression item

    for lv in range(2, LEVEL_MAX + 1):
        add("level", lv - 2, "Level %d" % lv, level=lv, progression=False)

    for i, v in enumerate(ALIGN_CROSSINGS):
        side = "Dark Side" if v < 50 else "Light Side"
        add("alignment", i, "Alignment: %s %d" % (side, v), value=v, progression=False)
    add("alignment", len(ALIGN_CROSSINGS), "Alignment: Fallen Jedi", bonus="fallen_jedi", progression=False)
    add("alignment", len(ALIGN_CROSSINGS) + 1, "Alignment: Redeemed Sith", bonus="redeemed_sith", progression=False)

    for i, (name, slot, partner) in enumerate(COMPANIONS):
        add("influence", i, "Influence: " + name, slot=slot, exclusive_with=partner, unreachable_policy=UNREACHABLE_POLICY if partner is not None else "", high=75, low=25, progression=False, only_if_option="companions != none")

    for n in range(1, 6):
        add("bazaar", n - 1, "Archipelago Bazaar: Purchase %d" % n, count=n, progression=False)
    for n in range(1, 21):
        add("bazaar", 4 + n, "Bazaar Token Exchange %d" % n, count=n, progression=False)

    # Bounty Datapads (the K1 "Additional Enemies" cards): forty checks, the nth fires when the player holds n datapads. Which of them a seed has depends on the carriers the
    # world picks (worlds/kotor2/__init__.py), so the access rule is worked out per seed.
    for n in range(1, BOUNTY_TOTAL + 1):
        add("bounty", n - 1, "Bounty Datapad #%d" % n, count=n, progression=False)

    # Additional quest checks: the quest locations again, EXTRA_MAX of each, every one with its own id and finished by the same journal stage. The id of the nth extra of the
    # quest at index i is 600 + 3 * i + (n - 1); once released the order of the quests must only grow.
    for i, l in enumerate([l for l in locs if l["type"] == "quest"]):
        title = l["name"][len("Quest: "):]
        for n in range(1, EXTRA_MAX + 1):
            add("questextra", EXTRA_MAX * i + n - 1, "Additional Quest Check: %s #%d" % (title, n), journal_tag=l["journal_tag"], target=l["target"],
                end_values=l["end_values"], planet=l["planet"], modules=l["modules"], requires=l["requires"], progression=False, missable=l["missable"],
                companion_dependent=l["companion_dependent"], part=n)

    names = [l["name"] for l in locs]
    ids = [l["id"] for l in locs]
    assert len(set(names)) == len(names), [n for n in names if names.count(n) > 1]
    assert len(set(ids)) == len(ids)
    out = {"_doc": "Locations of the KOTOR 2 world, generated by tools/build_world_data.py. Additional quest checks repeat every quest three times; the player's option decides how many count. "
                   "progression=false means the location holds only filler or useful items.",
           "base_id": BASE_ID, "level_max": LEVEL_MAX, "locations": locs}
    with open(os.path.join(ROOT, "data", "locations.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    kinds = {}
    for l in locs:
        kinds[l["type"]] = kinds.get(l["type"], 0) + 1
    print(len(locs), "locations:", kinds)


main()
