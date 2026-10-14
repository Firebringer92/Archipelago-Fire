r"""
Gives areas that have NO OnEnter script of their own the standard AP poll hook.

Every covered area's OnEnter is replaced by a trampoline that runs the real
script and then ap_poll_shared (see generate_area_trampolines.py). That needs
an OnEnter to replace. A module whose ARE has an empty OnEnter has nothing to
trampoline, and the heartbeat's DelayCommand chain dies on every module change,
so polling stays stopped in such an area until the player walks into a hooked
one. This sets the area's OnEnter to ap_area_poll (extender/scripts_src), which
only runs the poll.

Currently: see MODULES below (every play area found with an empty OnEnter). Not check
locations, only a polling hook.

Universal, not seed-gated, idempotent. Edits modules/<module>.rim in place (its
other resources, including anything the door/enemy patchers wrote, are kept),
backs the module up first into extender/backup/modules if no backup exists yet
(the same store the other module patchers use, so revert/restore covers it),
and copies ap_area_poll.ncs into Override. A save made inside the area keeps
its own copy of the area data, so the hook shows up after the area is loaded
fresh (leave and re-enter).

Usage:
  python patch_area_poll_hooks.py [--game-dir=<path>] [--backup-dir=<path>]
  python patch_area_poll_hooks.py --restore [--game-dir=<path>]
"""
import os
import shutil
import sys

from pykotor.common.misc import ResRef
from pykotor.resource.formats.gff import read_gff, write_gff
from pykotor.resource.formats.rim import read_rim, write_rim
from pykotor.resource.type import ResourceType

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
HANDLER_RESREF = "ap_area_poll"
HANDLER_NCS = os.path.join(REPO_ROOT, "extender", "scripts_src", f"{HANDLER_RESREF}.ncs")
HANDLER_NSS = os.path.join(REPO_ROOT, "extender", "scripts_src", f"{HANDLER_RESREF}.nss")
# Every play area whose ARE has an empty OnEnter and is not already covered by a trampoline
# (found by scanning all modules: Star Forge Deck 2 left polling dead in the final
# stretch, with companion fixes and the Star Forge reconcile silently not running). Left out
# on purpose: the minigame modules (*mg), the STUNT cutscene modules, and the Leviathan Hawk
# modules (ebo_m40aa, ebo_m40ad, ebo_m46ab), which have their own scene scripts.
MODULES = [
    "korr_m38aa",   # Tomb of Marka Ragnos
    "sta_m45ab",    # Star Forge, Deck 2
    "unk_m44ab",    # Unknown World, Temple Catacombs
    "danm14ae", "danm16",
    "kas_m22ab", "kas_m23ab", "kas_m23ac",
    "tar_m09aa",
    "tat_m17ac", "tat_m17af", "tat_m17ag",
]


def _arg_value(flag, default):
    for a in sys.argv[1:]:
        if a.startswith(flag + "="):
            return a.split("=", 1)[1]
    return default


def _find_modules_dir(game_dir):
    for name in ("modules", "Modules"):
        p = os.path.join(game_dir, name)
        if os.path.isdir(p):
            return p
    sys.exit(f"no modules folder under {game_dir}")


def apply(game_dir, backup_dir):
    mod_dir = _find_modules_dir(game_dir)
    override_dir = os.path.join(game_dir, "Override")
    os.makedirs(override_dir, exist_ok=True)
    shutil.copy2(HANDLER_NCS, os.path.join(override_dir, f"{HANDLER_RESREF}.ncs"))

    for module in MODULES:
        path = os.path.join(mod_dir, f"{module}.rim")
        if not os.path.exists(path):
            print(f"  {module}: {path} not found, skipped")
            continue
        r = read_rim(path)
        are_res = next((res for res in r if res.restype == ResourceType.ARE), None)
        if are_res is None:
            print(f"  {module}: no ARE resource, skipped")
            continue
        are = read_gff(are_res.data)
        current = str(are.root.get_resref("OnEnter")) if are.root.exists("OnEnter") else ""
        if current.lower() == HANDLER_RESREF:
            print(f"  {module}: already hooked")
            continue
        if current:
            # A module that does have its own script belongs in AREA_LIST
            # (generate_area_trampolines.py), not here.
            print(f"  {module}: has its own OnEnter {current!r}, left alone")
            continue

        os.makedirs(backup_dir, exist_ok=True)
        backup_path = os.path.join(backup_dir, f"{module}.rim")
        if not os.path.exists(backup_path):
            shutil.copy2(path, backup_path)
            print(f"  backed up {module}.rim -> {backup_path}")

        are.root.set_resref("OnEnter", ResRef(HANDLER_RESREF))
        data = bytearray()
        write_gff(are, data)
        r.set_data(are_res.resref, ResourceType.ARE, bytes(data))
        write_rim(r, path)
        print(f"  {module}: OnEnter set to {HANDLER_RESREF}")
    print("Area poll hooks: applied.")


def restore(game_dir, backup_dir):
    mod_dir = _find_modules_dir(game_dir)
    for module in MODULES:
        path = os.path.join(mod_dir, f"{module}.rim")
        backup_path = os.path.join(backup_dir, f"{module}.rim")
        if os.path.exists(path):
            are_res = next((res for res in read_rim(path) if res.restype == ResourceType.ARE), None)
            hooked = (are_res is not None
                      and str(read_gff(are_res.data).root.get_resref("OnEnter")).lower() == HANDLER_RESREF)
            if hooked and os.path.exists(backup_path):
                shutil.copy2(backup_path, path)
                print(f"  restored {module}.rim from backup")
    handler = os.path.join(game_dir, "Override", f"{HANDLER_RESREF}.ncs")
    if os.path.exists(handler):
        os.remove(handler)
        print(f"  removed Override/{HANDLER_RESREF}.ncs")
    print("Area poll hooks: removed.")


def main():
    game_dir = _arg_value("--game-dir", DEFAULT_GAME_DIR)
    backup_dir = _arg_value("--backup-dir", os.path.join(REPO_ROOT, "extender", "backup", "modules"))
    if not os.path.isfile(HANDLER_NCS):
        sys.exit(f"{HANDLER_NCS} missing -- compile {HANDLER_NSS} first")
    if "--restore" in sys.argv:
        restore(game_dir, backup_dir)
    else:
        apply(game_dir, backup_dir)


if __name__ == "__main__":
    main()
