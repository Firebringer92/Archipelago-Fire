"""
Builds, on the player's machine, the Override files that are derived from the game's own files.

The download carries recipes (names, offsets, edits) and this script, never copies of BioWare's scripts, dialogs, models or textures: each file is
read from the player's own KOTOR install with pykotor and written into Override. Install.bat runs it once; the client runs it again on every
Connect (it does nothing when every file is already there and unchanged).

  build_game_assets.py                 build whatever is missing or out of date
  build_game_assets.py --check         report what would be built, change nothing
  build_game_assets.py --restore       remove the files this script wrote (Uninstall.bat runs this)
  build_game_assets.py --out DIR       write into DIR instead of the game's Override (development; compares against shipped copies)

Categories (each a function below):
  preserved_scripts      the original vanilla scripts the generated wrappers call (apo_*), copied from the game's scripts under a new name
  cutstart_dialogs       the game's own scene dialogs with one extra unconditional link, so a PC of any class starts the scene (dialog_fixes.py)
  feat_training_dialogs  the seven companion dialogs with the feat training menu added (generate_feat_training.inject)
  saber_colors           the six extra lightsaber crystal colours: models, glow textures, templates, icons, upcrystals.2da (saber_colors.py)
  edited_templates       three of the game's creature and trigger templates with one field changed (template_fixes.py)
  companion_models       (only with --only) the game's Malak model with weapon animations added, made with MDLOps (model_builders.py)
"""
import argparse
import hashlib
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "Archipelago"))

DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
STATE_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "KotorAP")
MANIFEST_PATH = os.path.join(STATE_DIR, "game_assets_manifest.json")
PRESERVED_RECIPE = os.path.join(REPO_ROOT, "scripts", "preserved_originals.json")


class GameData:
    """Read access to the player's KOTOR install: the chitin archives and individual module files."""

    def __init__(self, game_dir):
        from pykotor.extract.installation import Installation
        self.game_dir = game_dir
        self.installation = Installation(game_dir)
        self._modules = {}

    def _module(self, file_name):
        if file_name not in self._modules:
            from pykotor.resource.formats.rim import read_rim
            path = os.path.join(self.game_dir, "modules", file_name)
            if not os.path.isfile(path):
                raise FileNotFoundError(f"{file_name} is not in {os.path.join(self.game_dir, 'modules')}")
            with open(path, "rb") as f:
                rim = read_rim(f.read())
            self._modules[file_name] = {(str(r.resref).lower(), r.restype.extension): r.data for r in rim}
        return self._modules[file_name]

    def resource(self, container, resref, extension):
        """The bytes of resref.extension from the chitin archives ("chitin") or from one module file, or None."""
        resref = resref.lower()
        if container == "chitin":
            from pykotor.resource.type import ResourceType
            from pykotor.extract.installation import SearchLocation
            res = self.installation.resource(resref, ResourceType.from_extension(extension), [SearchLocation.CHITIN])
            return bytes(res.data) if res is not None else None
        data = self._module(container).get((resref, extension))
        return bytes(data) if data is not None else None


def preserved_scripts(game):
    """apo_* : {file name: bytes}. Each is a vanilla compiled script, optionally with a few bytes changed in place (the recipe says which)."""
    with open(PRESERVED_RECIPE, encoding="utf-8") as f:
        recipe = json.load(f)
    out = {}
    for target, step in recipe.items():
        data = game.resource(step["from"], step["resref"], "ncs")
        if data is None:
            raise FileNotFoundError(f"the game has no {step['resref']}.ncs in {step['from']} (needed for {target}.ncs)")
        if "patch" in step:
            buf = bytearray(data)
            for offset, value in step["patch"]:
                buf[offset] = value
            data = bytes(buf)
        out[f"{target}.ncs"] = data
    return out


def cutstart_dialogs(game):
    import dialog_fixes
    return dialog_fixes.cutstart_dialogs(game)


def feat_training_dialogs(game):
    import dialog_fixes
    return dialog_fixes.feat_training_dialogs(game)


def saber_colors(game):
    import saber_colors as sc
    return sc.build(game)


def edited_templates(game):
    import template_fixes
    return template_fixes.edited_templates(game)


