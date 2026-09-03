r"""
Applies the door/trigger mapping AP's own entrance_rando engine computed
during world generation (see worlds/kotor/EntranceRando.py) to the real
game files -- rewriting each transition's LinkedToModule/LinkedTo GIT
fields to point at its shuffled destination instead of the vanilla one.

Reads the mapping straight out of the most recently generated seed's
slot_data (same pattern as patch_item_suppression.py's mode-resolution
check) rather than needing a separate export step.

Shares the same backup directory as patch_item_suppression.py
(extender/backup/modules/) -- both scripts repack the same underlying
module RIM files, so a single shared backup/restore covers whichever of
the two (or both) have touched a given module. Use
patch_item_suppression.py --restore to undo either or both.

Usage:
  python patch_door_randomizer.py                          -- apply (backs up first)
  python patch_door_randomizer.py --force                  -- apply without checking the option
  python patch_door_randomizer.py --game-dir "D:\...\swkotor" -- apply against a non-default install
  python patch_door_randomizer.py --seed=AP_123...          -- pin a specific output/ zip instead of newest-by-mtime

Needs pykotor only -- no NWScript compiler involved at all, this only
rewrites existing LinkedToModule/LinkedTo GFF fields, never generates or
compiles a script.
"""
import os
import shutil
import sys
import zipfile
import zlib

from pykotor.common.misc import ResRef
from pykotor.resource.formats.rim import read_rim, write_rim
from pykotor.resource.formats.gff import read_gff, write_gff
from pykotor.resource.type import ResourceType

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"


def _arg_value(flag, default):
    for i, a in enumerate(sys.argv):
        if a == flag and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
        if a.startswith(flag + "="):
            return a.split("=", 1)[1]
    return default


GAME_DIR = _arg_value("--game-dir", DEFAULT_GAME_DIR)
MOD_DIR = os.path.join(GAME_DIR, "modules")
BACKUP_DIR = os.path.join(REPO_ROOT, "extender", "backup", "modules")
OUTPUT_DIR = os.path.join(REPO_ROOT, "Archipelago", "output")
ARCHIPELAGO_ROOT = os.path.join(REPO_ROOT, "Archipelago")


def _latest_seed_door_mapping(seed_override=None):
    """Returns (mapping_dict, seed_path) or (None, None) if no seed with
    area_randomizer=True can be found/read.

    Same "which zip?" ambiguity as patch_item_suppression.py's
    _latest_seed_mode() -- see its docstring. Loud by default when more
    than one candidate exists; --seed=<substring> pins a specific one."""
    import glob
    zips = sorted(glob.glob(os.path.join(OUTPUT_DIR, "AP_*.zip")), key=os.path.getmtime, reverse=True)
    if not zips:
        return None, None
    if seed_override:
        matches = [z for z in zips if seed_override in os.path.basename(z)]
        if not matches:
            print(f"  --seed={seed_override!r} matched no file in {OUTPUT_DIR}")
            return None, None
        zips = matches
    elif len(zips) > 1:
        print(f"  NOTE: {len(zips)} seed zips in {OUTPUT_DIR}, picking newest by mtime:")
        for z in zips:
            print(f"    {os.path.basename(z)}  ({os.path.getmtime(z):.0f})")
        print(f"  -> using {os.path.basename(zips[0])}. Pass --seed=<name substring> to pick a different one.")
    try:
        sys.path.insert(0, ARCHIPELAGO_ROOT)
        from Utils import restricted_loads
        with zipfile.ZipFile(zips[0]) as z:
            name = next(n for n in z.namelist() if n.endswith(".archipelago"))
            with z.open(name) as f:
                raw = f.read()
        data = restricted_loads(zlib.decompress(raw[1:]))
        for slot_data in data.get("slot_data", {}).values():
            if slot_data.get("area_randomizer") and slot_data.get("door_mapping"):
                return slot_data["door_mapping"], zips[0]
        return None, zips[0]
    except Exception as e:
        print(f"  (couldn't read latest seed's slot_data: {e})")
        return None, None


def main():
    seed_override = _arg_value("--seed", None)
    if "--force" not in sys.argv:
        mapping, seed_path = _latest_seed_door_mapping(seed_override)
        if mapping is None:
            print("No generated seed with area_randomizer=True found -- "
                  "pass --force with a manually-set mapping, or generate a seed with the option set first.")
            return
        print(f"Seed ({os.path.basename(seed_path)}) has area_randomizer=True -- applying.")
    else:
        mapping, seed_path = _latest_seed_door_mapping(seed_override)
        if mapping is None:
            print("--force given but no seed output could be read at all -- nothing to apply.")
            return

    # Group by module so each module's RIM is only opened/backed-up/written once.
    by_module: dict = {}
    for key, dest in mapping.items():
        module, list_name, index_str = key.split(":", 2)
        by_module.setdefault(module, []).append((list_name, int(index_str), dest))

    os.makedirs(BACKUP_DIR, exist_ok=True)
    changed = 0
    unchanged_modules = 0

    for module, entries in sorted(by_module.items()):
        path = os.path.join(MOD_DIR, f"{module}.rim")
        if not os.path.exists(path):
            print(f"  {module}: RIM not found, skipping")
            continue
        try:
            r = read_rim(path)
        except Exception as e:
            print(f"  {module}: could not read RIM ({e}), skipping")
            continue

        git_res = None
        for res in r:
            if res.restype == ResourceType.GIT:
                git_res = res
                break
        if git_res is None:
            print(f"  {module}: no GIT resource, skipping")
            continue

        gff = read_gff(git_res.data)
        any_real_change = False
        for list_name, index, dest in entries:
            lst = gff.root.get_list(list_name)
            inst = lst.at(index)
            current_module = inst.get_resref("LinkedToModule").get() if inst.exists("LinkedToModule") else ""
            current_waypoint = inst.get_string("LinkedTo") if inst.exists("LinkedTo") else ""
            if current_module.lower() == dest["dest_module"].lower() and current_waypoint == dest["dest_waypoint"]:
                continue  # already vanilla-matching (the graceful-fallback entries) -- no write needed
            inst.set_resref("LinkedToModule", ResRef(dest["dest_module"]))
            inst.set_string("LinkedTo", dest["dest_waypoint"])
            any_real_change = True

        if not any_real_change:
            unchanged_modules += 1
            continue

        backup_path = os.path.join(BACKUP_DIR, f"{module}.rim")
        if not os.path.exists(backup_path):
            shutil.copy2(path, backup_path)

        new_git_data = bytearray()
        write_gff(gff, new_git_data)
        r.set_data(git_res.resref, ResourceType.GIT, bytes(new_git_data))
        write_rim(r, path)
        changed += 1
        print(f"  {module}: patched {len(entries)} transition(s)")

    print(f"\nDone. modules patched: {changed}, modules with no real change: {unchanged_modules}")


if __name__ == "__main__":
    main()
