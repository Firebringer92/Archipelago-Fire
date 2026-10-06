r"""
Boss datapads: Calo Nord, Darth Bandon and Admiral Saul Karath each carry a
datapad that drops when they die. Picking one up is what the client counts as
the matching "Boss: ..." check (generate_poll_shared.py's CheckBossDatapads
reports the possession; kotor_location_tracker.py turns it into the check).
Always on: not tied to any option.

Two static edits, both idempotent and safe to repeat on every Connect:
  1. the three datapad item templates (plot items, so they cannot be sold,
     dropped or destroyed) are written to Override;
  2. the datapad is appended, droppable, to the inventory of every fighting
     version of those three bosses, in each module's own _s.rim (a creature's
     ItemList is template data, so a corpse simply has the item to loot, the
     same way any carried gear does).

"Every version": Calo Nord and Darth Bandon are fought on several planets, so
every creature template of theirs is covered, whichever one a seed or route
reaches, and the cutscene-only stand-ins (STUNT_* modules) are left alone.
Looting any copy satisfies the check; a second copy is harmless.

Runs after the other module-rim writers in the Connect chain (loot mode,
door randomizer, additional enemies): those rebuild their rims from the
pristine backup copy, which would drop a datapad added earlier, so this one
re-checks and re-adds on every Connect. A rim is only rewritten when a
datapad is actually missing. Backs up a rim to the shared backup dir (the
same "only if not already backed up" rule every writer uses) before its
first edit.
"""
import os
import shutil
import sys

from pykotor.common.language import LocalizedString
from pykotor.common.misc import InventoryItem, ResRef
from pykotor.extract.installation import Installation
from pykotor.resource.formats.gff import read_gff, write_gff
from pykotor.resource.formats.rim import read_rim, write_rim
from pykotor.resource.generics.utc import construct_utc, dismantle_utc
from pykotor.resource.generics.uti import construct_uti, dismantle_uti
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
MOD_DIR = os.path.join(GAME_DIR, "Modules")
OVERRIDE = os.path.join(GAME_DIR, "Override")
# Shared with patch_loot_disturb.py / patch_additional_enemies.py / patch_door_randomizer.py.
BACKUP_DIR = os.path.join(REPO_ROOT, "extender", "backup", "modules")

# key -> (item resref/tag, item name). Keep the resrefs in sync with generate_poll_shared.py's
# _BOSS_DATAPADS and the "datapad_key" values in Locations.py.
DATAPADS = {
    "calo": ("ap_dp_calo", "Calo Nord's Datapad"),
    "bandon": ("ap_dp_bandon", "Darth Bandon's Datapad"),
    "karath": ("ap_dp_karath", "Admiral Karath's Datapad"),
}
DATAPAD_BASE_ITEM = "g_i_datapad001"

# (module, creature template resref, datapad key). Every FIGHTING version: found by scanning every
# module's _s.rim for creature templates named Calo Nord / Darth Bandon / Admiral Karath, then
# dropping the cutscene stand-ins (STUNT_* modules), the thugs and Dark Jedi who travel with them,
# Karath's non-combat capture scene (lev_m40aa), and, by decision, the Taris Calo Nord versions
# (tar_m03ab/m03ae/m08aa, non-combat or story-only) and the Endar Spire Bandon (it would open a check
# in the prologue).
TARGETS = [
    ("manm28aa", "n_calonord001", "calo"),       # Manaan landing
    ("tat_m18ac", "bp_calo_ambush", "calo"),     # Tatooine ambush (two templates)
    ("tat_m18ac", "bp_calo_ambush_2", "calo"),
    ("kas_m24aa", "kas_calo", "calo"),           # Kashyyyk
    ("korr_m36aa", "kor_calo", "calo"),          # Korriban
    ("manm28aa", "g_bandon001", "bandon"),       # Manaan
    ("tat_m18ac", "tat_bandon", "bandon"),       # Tatooine
    ("kas_m24aa", "kas_bandon", "bandon"),       # Kashyyyk
    ("korr_m36aa", "kor_bandon", "bandon"),      # Korriban
    ("lev_m40ad", "lev40_saulbridge", "karath"), # Leviathan bridge
]


