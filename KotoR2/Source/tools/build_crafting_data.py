"""Builds the crafting mode's data table from the research output (research/crafting/gear_audit.csv, research/items/tsl_items.json).

  data/crafting.json   the gear the project recipe table adds to the workbench, each with its type: [[resref, type], ...]

Only the audit's REAL gear (obtainable, not plot, not checked by a script or dialogue, not a prop) that the bench can resolve (its template is in the game's common
files) and that no vanilla recipe builds already. Types are the workbench tabs: armor (body armor, robes, clothing), ranged, melee, lightsaber, other (belts, gloves,
masks, bands, stealth units, implants, droid equipment). Only identifiers are written. Re-run after the research is refreshed:
  python tools/build_crafting_data.py
"""
import csv
import json
import os

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

TYPE_OF_GROUP = {
    "Armor": "armor", "Robes and clothing": "armor",
    "Ranged weapons": "ranged", "Melee weapons": "melee", "Lightsabers": "lightsaber",
    "Belts, gloves, masks, bands, stealth units": "other", "Implants": "other", "Droid equipment": "other",
}


def main() -> int:
    with open(os.path.join(ROOT, "research", "items", "tsl_items.json"), encoding="utf-8") as f:
        items = json.load(f)
    gear = []
    with open(os.path.join(ROOT, "research", "crafting", "gear_audit.csv"), encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row["verdict"] != "REAL" or row["craftable_today"]:
                continue
            resref = row["resref"].lower()
            info = items.get(resref)
            if info is None or "chitin" not in info["template_locations"] or row["group"] not in TYPE_OF_GROUP:
                continue
            gear.append([resref, TYPE_OF_GROUP[row["group"]]])
    gear.sort()
    with open(os.path.join(ROOT, "data", "crafting.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump({"gear": gear}, f, separators=(",", ":"))
        f.write("\n")
    counts = {}
    for _, t in gear:
        counts[t] = counts.get(t, 0) + 1
    print("%d gear recipes: %s" % (len(gear), counts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
