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
UNREACHABLE_POLICY = "auto_on_choice"   # when a pair's other side was chosen, the unchosen side's checks fire by themselves (to be confirmed)
OFFSETS = {"quest": 0, "area": 200, "recruit": 300, "level": 320, "alignment": 400, "influence": 420, "bazaar": 440, "questitem": 500}


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
            planet=r["planet"], modules=r["modules"], requires=r["requires"], progression=True, missable=r["missable"] == "yes",
            companion_dependent=r["companion_dependent"])

    with open(os.path.join(ROOT, "data", "area_locations.csv"), newline="", encoding="utf-8") as f:
        arows = [r for r in csv.DictReader(f) if r["used"] == "yes"]
    for i, r in enumerate(arows):
        add("area", i, "Visited: " + clean(r["name"]), module=r["module"], planet=r["planet"], requires=r["requires"], progression=True)

    for i, (name, slot, partner) in enumerate(COMPANIONS):
        add("recruit", i, "Companion Recruited: " + name, slot=slot, exclusive_with=partner, unreachable_policy=UNREACHABLE_POLICY if partner is not None else "", progression=True, only_if_option="companions != none")

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

    # Quest items: the candidates the user has not vetoed (tools/build_quest_items.py). Ids are assigned in the order of that file; once released the
    # order must only grow (append new items at the end, never reorder).
    qi_path = os.path.join(ROOT, "data", "quest_items.json")
    if os.path.exists(qi_path):
        with open(qi_path, encoding="utf-8") as f:
            qitems = [c for c in json.load(f)["items"] if c["verdict"] == "in"]
        for i, c in enumerate(qitems):
            add("questitem", i, "Quest Item: " + clean(c["name"]) + (" [%s]" % c["tag"] if sum(1 for o in qitems if clean(o["name"]) == clean(c["name"])) > 1 else ""),
                tag=c["tag"], modules=";".join(c["modules"]), requires=c["requires"], progression=bool(c["known_requirement"]), consumed=c["consumed_somewhere"])

    names = [l["name"] for l in locs]
    ids = [l["id"] for l in locs]
    assert len(set(names)) == len(names), [n for n in names if names.count(n) > 1]
    assert len(set(ids)) == len(ids)
    out = {"_doc": "Locations of the KOTOR 2 world, generated by tools/build_world_data.py. Quest items come from data/quest_items.json (candidates, pending the user's veto). "
                   "progression=false means the location holds only filler or useful items.",
           "base_id": BASE_ID, "level_max": LEVEL_MAX, "locations": locs}
    with open(os.path.join(ROOT, "data", "locations.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    kinds = {}
    for l in locs:
        kinds[l["type"]] = kinds.get(l["type"], 0) + 1
    print(len(locs), "locations:", kinds)


main()