def write_datapad_templates(installation):
    src = installation.resource(DATAPAD_BASE_ITEM, ResourceType.UTI)
    if src is None:
        sys.exit(f"vanilla {DATAPAD_BASE_ITEM}.uti not found -- is --game-dir a real KOTOR install?")
    written = 0
    for _key, (resref, title) in DATAPADS.items():
        uti = construct_uti(read_gff(src.data))
        uti.resref = ResRef(resref)
        uti.tag = resref
        uti.name = LocalizedString.from_english(title)
        uti.description = LocalizedString.from_english(
            "A datapad taken from a defeated boss. Can't be sold, dropped, or destroyed.")
        uti.plot = 1
        uti.stack_size = 1
        data = bytearray()
        write_gff(dismantle_uti(uti), data)
        path = os.path.join(OVERRIDE, f"{resref}.uti")
        if os.path.exists(path):
            with open(path, "rb") as f:
                if f.read() == bytes(data):
                    continue
        with open(path, "wb") as f:
            f.write(bytes(data))
        written += 1
    print(f"datapad templates: {written} written to Override ({len(DATAPADS) - written} already current)")


def _module_rim_path(base):
    """The module's _s.rim, matched case-insensitively (the install's own file names mix case)."""
    wanted = f"{base}_s.rim".lower()
    for fname in os.listdir(MOD_DIR):
        if fname.lower() == wanted:
            return os.path.join(MOD_DIR, fname)
    return None


def add_datapads_to_bosses():
    by_module = {}
    for module, resref, key in TARGETS:
        by_module.setdefault(module, []).append((resref, key))
    rewritten = []
    missing = []
    for module, targets in sorted(by_module.items()):
        path = _module_rim_path(module)
        if path is None:
            missing.append(module)
            continue
        rim = read_rim(path)
        changed = False
        for res in rim:
            if res.restype != ResourceType.UTC:
                continue
            for resref, key in targets:
                if res.resref.get().lower() != resref.lower():
                    continue
                item_resref = DATAPADS[key][0]
                utc = construct_utc(read_gff(res.data))
                if any(str(i.resref).lower() == item_resref for i in utc.inventory):
                    continue
                utc.inventory.append(InventoryItem(ResRef(item_resref), True, False))
                data = bytearray()
                write_gff(dismantle_utc(utc), data)
                rim.set_data(res.resref, res.restype, bytes(data))
                changed = True
        if not changed:
            continue
        backup = os.path.join(BACKUP_DIR, os.path.basename(path))
        if not os.path.exists(backup):
            os.makedirs(BACKUP_DIR, exist_ok=True)
            shutil.copy2(path, backup)
        write_rim(rim, path)
        rewritten.append(os.path.basename(path))
    if missing:
        print(f"WARNING: no _s.rim found for module(s): {', '.join(missing)}")
    print(f"boss datapads: {len(rewritten)} module file(s) rewritten ({', '.join(rewritten) or 'all already current'})")
    return not missing


def restore():
    """Takes the datapads back out: removes each datapad from the boss templates it was added to and
    deletes the three item templates from Override. Works on the LIVE module files (not by copying a
    backup over them), so it undoes only this patch and leaves whatever the other module-file patchers
    wrote to the same files in place."""
    removed = 0
    rewritten = 0
    by_module = {}
    for module, resref, key in TARGETS:
        by_module.setdefault(module, []).append((resref, key))
    for module, targets in sorted(by_module.items()):
        path = _module_rim_path(module)
        if path is None:
            continue
        rim = read_rim(path)
        changed = False
        for res in rim:
            if res.restype != ResourceType.UTC:
                continue
            for resref, key in targets:
                if res.resref.get().lower() != resref.lower():
                    continue
                item_resref = DATAPADS[key][0]
                utc = construct_utc(read_gff(res.data))
                keep = [i for i in utc.inventory if str(i.resref).lower() != item_resref]
                if len(keep) == len(utc.inventory):
                    continue
                removed += len(utc.inventory) - len(keep)
                utc.inventory = keep
                data = bytearray()
                write_gff(dismantle_utc(utc), data)
                rim.set_data(res.resref, res.restype, bytes(data))
                changed = True
        if changed:
            write_rim(rim, path)
            rewritten += 1
    deleted = 0
    for _key, (resref, _title) in DATAPADS.items():
        path = os.path.join(OVERRIDE, f"{resref}.uti")
        if os.path.exists(path):
            os.remove(path)
            deleted += 1
    print(f"boss datapads restore: removed {removed} datapad(s) from {rewritten} module file(s), deleted {deleted} item template(s)")


def main():
    if not os.path.isdir(MOD_DIR):
        sys.exit(f"Modules folder not found: {MOD_DIR}")
    if "--restore" in sys.argv:
        restore()
        return
    installation = Installation(GAME_DIR)
    write_datapad_templates(installation)
    ok = add_datapads_to_bosses()
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
