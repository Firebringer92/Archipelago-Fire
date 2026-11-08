"""Builds the area randomizer's data table from the research output (research/areas/) and the area table (data/area_locations.csv).

  data/doors.json   the doors and walk-through triggers that the randomizer may re-link, in coupled pairs (a door and its reverse), the module each one is in, the
                    waypoint on its own side where a player arrives through it, the modules the player can reach without any door (the roots), and the story
                    requirements of each pooled module

The pool is the research's scenario S2 (the K1 analogue): everything except the stunt and duplicate modules, the Ebon Hawk variants, the prologue (Peragus and
Harbinger), the Ravager, Malachor and 205TEL, plus the set pieces named below and all of Telos. Only identifiers and numbers are written. Re-run after the research is refreshed:
  python tools/build_door_data.py
"""
import csv
import json
import os

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
R = os.path.join(ROOT, "research", "areas")

STUNT_OR_DUPLICATE = {"107PER", "211TEL", "371NAR", "421DXN", "505OND", "510OND", "154HAR", "352NAR", "603DAN", "950COR",
                      "001EBO", "002EBO", "003EBO", "004EBO", "005EBO", "006EBO", "007EBO"}
PROLOGUE = {"101PER", "102PER", "103PER", "104PER", "105PER", "106PER", "151HAR", "152HAR", "153HAR"}
ENDGAME = {"851NIH", "852NIH", "853NIH", "901MAL", "902MAL", "903MAL", "904MAL", "905MAL", "906MAL", "907MAL", "205TEL"}
# Project additions to the research scenario: the three late-game Citadel copies (they exist only after the Council), the end-of-Dantooine module, Vash's duel and
# the two vision modules, which scripts enter and lock behind the player.
SET_PIECES = {"220TEL", "221TEL", "222TEL", "650DAN", "702KOR", "710KOR", "711KOR"}
# Telos and the Citadel are left out entirely (user decision 2026-11-07): their early game is scripted around the vanilla layout.
TELOS = {m for m in ("201TEL 202TEL 203TEL 204TEL 205TEL 207TEL 208TEL 209TEL 211TEL 220TEL 221TEL 222TEL 231TEL 232TEL 233TEL 261TEL 262TEL").split()}
EXCLUDED = STUNT_OR_DUPLICATE | PROLOGUE | ENDGAME | SET_PIECES | TELOS
# Modules the player reaches without any door: the landing of each planet from the galaxy map, and Onderon, which the guides on Dxun take the player to.
ROOTS = ["301NAR", "401DXN", "501OND", "601DAN", "701KOR"]


def parse_requires(text):
    out = {}
    for part in (text or "").split():
        key, _, n = part.partition(">=")
        out[key] = int(n)
    return out


def main() -> int:
    with open(os.path.join(R, "door_graph.json"), encoding="utf-8") as f:
        graph = json.load(f)
    with open(os.path.join(R, "door_pairs.json"), encoding="utf-8") as f:
        pairs = json.load(f)["pairs"]
    pooled = []
    for p in pairs:
        a, b = graph[p["a"]], graph[p["b"]]
        if any(e["module"] in EXCLUDED or e["dest_module"] in EXCLUDED for e in (a, b)):
            continue
        pooled.append((p["a"], p["b"]))
    doors = {}
    for ka, kb in pooled:
        for k, other in ((ka, kb), (kb, ka)):
            e = graph[k]
            # a door's partner links into this door's module: the waypoint it names is where a player arrives next to THIS door
            doors[k] = {"module": e["module"], "list": e["list"], "index": e["index"], "kind": e["kind"], "arrive": graph[other]["dest_waypoint"]}
    modules = sorted({d["module"] for d in doors.values()})
    requires = {}
    with open(os.path.join(ROOT, "data", "area_locations.csv"), encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row["module"] in modules:
                requires[row["module"]] = parse_requires(row["requires"])
    roots = [m for m in ROOTS if m in modules]
    out = {"roots": roots, "modules": modules, "module_requires": {m: requires.get(m, {}) for m in modules},
           "doors": {k: doors[k] for k in sorted(doors)}, "pairs": [list(p) for p in sorted(pooled)]}
    with open(os.path.join(ROOT, "data", "doors.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=0, separators=(",", ":"))
        f.write("\n")
    print("%d pairs (%d doors), %d modules, roots %s, %d doors are triggers" % (len(pooled), len(doors), len(modules), roots, sum(1 for d in doors.values() if d["kind"] != "door")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
