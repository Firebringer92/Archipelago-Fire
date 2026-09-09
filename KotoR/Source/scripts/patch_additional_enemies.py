r"""
Additively places brand-new hostile creatures alongside whatever's
already in a module -- existing enemies/scripts/encounters are NEVER
touched, removed, or replaced, this only adds more. Tester-run locally,
same seed-gated pattern as patch_item_suppression.py/
patch_door_randomizer.py (reads real slot_data written by KotorClient.py
on Connect, not baked into the item pool -- no AP items involved in this
feature at all).

Reads three tables, all precomputed ONCE by
research/enemy_randomization/build_reference_tables.py and checked into
extender/area_trampolines/ (module geometry never changes, so the real
walkmesh/safety search never needs to run again here):

  - _enemy_spawn_points.json (Table A): {module: [{x, y, z, room}, ...]}
    -- exact, already safety-checked (hitradius<=1.0 footprint + the
    risky-anchor buffer) coordinates. This script only ever decides WHICH
    creature goes in each precomputed slot, never WHERE.
  - _enemy_cr_bands.json (Table B): {module: {cr_min, cr_max, cr_avg,
    dominant_category, target_new_enemies, ...}}.
  - _enemy_category_pools.json (Table C): {category: [resref, ...]}.
  - _enemy_safe_pool.json: the full 88-creature safe pool (flat list).

Mode (Options.py's AdditionalEnemies, read from slot_data's
additional_enemies_mode):
  0 off             -- nothing happens, vanilla.
  1 area_appropriate -- draw only from the target module's own
    dominant_category pool (Table C), CR-filtered against that module's
    own real range (see _pick_creature's tolerance).
  2 random_sane     -- draw from the full safe pool, still CR-filtered
    against the module's own range -- more variety than mode 1, same
    difficulty consistency.
  3 fully_random    -- draw from the full safe pool, no CR restriction at
    all -- confirmed live capable of being significantly over/under-tuned
    for wherever it lands.

Uses the real AP seed_name as its own RNG seed (not a fresh random draw
each run) -- the same player reconnecting to the same seed gets the same
placements every time, matching this project's determinism expectations
elsewhere. Falls back to an unseeded RNG with a warning if seed_name
wasn't written (e.g. testing via --force before ever connecting once).

Usage:
  python patch_additional_enemies.py                          -- apply (backs up first)
  python patch_additional_enemies.py --restore                -- restore all patched modules from backup
  python patch_additional_enemies.py --game-dir "D:\...\swkotor"
  python patch_additional_enemies.py --force --mode=<off|area_appropriate|random_sane|fully_random>
    -- skip reading real seed data, apply a manually-chosen mode instead
"""
import json
import math
import os
import random
import shutil
import sys

from pykotor.common.misc import ResRef
from pykotor.extract.installation import Installation
from pykotor.resource.formats.gff import read_gff, write_gff
from pykotor.resource.formats.rim import read_rim, write_rim
from pykotor.resource.generics.git import construct_git, dismantle_git, GITCreature
from pykotor.resource.type import ResourceType

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TABLES_DIR = os.path.join(REPO_ROOT, "extender", "area_trampolines")
SPAWN_POINTS_JSON = os.path.join(TABLES_DIR, "_enemy_spawn_points.json")
CR_BANDS_JSON = os.path.join(TABLES_DIR, "_enemy_cr_bands.json")
CATEGORY_POOLS_JSON = os.path.join(TABLES_DIR, "_enemy_category_pools.json")
SAFE_POOL_JSON = os.path.join(TABLES_DIR, "_enemy_safe_pool.json")
SLOT_DATA_PATH = os.path.join(TABLES_DIR, "_slot_data.json")
BACKUP_DIR = os.path.join(REPO_ROOT, "extender", "backup", "modules")
DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"

MODE_NAMES = {0: "off", 1: "area_appropriate", 2: "random_sane", 3: "fully_random"}
# CR tolerance either side of a module's own real [cr_min, cr_max] range,
# for modes 1/2 -- a hard exact-range match would empty out the smaller
# category pools (Table C) for many modules; this keeps draws roughly
# difficulty-consistent without being so strict placement silently fails.
CR_TOLERANCE = 2.0


def _arg_value(flag, default):
    for i, a in enumerate(sys.argv):
        if a == flag and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
        if a.startswith(flag + "="):
            return a.split("=", 1)[1]
    return default


def restore(game_dir: str):
    if not os.path.isdir(BACKUP_DIR):
        print("No backup directory found -- nothing to restore.")
        return
    mod_dir = os.path.join(game_dir, "modules")
    restored = 0
    for fname in os.listdir(BACKUP_DIR):
        shutil.copy2(os.path.join(BACKUP_DIR, fname), os.path.join(mod_dir, fname))
        restored += 1
        print(f"  restored {fname}")
    print(f"Restored {restored} module RIM(s) from backup.")


def _load_tables():
    missing = [p for p in (SPAWN_POINTS_JSON, CR_BANDS_JSON, CATEGORY_POOLS_JSON, SAFE_POOL_JSON) if not os.path.exists(p)]
    if missing:
        sys.exit("Missing reference table(s):\n" + "\n".join(f"  {p}" for p in missing) +
                  "\nRun research/enemy_randomization/build_reference_tables.py first.")
    with open(SPAWN_POINTS_JSON, encoding="utf-8") as f:
        spawn_points = json.load(f)
    with open(CR_BANDS_JSON, encoding="utf-8") as f:
        cr_bands = json.load(f)
    with open(CATEGORY_POOLS_JSON, encoding="utf-8") as f:
        category_pools = json.load(f)
    with open(SAFE_POOL_JSON, encoding="utf-8") as f:
        safe_pool = json.load(f)
    return spawn_points, cr_bands, category_pools, safe_pool


