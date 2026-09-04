r"""
Applies the door/trigger mapping AP's own entrance_rando engine computed
during world generation (see worlds/kotor/EntranceRando.py) to the real
game files -- rewriting each transition's LinkedToModule/LinkedTo GIT
fields to point at its shuffled destination instead of the vanilla one.

Reads the mapping out of extender/area_trampolines/_slot_data.json --
written by KotorClient.py on every successful Connect, straight from the
real slot_data the AP server sent THIS player for THEIR OWN slot (see
KotorClient.py's SLOT_DATA_PATH/write_slot_data_for_patch_scripts()).
You must connect once with KotorClient.py before running this (see
README.md Step 6). This works identically whether you're hosting or
joining someone else's multiworld -- neither needs local access to a
generated AP_<seed>.zip at all (found broken 2026-09-04: the previous
approach read the zip directly, which only ever existed on whichever
machine ran Generate.py -- a joining player never has it, so this
literally couldn't work for them before; it also didn't filter for THIS
player's own slot, grabbing whichever slot's data happened to be read
first in a multiworld with more than one KOTOR player).

Shares the same backup directory as patch_item_suppression.py
(extender/backup/modules/) -- both scripts repack the same underlying
module RIM files, so a single shared backup/restore covers whichever of
the two (or both) have touched a given module. Use
patch_item_suppression.py --restore to undo either or both.

Usage:
  python patch_door_randomizer.py                          -- apply (backs up first)
  python patch_door_randomizer.py --force                  -- skip the area_randomizer check, apply anyway
  python patch_door_randomizer.py --game-dir "D:\...\swkotor" -- apply against a non-default install

Needs pykotor only -- no NWScript compiler involved at all, this only
rewrites existing LinkedToModule/LinkedTo GFF fields, never generates or
compiles a script.
"""
import json
import os
import shutil
import sys

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
# Same path patch_item_suppression.py reads -- see its own copy of this
# constant/comment for the full reasoning.
SLOT_DATA_PATH = os.path.join(REPO_ROOT, "extender", "area_trampolines", "_slot_data.json")


def _connected_door_mapping():
    """Returns the door_mapping dict from _slot_data.json, or None if that
    file doesn't exist yet (never connected), area_randomizer wasn't
    actually on for this seed, or the file doesn't parse."""
    if not os.path.isfile(SLOT_DATA_PATH):
        return None
    try:
        with open(SLOT_DATA_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("door_mapping") or None
    except Exception as e:
        print(f"  (couldn't read {SLOT_DATA_PATH}: {e})")
        return None


def main():
    mapping = _connected_door_mapping()
    if mapping is None:
        if "--force" not in sys.argv:
            print(f"No usable door_mapping at {SLOT_DATA_PATH} -- connect once with KotorClient.py "
                  "first (see README.md Step 6), which writes your seed's real door_mapping there on "
                  "every successful Connect (only present at all if area_randomizer is actually on for "
                  "your seed). Pass --force to bypass this check if you believe that's wrong.")
        else:
            print("--force given but no usable door_mapping could be read at all -- nothing to apply.")
        return
    print("Connected seed has a real door_mapping -- applying.")

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