def companion_models(game):
    """N_DarthMalak with the weapon animations the game's own model lacks (the New Companion option's Malak). Made with MDLOps from the player's own
    model (fix_malak_basic_attack_animations.py, about 20 seconds, then kept in the KotorAP models folder under LOCALAPPDATA)."""
    import model_builders
    folder = model_builders.ensure("malak", game.game_dir)
    out = {}
    for name in ("N_DarthMalak.mdl", "N_DarthMalak.mdx"):
        with open(os.path.join(folder, name), "rb") as f:
            out[name] = f.read()
    return out


CATEGORIES = {
    "preserved_scripts": preserved_scripts,
    "saber_colors": saber_colors,
    "edited_templates": edited_templates,
    "cutstart_dialogs": cutstart_dialogs,
    "feat_training_dialogs": feat_training_dialogs,
}


# built only when asked for (--only), because they need the model tool and the option that uses them
OPTIONAL_CATEGORIES = {
    "companion_models": companion_models,
}


def ensure_compiler_support(game):
    """The compiler reads nwscript.nss (the game's own definition of its script language) from the folder it compiles in, extender/scripts_src.
    It is written from the player's install and not shipped. Returns True when it had to write it."""
    from pykotor.resource.type import ResourceType
    from pykotor.extract.installation import SearchLocation
    res = game.installation.resource("nwscript", ResourceType.NSS, [SearchLocation.CHITIN])
    if res is None:
        raise FileNotFoundError("the game has no nwscript.nss")
    path = os.path.join(REPO_ROOT, "extender", "scripts_src", "nwscript.nss")
    data = bytes(res.data)
    if os.path.isfile(path) and open(path, "rb").read() == data:
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return True


def _sha1(data):
    return hashlib.sha1(data).hexdigest()


def _load_manifest():
    try:
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_manifest(manifest):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1)


def build(game_dir, out_dir, check_only=False, only=None):
    """Writes every derived file that is missing or differs. Returns (written, unchanged)."""
    game = GameData(game_dir)
    manifest = _load_manifest()
    key = out_dir.lower()
    entry = manifest.setdefault(key, {"files": {}})
    written = unchanged = 0
    os.makedirs(out_dir, exist_ok=True)
    available = {**CATEGORIES, **OPTIONAL_CATEGORIES}
    for name, fn in available.items():
        if (only and name not in only) or (not only and name in OPTIONAL_CATEGORIES):
            continue
        files = fn(game)
        for fname, data in files.items():
            path = os.path.join(out_dir, fname)
            digest = _sha1(data)
            if os.path.isfile(path) and _sha1(open(path, "rb").read()) == digest:
                unchanged += 1
                entry["files"].setdefault(fname, digest)
                continue
            written += 1
            if not check_only:
                with open(path, "wb") as f:
                    f.write(data)
                entry["files"][fname] = digest
    if not check_only:
        _save_manifest(manifest)
    return written, unchanged


def restore(out_dir):
    """Removes the files this script wrote (only those still byte-identical to what it wrote)."""
    manifest = _load_manifest()
    entry = manifest.get(out_dir.lower())
    if not entry:
        return 0
    removed = 0
    for fname, digest in entry["files"].items():
        path = os.path.join(out_dir, fname)
        if os.path.isfile(path) and _sha1(open(path, "rb").read()) == digest:
            os.remove(path)
            removed += 1
    manifest.pop(out_dir.lower(), None)
    _save_manifest(manifest)
    return removed


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--game-dir", default=DEFAULT_GAME_DIR)
    ap.add_argument("--out", default=None, help="write here instead of <game-dir>\\Override")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--restore", action="store_true")
    ap.add_argument("--only", nargs="*", default=None, help="category names")
    args = ap.parse_args()
    game_dir = args.game_dir.strip().strip('"').rstrip("\\/ ") or args.game_dir
    out_dir = args.out or os.path.join(game_dir, "Override")
    try:
        if args.restore:
            print(f"Game assets: removed {restore(out_dir)} files.")
            return
        written, unchanged = build(game_dir, out_dir, check_only=args.check, only=args.only)
        if not args.check and not args.only and not args.out:
            ensure_compiler_support(GameData(game_dir))
        verb = "would build" if args.check else "built"
        print(f"Game assets: {verb} {written}, already in place {unchanged}.")
    except Exception as e:
        print(f"build_game_assets.py failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
