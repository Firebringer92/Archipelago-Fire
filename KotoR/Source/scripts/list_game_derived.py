"""
Dev tool. Lists the project files that are copies or edits of the game's own files (models, textures, portraits, edited dialogs and templates, preserved
vanilla scripts, the journal), as paths relative to the project folder. These must not be published; build_game_assets.py makes them on the player's
machine instead. The GitHub sync and the packagers use this list so a derived file never goes out by accident.

  python list_game_derived.py [--game-dir=PATH]      print the list
"""
import glob
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "Archipelago"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
FOLDERS = [os.path.join("extender", "raw_override_files"), os.path.join("extender", "scripts_src"),
           os.path.join("extender", "dialog_bases"), os.path.join("extender", "portrait_sources")]
ALWAYS_DERIVED = {".mdl", ".mdx", ".tga", ".tpc", ".txi", ".jrl", ".2da", ".png"}
NAME_CHECKED = {".dlg", ".utc", ".utt", ".utp", ".uti"}


def vanilla_names(game_dir):
    """{extension: set of resrefs} for the template and dialog types, across the chitin archives, patch.erf and every module."""
    from pykotor.extract.installation import Installation
    from pykotor.resource.formats.erf import read_erf
    from pykotor.resource.formats.rim import read_rim
    names = {e[1:]: set() for e in NAME_CHECKED}
    inst = Installation(game_dir)
    for res in inst.chitin_resources():
        ext = res.restype().extension
        if ext in names:
            names[ext].add(res.resname().lower())
    paths = glob.glob(os.path.join(game_dir, "modules", "*.rim")) + glob.glob(os.path.join(game_dir, "modules", "*.mod")) \
        + glob.glob(os.path.join(game_dir, "rims", "*.rim")) + [os.path.join(game_dir, "patch.erf")]
    for path in paths:
        if not os.path.isfile(path):
            continue
        try:
            data = open(path, "rb").read()
            cont = read_erf(data) if path.lower().endswith((".erf", ".mod")) else read_rim(data)
        except Exception:
            continue
        for r in cont:
            ext = r.restype.extension
            if ext in names:
                names[ext].add(str(getattr(r, "resref", None) or getattr(r, "resname", "")).lower())
    return names


def saber_files():
    import add_saber_crystal_colors as s
    return {n.lower() for n in s.list_deployed_filenames()}


def preserved_script_names():
    with open(os.path.join(REPO_ROOT, "scripts", "preserved_originals.json"), encoding="utf-8") as f:
        return {k.lower() + ".ncs" for k in json.load(f)}


def derived_files(game_dir=DEFAULT_GAME_DIR):
    vanilla = vanilla_names(game_dir)
    saber = saber_files()
    preserved = preserved_script_names()
    out = []
    for folder in FOLDERS:
        base = os.path.join(REPO_ROOT, folder)
        if not os.path.isdir(base):
            continue
        for root, _dirs, files in os.walk(base):
            for fn in files:
                low = fn.lower()
                stem, ext = os.path.splitext(low)
                rel = os.path.relpath(os.path.join(root, fn), REPO_ROOT)
                if ext in ALWAYS_DERIVED:
                    out.append(rel)
                elif ext in (".ncs", ".nss") and (low in preserved or low.startswith("apo_")):
                    out.append(rel)
                elif low == "nwscript.nss":      # the game's own script language definition, written from the player's install (build_game_assets.py)
                    out.append(rel)
                elif ext in NAME_CHECKED and (stem in vanilla[ext[1:]] or low in saber):
                    out.append(rel)
    root_copy = os.path.join("extender", "nwscript.nss")
    if os.path.isfile(os.path.join(REPO_ROOT, root_copy)):
        out.append(root_copy)
    return sorted(out)


def builder_output_names(game_dir=DEFAULT_GAME_DIR):
    """Lower-case names of every file build_game_assets.py makes on the player's machine (so the packagers leave them out of dist/Override),
    including the models the droid and companion options build (model_builders.py)."""
    import build_game_assets as b
    import model_builders
    game = b.GameData(game_dir)
    names = set()
    for fn in b.CATEGORIES.values():
        names |= {n.lower() for n in fn(game)}
    for outputs, _steps in model_builders.KINDS.values():
        names |= {n.lower() for n in outputs}
    return names


if __name__ == "__main__":
    gd = DEFAULT_GAME_DIR
    for a in sys.argv[1:]:
        if a.startswith("--game-dir="):
            gd = a.split("=", 1)[1]
    for rel in derived_files(gd):
        print(rel)
