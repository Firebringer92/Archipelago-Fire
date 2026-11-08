"""Builds the enemy randomizer's data table from the research output (research/enemies/).

  data/enemies.json   per module: the precomputed safe spawn points and the module's challenge-rating band and dominant creature category;
                      the pool of creature templates (challenge rating, category, and where the template comes from)

Only identifiers and numbers are written (module names, resrefs, coordinates, ratings): no names or other game text. Re-run after the research is refreshed:
  python tools/build_enemy_data.py
"""
import csv
import json
import os

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
R = os.path.join(ROOT, "research", "enemies")

# Modules that get no extra creatures: story set pieces where scripted fights, waves or cutscene states would be disturbed (the yacht fight, Vash's duel, the two
# vision modules, the Nihilus fight and the Malachor proving ground). The research marks all of them as combat modules; this list is a project decision.
GENERIC_SPAWN = {"k_def_spawn01", "k_def_spn_t_none", "k_def_spn_t_drd", "k_def_spn_t_jedi", "k_def_grenspn"}
EXCLUDED_MODULES = ["351NAR", "702KOR", "710KOR", "711KOR", "852NIH", "906MAL"]
# Creature templates that are never drawn: found in a live test to look unfinished. n_swoopgang (appearance Swoop_Gang_01) is shown as an untextured white figure.
# Add a template here when a live test shows one that looks or behaves unfinished; the pool is rebuilt without it.
EXCLUDED_TEMPLATES = {"n_swoopgang"}


def main() -> int:
    def load(name):
        with open(os.path.join(R, name), encoding="utf-8") as f:
            return json.load(f)
    points = load("enemy_spawn_points.json")
    bands = load("enemy_cr_bands.json")
    detail = dict(load("enemy_safe_pool_detail.json"))
    modules = {}
    for module in sorted(points):
        if module in EXCLUDED_MODULES or not points[module]:
            continue
        b = bands[module]
        modules[module] = {"cr_min": b["cr_min"], "cr_max": b["cr_max"], "cr_cap": b["cr_max_nonboss"], "category": b["dominant_category"] or "",
                           "points": [[p["x"], p["y"], p["z"]] for p in points[module]]}
    pool = {}
    # The 38 creatures of the research's extended pool whose only problem was a designer tag in the name ({Male 2}, {Replacement 1}, ...): the ones that run only the
    # game's generic spawn scripts are added (project decision 2026-11-07, "extend if the risk is low"). Left out: the Onderon civil-war soldiers and droids (side-bound
    # spawn scripts), a corpse prop, a quest bounty hunter and a door-scene commando.
    extended = {}
    for row in csv.DictReader(open(os.path.join(R, "enemy_candidates_all.csv"), encoding="utf-8", newline="")):
        if (row["resref"] in set(load("enemy_pools_extended.json")["pool"]) and row["resref"] not in detail
                and row["spawn_script"] in GENERIC_SPAWN and not any(t in row["name"] for t in ("{Corpse}", "{CA}", "{TSF Door}"))):
            scope = row["template_scope"]
            home = [m for m in (row["home_modules"] or row["placed_in_modules"]).split("|") if m]      # the archive that holds the template
            extended[row["resref"]] = {"cr": float(row["cr"]), "category": row["category"], "source": "global" if scope == "global" else home[0]}
    for resref, d in sorted(detail.items()):
        if d["template_scope"] == "global":
            source = "global"
        else:
            source = (d["placed_in"] or d["home_modules"])[0]                # the module whose copy of the template is used
        pool[resref] = {"cr": d["cr"], "category": d["category"], "source": source}
    pool.update(extended)
    pool = dict(sorted((k, v) for k, v in pool.items() if k not in EXCLUDED_TEMPLATES))
    with open(os.path.join(ROOT, "data", "enemies.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump({"excluded_modules": EXCLUDED_MODULES, "modules": modules, "pool": pool}, f, indent=0, separators=(",", ":"))
        f.write("\n")
    print("%d modules, %d spawn points, pool %d" % (len(modules), sum(len(m["points"]) for m in modules.values()), len(pool)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