def _resolve_seed_mode():
    """Mirrors patch_item_suppression.py's _connected_seed_mode() --
    reads additional_enemies_mode/seed_name straight from the real
    slot_data KotorClient.py wrote on the last successful Connect."""
    if not os.path.isfile(SLOT_DATA_PATH):
        return None, None
    try:
        with open(SLOT_DATA_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("additional_enemies_mode", 0), data.get("seed_name")
    except Exception as e:
        print(f"  (couldn't read {SLOT_DATA_PATH}: {e})")
        return None, None


def _creature_cr(installation: Installation, resref: str, cr_cache: dict) -> float:
    if resref not in cr_cache:
        res = installation.resource(resref, ResourceType.UTC)
        cr_cache[resref] = read_gff(res.data).root.get_single("ChallengeRating", 0.0) if res else 0.0
    return cr_cache[resref]


def _pick_creature(pool: list, cr_min: float, cr_max: float, installation: Installation,
                    cr_cache: dict, rng: random.Random) -> str:
    """Filters `pool` to roughly [cr_min - CR_TOLERANCE, cr_max +
    CR_TOLERANCE], falling back to the full unfiltered pool if that
    empties it out (a small category pool can easily have nothing in
    range) -- always returns SOMETHING from `pool` rather than failing,
    since every candidate in `pool` already passed every safety filter
    regardless of CR."""
    if not pool:
        return None
    filtered = [r for r in pool if cr_min - CR_TOLERANCE <= _creature_cr(installation, r, cr_cache) <= cr_max + CR_TOLERANCE]
    return rng.choice(filtered if filtered else pool)


def apply_module(module: str, points: list, band: dict, mode: int, category_pools: dict,
                  safe_pool: list, installation: Installation, cr_cache: dict,
                  rng: random.Random, game_dir: str) -> int:
    mod_dir = os.path.join(game_dir, "modules")
    path = os.path.join(mod_dir, f"{module}.rim")
    if not os.path.exists(path):
        print(f"  {module}: RIM not found, skipping")
        return 0

    cr_min = band.get("cr_min", 1.0)
    cr_max = band.get("cr_max", cr_min)
    if mode == 1:
        pool = category_pools.get(band.get("dominant_category"), safe_pool)
    else:  # 2 (random_sane) and 3 (fully_random) both draw from the full pool -- only the CR filter differs below
        pool = safe_pool

    r = read_rim(path)
    git_res = next((res for res in r if res.restype == ResourceType.GIT), None)
    if git_res is None:
        print(f"  {module}: no GIT resource, skipping")
        return 0
    git = construct_git(read_gff(git_res.data))

    os.makedirs(BACKUP_DIR, exist_ok=True)
    backup_path = os.path.join(BACKUP_DIR, f"{module}.rim")
    if not os.path.exists(backup_path):
        shutil.copy2(path, backup_path)

    placed = 0
    for point in points:
        if mode == 3:
            resref = rng.choice(safe_pool)  # fully_random: no CR filter at all, by design
        else:
            resref = _pick_creature(pool, cr_min, cr_max, installation, cr_cache, rng)
        if resref is None:
            continue
        c = GITCreature(point["x"], point["y"], point["z"])
        c.resref = ResRef(resref)
        c.bearing = rng.uniform(0, 2 * math.pi)
        git.creatures.append(c)
        placed += 1

    if placed == 0:
        return 0

    new_git_data = bytearray()
    write_gff(dismantle_git(git), new_git_data)
    r.set_data(git_res.resref, ResourceType.GIT, bytes(new_git_data))
    write_rim(r, path)
    print(f"  {module}: placed {placed} new creature(s)")
    return placed


def main():
    game_dir = _arg_value("--game-dir", DEFAULT_GAME_DIR)

    if "--restore" in sys.argv:
        restore(game_dir)
        return

    if "--force" not in sys.argv:
        mode, seed_name = _resolve_seed_mode()
        if mode is None:
            print(f"No usable data at {SLOT_DATA_PATH} -- connect once with KotorClient.py first "
                  "(see README.md Step 6), which writes your seed's real additional_enemies_mode "
                  "there on every successful Connect. Otherwise, pass --force with a manually-set mode.")
            return
        print(f"Connected seed resolves to additional_enemies_mode={mode} ({MODE_NAMES.get(mode, '?')}) -- applying.")
    else:
        mode_arg = _arg_value("--mode", "off")
        mode = {v: k for k, v in MODE_NAMES.items()}.get(mode_arg)
        seed_name = None
        if mode is None:
            print(f"--force given but --mode={mode_arg!r} isn't one of {sorted(MODE_NAMES.values())} -- nothing to apply.")
            return

    if mode == 0:
        print("Mode is 'off' -- nothing to place, vanilla is left alone.")
        return

    if not seed_name:
        print("WARNING: no seed_name available (never connected, or --force was used) -- "
              "using an unseeded RNG. Placements will differ every time this is re-run.")
    rng = random.Random(seed_name)

    spawn_points, cr_bands, category_pools, safe_pool = _load_tables()
    installation = Installation(game_dir)
    cr_cache = {}

    total_placed = 0
    print(f"Placing additional enemies across {len(spawn_points)} module(s)...")
    for module, points in spawn_points.items():
        band = cr_bands.get(module, {})
        total_placed += apply_module(module, points, band, mode, category_pools, safe_pool,
                                      installation, cr_cache, rng, game_dir)

    print(f"\nDone. Placed {total_placed} new creature(s) across {len(spawn_points)} module(s).")
    print(f"Backup at {BACKUP_DIR} -- restore via `python patch_additional_enemies.py --restore`.")


if __name__ == "__main__":
    main()
