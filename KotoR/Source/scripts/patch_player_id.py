"""Writes the Player ID item template, Override/ap_pid.uti.

The Player ID is a plot item the Endar Spire entry script (area_entry_diag_lines in the two area generators)
gives a brand-new level-1 character once. It records which seed and slot the character was started for: its
NAME carries the slot and a short hash of the seed ("Player ID: <slot> <hash>"), and the item data, name
included, is baked into the save when the item is created. The poll reports the name (`AP|PLAYERID|...`) and the
client records it next to each delivery. Nothing is enforced on it yet.

The template is per seed, so this runs on every Connect with the current seed's hash. It rewrites the file only
when the name changed, and a placeholder ships in the bundle so the file always exists at game launch.

Usage:
  python patch_player_id.py --save-id=<hash> --slot=<slot name> [--game-dir=<path>]
  python patch_player_id.py --placeholder   (writes only extender/raw_override_files/ap_pid.uti, for packaging)
"""
import os
import sys

from pykotor.common.language import LocalizedString
from pykotor.common.misc import ResRef
from pykotor.extract.installation import Installation
from pykotor.resource.formats.gff import read_gff, write_gff
from pykotor.resource.generics.uti import construct_uti, dismantle_uti
from pykotor.resource.type import ResourceType

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
RAW_DIR = os.path.join(REPO_ROOT, "extender", "raw_override_files")
RESREF = "ap_pid"
BASE_ITEM = "g_i_datapad001"  # same known-good icon and model choice as the progression marker
NAME_PREFIX = "Player ID: "
PLACEHOLDER_NAME = NAME_PREFIX + "no seed yet"


def clean_slot(slot):
    """The name is read back by the poll and split on '|' and '"', so neither may appear; kept short."""
    cleaned = "".join(c if (c.isprintable() and c not in '|"') else "_" for c in (slot or "")).strip()
    return cleaned[:20] or "unknown"


def item_name(slot, save_id):
    """The client parses the hash as the LAST space-separated word of this name."""
    return f"{NAME_PREFIX}{clean_slot(slot)} {save_id}"


def build_template(installation, name):
    src = installation.resource(BASE_ITEM, ResourceType.UTI)
    if src is None:
        sys.exit(f"vanilla {BASE_ITEM}.uti not found -- is the game dir a real KOTOR install?")
    uti = construct_uti(read_gff(src.data))
    uti.resref = ResRef(RESREF)
    uti.tag = RESREF
    uti.name = LocalizedString.from_english(name)
    uti.description = LocalizedString.from_english(
        "Records which Archipelago seed and slot this character was started for. "
        "Can't be sold, dropped, or destroyed.")
    uti.plot = 1
    uti.stack_size = 1
    data = bytearray()
    write_gff(dismantle_uti(uti), data)
    return bytes(data)


def current_name(path):
    try:
        uti = construct_uti(read_gff(path))
        return uti.name.get(0, 0) if hasattr(uti.name, "get") else None
    except Exception:
        return None


def main():
    game_dir = DEFAULT_GAME_DIR
    save_id = None
    slot = None
    placeholder = False
    for a in sys.argv[1:]:
        if a.startswith("--game-dir="):
            game_dir = a.split("=", 1)[1]
        elif a.startswith("--save-id="):
            save_id = a.split("=", 1)[1]
        elif a.startswith("--slot="):
            slot = a.split("=", 1)[1]
        elif a == "--placeholder":
            placeholder = True
    installation = Installation(game_dir)

    if placeholder:
        os.makedirs(RAW_DIR, exist_ok=True)
        with open(os.path.join(RAW_DIR, f"{RESREF}.uti"), "wb") as f:
            f.write(build_template(installation, PLACEHOLDER_NAME))
        print(f"wrote placeholder {RESREF}.uti to {RAW_DIR}")
        return

    if not save_id or slot is None:
        sys.exit("usage: patch_player_id.py --save-id=<hash> --slot=<slot> [--game-dir=<path>]")
    override_dir = os.path.join(game_dir, "Override")
    os.makedirs(override_dir, exist_ok=True)
    path = os.path.join(override_dir, f"{RESREF}.uti")
    name = item_name(slot, save_id)
    if os.path.exists(path) and current_name(path) == name:
        print(f"player id template unchanged ({name})")
        return
    with open(path, "wb") as f:
        f.write(build_template(installation, name))
    print(f"player id template written ({name})")


if __name__ == "__main__":
    main()
