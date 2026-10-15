r"""
Placement check for the story-gate Progression System, run against Archipelago spoiler files (single-player KotOR seeds
generated with progression_system on, spoiler level 3).

For every spoiler it rebuilds, from the spoiler's own location -> item list, what a player could reach, and reports:

  1. Reachability: starting with nothing, repeatedly collect every item at every reachable check until nothing changes. Every
     check must end up reachable and every progression item collected.
  2. Self-lock: for each progression item and each companion item, remove just the item at its own check and recompute. If that check is no
     longer reachable, the item sits where it could not be reached without it (directly or through a chain of other items).
  3. Placement invariants, written independently of StoryGates.py:
       - no progression item on the Leviathan, the Unknown World, the Star Forge, the epilogue or the Malak fight;
       - no non-Taris progression item on Taris or the Endar Spire (the player cannot come back to either);
       - no Tatooine / Kashyyyk / Manaan / Korriban progression item on its own planet;
       - no progression or companion item on an open-world star map check.
  4. Sphere of each progression item (the round in which it first becomes collectable), to show the shape of the chain.

The access requirements come from worlds/kotor/StoryGates.py (location_requirements) plus the companion rule in Rules.py
(each companion's Ebon Hawk subplot check needs that companion under ap_gated). They are the same rules the
generator used, so this verifies how the generator APPLIED them and what ended up where; it cannot find a gate the rules
leave out.

  python check_story_gate_spoilers.py <spoiler.txt> [more spoilers...]
Run from the Archipelago folder (or any folder; it adds the Archipelago folder to the import path).
"""
import collections
import os
import re
import sys

ARCH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Archipelago")
sys.path.insert(0, ARCH)

from worlds.kotor.Locations import COMPANION_SUBPLOT_LOCATIONS, location_table  # noqa: E402
from worlds.kotor.StoryGates import location_requirements  # noqa: E402

FAMILIES = {"Taris": "tar", "Dantooine": "dan", "Tatooine": "tat", "Kashyyyk": "kas", "Manaan": "man", "Korriban": "kor",
            "Unknown World": "unk", "Star Forge": "fin"}
TOKEN_RE = re.compile(r"^(Taris|Dantooine|Tatooine|Kashyyyk|Manaan|Korriban|Unknown World|Star Forge) Progression ([123])$")
OWN_PLANET = {"tat": "Tatooine", "kas": "Kashyyyk", "man": "Manaan", "kor": "Korriban"}
FAMILY_SIZE = 3
STAR_MAP_CHECKS = {"Tatooine: Star Map: Tatooine", "Kashyyyk: Star Map: Kashyyyk", "Manaan: Star Map: Manaan",
                   "Korriban: Star Map: Korriban"}


def parse(path):
    text = open(path, encoding="utf-8-sig").read()
    start = text.index("\nLocations:\n") + 1
    header = text[:start]
    ap_gated = "Companion Mode:                  Ap Gated" in header
    body = text[start:]
    body = body[:body.index("Playthrough:")] if "Playthrough:" in body else body
    names = sorted(location_table, key=len, reverse=True)
    placements = {}
    for line in body.splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        for name in names:
            if line.startswith(name + ": "):
                placements[name] = line[len(name) + 2:]
                break
        else:
            placements[line] = None  # unknown line, reported below
    return placements, ap_gated


def requirement_check(loc, held_tokens, held_items, ap_gated):
    data = location_table[loc]
    for fam, step in location_requirements(loc, data):
        if held_tokens[fam] < min(step, FAMILY_SIZE):
            return False
    if ap_gated:
        need = COMPANION_SUBPLOT_LOCATIONS.get(loc)
        if need and need not in held_items:
            return False
    return True


def reach(placements, ap_gated, removed_loc=None):
    """(set of reachable checks, {item: sphere it was first collected in})."""
    held_tokens = collections.Counter()
    held_items = set()
    reached = set()
    sphere_of = {}
    sphere = 0
    changed = True
    while changed:
        changed = False
        new = [loc for loc in placements if loc not in reached and loc in location_table
               and requirement_check(loc, held_tokens, held_items, ap_gated)]
        for loc in new:
            reached.add(loc)
            item = placements[loc]
            if loc == removed_loc or item is None:
                continue
            sphere_of.setdefault(item, sphere)
            held_items.add(item)
            m = TOKEN_RE.match(item)
            if m:
                held_tokens[FAMILIES[m.group(1)]] += 1
            changed = True
        if new:
            sphere += 1
            changed = True if new else changed
    return reached, sphere_of


