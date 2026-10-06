"""Writes the 78 location marker items, one plot item per area, for the game-side visited-areas record.

An area's entry script (generate_area_trampolines.py / generate_trampoline_batch.py, area_entry_diag_lines)
gives the player `ap_loc_<idx>` the first time that area is entered; the poll's CheckVisitedMarkers()
reports every marker the player holds, and the client credits the matching "Visited:" location. Presence
in the inventory is the whole record: it survives area changes, saves and restarts, and does not need the
client to be running.

The templates are static and seed-independent: plot items (cannot be sold, dropped or destroyed) cloned from
the same base item as the progression marker and the Vendor Passes, named from the "Visited:" locations in
worlds/kotor/Locations.py. They are written to the game's Override and to extender/raw_override_files, and
listed in extender/scripts_src/_location_manifest.json for package_dist.py.

Usage: python generate_location_items.py [--game-dir=<path>]
"""
import json
import os
import re
import sys

from pykotor.common.language import LocalizedString
from pykotor.common.misc import ResRef
from pykotor.extract.installation import Installation
from pykotor.resource.formats.gff import read_gff, write_gff
from pykotor.resource.generics.uti import construct_uti, dismantle_uti
from pykotor.resource.type import ResourceType

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCATIONS_PY = os.path.join(REPO_ROOT, "Archipelago", "worlds", "kotor", "Locations.py")
RAW_DIR = os.path.join(REPO_ROOT, "extender", "raw_override_files")
MANIFEST_PATH = os.path.join(REPO_ROOT, "extender", "scripts_src", "_location_manifest.json")
BASE_ITEM = "g_i_datapad001"  # same known-good icon and model choice as the progression marker
DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"

_VISITED_RE = re.compile(
    r'"Visited: ([^"]+)": LocationData\(base_id \+ \d+, region="Exploration", location_type="area", area_idx=(\d+)')


def marker_resref(idx):
    """Must match area_entry_diag_lines() in the two area generators and the poll's tag scan."""
    return f"ap_loc_{idx:02d}"


def visited_areas():
    with open(LOCATIONS_PY, encoding="utf-8") as f:
        rows = _VISITED_RE.findall(f.read())
    areas = {int(idx): name for name, idx in rows}
    if len(areas) != len(rows):
        sys.exit("duplicate area_idx among the Visited locations -- fix Locations.py first")
    return dict(sorted(areas.items()))


def main():
    game_dir = DEFAULT_GAME_DIR
    for a in sys.argv[1:]:
        if a.startswith("--game-dir="):
            game_dir = a.split("=", 1)[1]
    override_dir = os.path.join(game_dir, "Override")

    areas = visited_areas()
    if len(areas) != 78 or max(areas) > 99:
        sys.exit(f"expected 78 Visited areas with two-digit indexes, found {len(areas)} (max {max(areas)})")
    installation = Installation(game_dir)
    src = installation.resource(BASE_ITEM, ResourceType.UTI)
    if src is None:
        sys.exit(f"vanilla {BASE_ITEM}.uti not found -- is {game_dir} a real KOTOR install?")

    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(override_dir, exist_ok=True)
    files = []
    for idx, name in areas.items():
        resref = marker_resref(idx)
        uti = construct_uti(read_gff(src.data))
        uti.resref = ResRef(resref)
        uti.tag = resref
        uti.name = LocalizedString.from_english(f"Location: {name}")
        uti.description = LocalizedString.from_english(
            "Marks that you have been to this area, for the Archipelago location log. "
            "Can't be sold, dropped, or destroyed.")
        uti.plot = 1
        uti.stack_size = 1
        data = bytearray()
        write_gff(dismantle_uti(uti), data)
        for d in (override_dir, RAW_DIR):
            with open(os.path.join(d, f"{resref}.uti"), "wb") as f:
                f.write(bytes(data))
        files.append(f"{resref}.uti")
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump({"raw_files": files}, f, indent=2)
        f.write("\n")
    print(f"wrote {len(files)} location marker templates to {override_dir} and {RAW_DIR}")
    print(f"manifest: {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
