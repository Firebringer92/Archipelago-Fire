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
    all -- capable of being significantly over/under-tuned for wherever
    it lands.

Bounty cards: whenever mode != off, exactly one of each
module's newly-placed enemies is cloned (never edits the shared vanilla
template it drew from, since that template is likely reused by ordinary
enemies elsewhere) to also drop a shared "Bounty Card" item on death.
AP checks these off purely by counting how many the player is carrying
(see kotor_location_tracker.py's BOUNTY_THRESHOLDS) -- no per-module item
distinction needed. Doubles as a debug signal: a module never awarding
its card is a hard, unambiguous indicator that this script's placement
failed for that module specifically.

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
import subprocess
import sys

from pykotor.common.language import LocalizedString
from pykotor.common.misc import ResRef
from pykotor.extract.installation import Installation
from pykotor.resource.formats.gff import read_gff, write_gff
from pykotor.resource.formats.rim import read_rim, write_rim
from pykotor.resource.generics.git import construct_git, dismantle_git, GITCreature
from pykotor.resource.generics.utc import construct_utc, dismantle_utc
from pykotor.resource.generics.uti import construct_uti, dismantle_uti
from pykotor.resource.type import ResourceType

from nwnnsscomp_path import resolve_nwnnsscomp  # noqa: E402 -- see that module's docstring

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TABLES_DIR = os.path.join(REPO_ROOT, "extender", "area_trampolines")
SRC_DIR = os.path.join(REPO_ROOT, "extender", "scripts_src")
SPAWN_POINTS_JSON = os.path.join(TABLES_DIR, "_enemy_spawn_points.json")
CR_BANDS_JSON = os.path.join(TABLES_DIR, "_enemy_cr_bands.json")
CATEGORY_POOLS_JSON = os.path.join(TABLES_DIR, "_enemy_category_pools.json")
SAFE_POOL_JSON = os.path.join(TABLES_DIR, "_enemy_safe_pool.json")
SLOT_DATA_PATH = os.path.join(TABLES_DIR, "_slot_data.json")
BACKUP_DIR = os.path.join(REPO_ROOT, "extender", "backup", "modules")
DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
NWNNSSCOMP = resolve_nwnnsscomp()

MODE_NAMES = {0: "off", 1: "area_appropriate", 2: "random_sane", 3: "fully_random"}
# CR tolerance BELOW a module's own real cr_min, for modes 1/2 -- a hard
# exact-range match would empty out the smaller category pools (Table C)
# for many modules; loosening the floor keeps draws roughly difficulty-
# consistent without being so strict placement silently fails. Applied to
# the floor only, NOT the ceiling: a weaker-than-expected addition is
# harmless, but a stronger one is exactly what these two modes exist to
# prevent. A symmetric tolerance here was a real, confirmed bug --
# Rakata Warriors (ChallengeRating 8.0, endgame-tier) were passing the
# filter for Taris Sewers (cr_max as low as 6.0) purely because +/-2.0
# on both ends pushed the effective ceiling up to 8.0, wide enough to
# admit them legitimately. cr_max is now a hard ceiling in _pick_creature
# regardless of this tolerance value.
#
# _enemy_cr_bands.json's per-module cr_max is meant to reflect that
# module's TYPICAL native difficulty, not its single hardest outlier.
# tar_m05ab's cr_max was hand-corrected from 10.0 to 4.0 for exactly this
# reason: tar05_stampy (a unique named rancor, CR 10.0) is a one-off boss
# encounter, not representative of the sewer's normal enemies (whose real
# max is 4.0, e.g. tar05_assault001/tar04_gamraidlea). Other single-
# instance high-CR creatures found elsewhere (Carth Onasi, Bandon, Selven,
# generic rank-tier enemies like "Dark Jedi Master"/"Sith Grenadier", etc.)
# were checked and are NOT carved out: their modules' recorded cr_max
# already excludes them, or they're a legitimate difficulty tier rather
# than a unique boss. Only add a similar carveout for another module if a
# specific unique creature is confirmed (via FirstName/resref, not just a
# high CR-to-average ratio) to be inflating that module's cr_max above its
# real typical ceiling.
CR_TOLERANCE = 2.0

# Bounty cards (see kotor_location_tracker.py's BOUNTY_THRESHOLDS and
# Rules.py's NON_PROGRESSION_LOCATION_TYPES): always on whenever mode !=
# off, one card per module, dropped by exactly ONE of that module's
# newly-placed enemies on death. Doubles as a debug signal -- a module
# never awarding its card is a strong, hard indicator that this script's
# placement failed for that module specifically, not just a missed check.
BOUNTY_CARD_RESREF = "ap_bounty_card"
# Was g_i_asthitem001 (the Galactic Coin's own base, BaseItem 65 Aesthetic
# Item) -- that base renders as a blank white icon for this item (the
# Coin's own icon apparently isn't just "whatever
# BaseItem 65 defaults to" -- there's more to it than copying the base
# alone got right). g_i_datapad001 (BaseItem 52, a real vanilla quest
# datapad) is a known-good icon/model AND a better thematic fit for
# "proof of a bounty" than a generic aesthetic trinket. Not
# quest_dependent in gear_items.json (same as before), so still
# automatically exempt from loot_mode destroy/replace suppression.
BOUNTY_CARD_BASE_ITEM = "g_i_datapad001"


def _arg_value(flag, default):
    for i, a in enumerate(sys.argv):
        if a == flag and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
        if a.startswith(flag + "="):
            return a.split("=", 1)[1]
    return default


def restore(game_dir: str):
    override_dir = os.path.join(game_dir, "Override")
    removed = 0
    for fname in os.listdir(override_dir) if os.path.isdir(override_dir) else []:
        lower = fname.lower()
        if lower == f"{BOUNTY_CARD_RESREF}.uti" or lower.startswith("apbnty"):
            os.remove(os.path.join(override_dir, fname))
            removed += 1
    if removed:
        print(f"  removed {removed} bounty-card Override file(s)")

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
    """Filters `pool` to [cr_min - CR_TOLERANCE, cr_max] -- cr_max is a
    HARD ceiling, not loosened by CR_TOLERANCE (see that constant's own
    comment for the real bug this closes: a symmetric tolerance let
    Rakata Warriors, CR 8.0, pass for Taris Sewers, cr_max 6.0). Falls
    back to the full unfiltered pool if the filter empties it out (a
    small category pool can easily have nothing in range) -- always
    returns SOMETHING from `pool` rather than failing, since every
    candidate in `pool` already passed every safety filter regardless of
    CR. This fallback can still exceed cr_max in the rare case a
    category pool has nothing at or below it at all -- accepted
    trade-off over returning nothing, same reasoning as before."""
    if not pool:
        return None
    filtered = [r for r in pool if cr_min - CR_TOLERANCE <= _creature_cr(installation, r, cr_cache) <= cr_max]
    return rng.choice(filtered if filtered else pool)


def write_bounty_card_template(installation: Installation, override_dir: str) -> None:
    """One shared item, not one per module -- kotor_location_tracker.py's
    _handle_bounty_count checks off locations purely by COUNTING how many
    of these the player is carrying (Plot=1 quest items can't be sold/
    dropped/destroyed, so the count only ever goes up -- same monotonic
    shape as character level), so there's no need for 40 distinguishable
    tags the way an earlier design draft assumed. Also implicitly exempt
    from loot_mode destroy/replace suppression for free: patch_item_
    suppression.py's whitelist is built entirely from gear_items.json's
    own keys, and this resref is deliberately never added there, so it
    can never match that script's suppression condition at all."""
    src = installation.resource(BOUNTY_CARD_BASE_ITEM, ResourceType.UTI)
    if src is None:
        sys.exit(f"vanilla {BOUNTY_CARD_BASE_ITEM}.uti not found -- is --game-dir a real KOTOR install?")
    uti = construct_uti(read_gff(src.data))
    uti.resref = ResRef(BOUNTY_CARD_RESREF)
    uti.tag = BOUNTY_CARD_RESREF
    uti.name = LocalizedString.from_english("Bounty Datapad")
    uti.description = LocalizedString.from_english(
        "A datapad logging proof of a bounty claimed from one of the additional dangers "
        "roaming this world. Can't be sold, dropped, or destroyed.")
    uti.plot = 1
    uti.stack_size = 99
    data = bytearray()
    write_gff(dismantle_uti(uti), data)
    with open(os.path.join(override_dir, f"{BOUNTY_CARD_RESREF}.uti"), "wb") as f:
        f.write(bytes(data))
    print(f"  wrote Override/{BOUNTY_CARD_RESREF}.uti")


def build_bounty_death_wrapper(original_on_death: str) -> str:
    """Preserve-original + wrapper, same shape used everywhere else in
    this project for a hook that must not silently replace real vanilla
    behavior. Calling the original OnDeath script first (if the chosen
    creature had one at all -- many of the safe-pool creatures don't)
    means whatever real death behavior/loot/journal update that enemy
    already had keeps happening exactly as before; this only ADDS the
    bounty card on top. CreateItemOnObject targets OBJECT_SELF, which at
    OnDeath time is still the (now-dead, lootable) creature corpse -- the
    card shows up in its loot window like any other carried item."""
    call_original = f'    ExecuteScript("{original_on_death}", OBJECT_SELF);\n' if original_on_death else ""
    return f"""// Additional Enemies bounty-card drop. Generated by
// scripts/patch_additional_enemies.py -- one of these per module, cloned
// onto exactly one of that module's newly-placed enemies. Preserves the
// original creature's own OnDeath ({original_on_death or '(none)'}) by
// calling it first, then adds the bounty card on top.
#include "kse"

void main()
{{
{call_original}    CreateItemOnObject("{BOUNTY_CARD_RESREF}", OBJECT_SELF, 1);
    KSE_Diag(152, "AP|BOUNTY|DROPPED");
}}
"""


def _clone_bounty_carrier(resref: str, module_index: int, installation: Installation, override_dir: str) -> str:
    """Clones `resref`'s real .utc into a brand-new, module-unique
    template that behaves identically except for also dropping the
    bounty card on death -- see build_bounty_death_wrapper's own comment
    for why this can't just override the shared template in place.
    Returns the new resref to place instead of the original."""
    utc_resref = f"apbnty{module_index:02d}"
    wrapper_resref = f"apbntyd{module_index:02d}"

    src = installation.resource(resref, ResourceType.UTC)
    if src is None:
        sys.exit(f"vanilla {resref}.utc not found while cloning a bounty carrier -- installation data is unexpectedly missing this creature")
    utc = construct_utc(read_gff(src.data))
    original_on_death = str(utc.on_death)

    nss_path = os.path.join(SRC_DIR, f"{wrapper_resref}.nss")
    ncs_path = os.path.join(SRC_DIR, f"{wrapper_resref}.ncs")
    with open(nss_path, "w", encoding="utf-8") as f:
        f.write(build_bounty_death_wrapper(original_on_death))
    result = subprocess.run([NWNNSSCOMP, "-c", nss_path, "-o", ncs_path],
                            capture_output=True, text=True, cwd=SRC_DIR)
    if not os.path.exists(ncs_path) or os.path.getmtime(ncs_path) < os.path.getmtime(nss_path) - 5:
        sys.exit(f"COMPILE FAILED for {wrapper_resref}:\n{result.stdout}\n{result.stderr}")
    shutil.copy2(ncs_path, os.path.join(override_dir, f"{wrapper_resref}.ncs"))

    utc.resref = ResRef(utc_resref)
    utc.tag = f"{utc.tag}_apbnty{module_index:02d}"
    utc.on_death = ResRef(wrapper_resref)
    data = bytearray()
    write_gff(dismantle_utc(utc), data)
    with open(os.path.join(override_dir, f"{utc_resref}.utc"), "wb") as f:
        f.write(bytes(data))
    return utc_resref


def apply_module(module: str, points: list, band: dict, mode: int, category_pools: dict,
                  safe_pool: list, installation: Installation, cr_cache: dict,
                  rng: random.Random, game_dir: str, module_index: int) -> int:
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

    # Idempotency guard -- confirmed REAL bug, live: running this script
    # twice against an already-patched install (e.g. /ap_patch_all fired
    # without a preceding /ap_restore_all -- this function has no
    # once-per-seed gate of its own, that lives entirely in KotorClient.py
    # and doesn't cover a direct CLI invocation) silently APPENDS a second
    # full batch on top of the first, rather than either no-op'ing or
    # replacing -- confirmed live across all 39 affected modules, each at
    # EXACTLY 2x its real target_new_enemies, with duplicate creatures
    # stacked at IDENTICAL coordinates (the same fixed spawn_points list,
    # reused a second time). `apbnty{module_index:02d}` (the bounty-card
    # carrier's own resref, unique to THIS script and never a name that
    # exists in vanilla or gets reused any other way) already being
    # present in the module's CURRENT live creature list is reliable
    # proof this exact module was already patched at least once since its
    # last real restore -- unlike checking "does a backup file already
    # exist" (which persists across a legitimate restore-then-reapply
    # cycle and would wrongly block that normal workflow), this checks
    # the module's actual CURRENT state, so a real restore (which puts
    # vanilla data back, removing this marker) correctly clears it.
    marker_resref = f"apbnty{module_index:02d}"
    if any(str(c.resref).lower() == marker_resref for c in git.creatures):
        print(f"  {module}: already has Additional Enemies placements ({marker_resref} marker found) -- "
              f"skipping to avoid doubling up. Run --restore first if you actually want to re-roll this module.")
        return 0

    os.makedirs(BACKUP_DIR, exist_ok=True)
    backup_path = os.path.join(BACKUP_DIR, f"{module}.rim")
    if not os.path.exists(backup_path):
        shutil.copy2(path, backup_path)

    override_dir = os.path.join(game_dir, "Override")
    bounty_assigned = False
    placed = 0
    for point in points:
        if mode == 3:
            resref = rng.choice(safe_pool)  # fully_random: no CR filter at all, by design
        else:
            resref = _pick_creature(pool, cr_min, cr_max, installation, cr_cache, rng)
        if resref is None:
            continue
        if not bounty_assigned:
            # Exactly one enemy per module carries the bounty card -- the
            # FIRST one successfully picked, deterministic given the same
            # seed/rng state as everything else here. Clone rather than
            # edit the shared vanilla template directly: that template is
            # very likely reused by ordinary enemies elsewhere in the
            # game too, and an OnDeath override on the shared template
            # would fire for every one of those instances, not just this
            # one placement (same risk already flagged for the original
            # "unique enemy kill location" idea this feature grew out of).
            resref = _clone_bounty_carrier(resref, module_index, installation, override_dir)
            bounty_assigned = True
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

    override_dir = os.path.join(game_dir, "Override")
    os.makedirs(override_dir, exist_ok=True)
    write_bounty_card_template(installation, override_dir)

    total_placed = 0
    print(f"Placing additional enemies across {len(spawn_points)} module(s)...")
    for module_index, (module, points) in enumerate(spawn_points.items(), start=1):
        band = cr_bands.get(module, {})
        total_placed += apply_module(module, points, band, mode, category_pools, safe_pool,
                                      installation, cr_cache, rng, game_dir, module_index)

    print(f"\nDone. Placed {total_placed} new creature(s) across {len(spawn_points)} module(s), "
          f"one bounty card each (see Bounty Card #1-{len(spawn_points)} in Locations.py).")
    print(f"Backup at {BACKUP_DIR} -- restore via `python patch_additional_enemies.py --restore`.")


if __name__ == "__main__":
    main()
