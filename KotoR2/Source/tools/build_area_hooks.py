"""Gives areas that have no OnEnter script one, by writing a copy of the area file (.are) into the game's Override folder with
OnEnter set to our hook script. Nothing in the game's own archives is touched; delete the copies to undo.

The area files are built from the player's own game files at run time (nothing game-derived is stored in the project).

An area file is found by its name, and a few modules share one name (the Ebon Hawk's 003EBO to 007EBO, 151HAR and 154HAR, 204TEL and 205TEL, 601DAN and 603DAN, 904MAL
and 907MAL). One copy in Override would then replace the area of every module that uses the name, with the other module's rooms and entry script. So a module whose area
file is shared with a module whose file is different is not hooked here (reported as skipped); the modules that have an entry script are hooked by tools/build_area_wrappers.py,
which works on the script's name instead.

  python tools/build_area_hooks.py 102PER                 # one module
  python tools/build_area_hooks.py --all-empty            # the modules whose OnEnter is empty (and whose area file is theirs alone)
  python tools/build_area_hooks.py --remove 102PER        # delete the copy
  python tools/build_area_hooks.py --dry-run --all-empty  # report what would be written
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if "--game-dir" in sys.argv[:-1]:                    # tsl_data reads the game folder when it is imported
    os.environ["K2_GAME_DIR"] = os.path.abspath(sys.argv[sys.argv.index("--game-dir") + 1])
import tsl_data  # noqa: E402
from pykotor.resource.formats.gff import read_gff, write_gff  # noqa: E402
from pykotor.resource.type import ResourceType  # noqa: E402

HOOK_SCRIPT = "k2se_ap_enter"
EMPTY_MODULES = "102PER 151HAR 153HAR 207TEL 211TEL 220TEL 233TEL 304NAR 352NAR 371NAR 404DXN 505OND 510OND 603DAN 610DAN 650DAN 702KOR 711KOR 852NIH 902MAL 903MAL 904MAL 905MAL 906MAL".split()


def shared_with_other_area(module, resref, data):
    """The modules whose area file has this name but other contents (the file in Override would replace theirs)."""
    others = []
    for m in tsl_data.module_bases():
        if m.upper() == module.upper():
            continue
        for r in tsl_data.module_resources(m):
            if r.restype() == ResourceType.ARE:
                if r.resname().lower() == resref.lower() and r.data() != data:
                    others.append(m.upper())
                break
    return others


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("modules", nargs="*")
    ap.add_argument("--all-empty", action="store_true")
    ap.add_argument("--remove", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--game-dir", default=None, help="the KOTOR 2 folder (default: K2_GAME_DIR or the usual install place)")
    ap.add_argument("--out", default=None, help="where the area copies go (default: the game's Override folder)")
    a = ap.parse_args()
    mods = EMPTY_MODULES if a.all_empty else [m.upper() for m in a.modules]
    if not mods:
        ap.error("name at least one module or use --all-empty")
    out = os.path.abspath(a.out) if a.out else os.path.join(tsl_data.GAME, "override")
    os.makedirs(out, exist_ok=True)
    for m in mods:
        found = False
        for r in tsl_data.module_resources(m):
            if r.restype() != ResourceType.ARE:
                continue
            found = True
            resref = r.resname()
            path = os.path.join(out, resref.lower() + ".are")
            if a.remove:
                if os.path.exists(path):
                    os.remove(path)
                    print("removed", path)
                continue
            gff = read_gff(r.data())
            cur = str(gff.root.get_resref("OnEnter")).strip()
            print("%s: area %s, OnEnter now %r" % (m, resref, cur))
            if cur:
                print("  skipped: this area already has an OnEnter script (tools/build_area_wrappers.py hooks that one)")
                continue
            clash = shared_with_other_area(m, resref, r.data())
            if clash:
                print("  skipped: the area file name %s is also used by %s with other contents, one copy would replace theirs" % (resref, ", ".join(clash)))
                continue
            if a.dry_run:
                continue
            gff.root.set_resref("OnEnter", HOOK_SCRIPT)
            write_gff(gff, path, ResourceType.ARE)
            print("  wrote", path)
        if not found:
            print(m, ": no area file found")


if __name__ == "__main__":
    main()