def planet_of_check(loc):
    """Planet or phase of a check from its name and region only (independent of StoryGates.location_planet)."""
    data = location_table[loc]
    if loc in ("General: The Code of the Sith", "General: Premium Merchant"):
        return "Korriban"  # taught in the academy / sold by the Dreshdae bartender
    name = loc[len("Visited: "):] if loc.startswith("Visited: ") else loc
    for planet in ("Endar Spire", "Taris", "Dantooine", "Tatooine", "Kashyyyk", "Manaan", "Korriban", "Unknown World",
                   "Star Forge", "Leviathan"):
        if name.startswith(planet) or data.region == planet:
            return planet
    if name.startswith("Yavin") or loc in ("Malak Defeated", "Sith Base: The Final Confrontation") or data.region == "Sith Base":
        return "Ending"
    return None


def check_one(path):
    placements, ap_gated = parse(path)
    problems = []
    unknown = [k for k, v in placements.items() if v is None or k not in location_table]
    if unknown:
        problems.append(f"unparsed spoiler lines: {unknown[:3]}")
    reached, sphere_of = reach(placements, ap_gated)
    missing = sorted(set(location_table) & set(placements) - reached)
    if missing:
        problems.append(f"{len(missing)} checks never reachable, e.g. {missing[:4]}")

    token_at = {item: loc for loc, item in placements.items() if item and TOKEN_RE.match(item)}
    if len(token_at) != 8 * FAMILY_SIZE:
        problems.append(f"expected 24 progression items placed, found {len(token_at)}")
    for item, loc in sorted(token_at.items()):
        if item not in sphere_of:
            problems.append(f"{item} is never collected (at {loc})")

    # 2. self-lock for every progression item and companion item
    for loc, item in placements.items():
        if not item or not (TOKEN_RE.match(item) or item.startswith("Companion: ")):
            continue
        r, _ = reach(placements, ap_gated, removed_loc=loc)
        if loc not in r:
            problems.append(f"SELF-LOCK: '{item}' sits at '{loc}', which cannot be reached without it")

    # 3. placement invariants, independent of StoryGates
    for item, loc in token_at.items():
        fam = FAMILIES[TOKEN_RE.match(item).group(1)]
        planet = planet_of_check(loc)
        if planet in ("Leviathan", "Unknown World", "Star Forge", "Ending"):
            problems.append(f"PLACEMENT: '{item}' at '{loc}' ({planet}, no way back)")
        if planet in ("Taris", "Endar Spire") and fam != "tar":
            problems.append(f"PLACEMENT: '{item}' at '{loc}' ({planet}, one-way, not a Taris item)")
        if fam in OWN_PLANET and planet == OWN_PLANET[fam]:
            problems.append(f"PLACEMENT: '{item}' at '{loc}' (its own planet)")
    for loc, item in placements.items():
        if loc in STAR_MAP_CHECKS and item and (TOKEN_RE.match(item) or item.startswith("Companion: ")):
            problems.append(f"PLACEMENT: '{item}' at '{loc}' (a star map check holds no progression item)")
    chain = sorted((sphere_of.get(i, -1), i, planet_of_check(l)) for i, l in token_at.items())
    return problems, chain, reached


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    total = 0
    for path in sys.argv[1:]:
        problems, chain, reached = check_one(path)
        total += len(problems)
        spheres = max((s for s, _, _ in chain), default=0)
        print(f"{os.path.basename(path)}: {'OK' if not problems else str(len(problems)) + ' PROBLEM(S)'}  "
              f"({len(reached)} checks reachable, progression items collected by round {spheres})")
        for p in problems:
            print("   " + p)
    print(f"\n{total} problem(s) in {len(sys.argv) - 1} spoiler(s)")
    sys.exit(1 if total else 0)


if __name__ == "__main__":
    main()
