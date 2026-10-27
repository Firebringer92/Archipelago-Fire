"""
Dev tool. Works out where each preserved vanilla script shipped in dist/Override (the apo_* files) comes from in the game, and writes the
recipe (names and byte patches only, no game content) to scripts/preserved_originals.json. build_game_assets.py follows that recipe on a
player's machine, so the bundle does not have to carry copies of BioWare's compiled scripts.

For each apo_* file: an exact match on a script in the chitin archives or a module is recorded as a plain copy; a file of the same length that
differs in a few bytes from one game script is recorded as a copy plus those byte patches (the preserved scripts whose exit-script name was
changed in place).
"""
import argparse
import glob
import hashlib
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "Archipelago"))

DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
RECIPE_PATH = os.path.join(REPO_ROOT, "scripts", "preserved_originals.json")


def game_scripts(game_dir):
    """Every compiled script in the game: {(container, resref): bytes}. container is "chitin" or the module file name."""
    from pykotor.extract.installation import Installation
    from pykotor.resource.formats.rim import read_rim
    out = {}
    inst = Installation(game_dir)
    for res in inst.chitin_resources():
        if res.restype().extension == "ncs":
            out[("chitin", res.resname().lower())] = res.data()
    for path in sorted(glob.glob(os.path.join(game_dir, "modules", "*.rim"))):
        try:
            rim = read_rim(open(path, "rb").read())
        except Exception:
            continue
        for res in rim:
            if res.restype.extension == "ncs":
                out[(os.path.basename(path), str(res.resref).lower())] = res.data
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--game-dir", default=DEFAULT_GAME_DIR)
    ap.add_argument("--dist-override", default=os.path.join(REPO_ROOT, "dist", "Override"))
    args = ap.parse_args()

    scripts = game_scripts(args.game_dir)
    by_hash = {}
    by_len = {}
    for key, data in scripts.items():
        # chitin first, then the module file name, so the choice of source is the same on every run
        by_hash.setdefault(hashlib.sha1(data).hexdigest(), []).append(key)
        by_len.setdefault(len(data), []).append(key)
    for keys in by_hash.values():
        keys.sort(key=lambda k: (k[0] != "chitin", k))

    recipe = {}
    unmatched = []
    names = sorted(f for f in os.listdir(args.dist_override) if f.lower().startswith("apo_") and f.lower().endswith(".ncs"))
    for fn in names:
        data = open(os.path.join(args.dist_override, fn), "rb").read()
        target = fn[:-4].lower()
        keys = by_hash.get(hashlib.sha1(data).hexdigest())
        if keys:
            container, resref = keys[0]
            recipe[target] = {"from": container, "resref": resref}
            continue
        best = None
        for key in by_len.get(len(data), []):
            src = scripts[key]
            diffs = [(i, b) for i, (a, b) in enumerate(zip(src, data)) if a != b]
            if best is None or len(diffs) < len(best[1]):
                best = (key, diffs)
        if best is not None and len(best[1]) <= 32:
            container, resref = best[0]
            recipe[target] = {"from": container, "resref": resref, "patch": [[i, b] for i, b in best[1]]}
        else:
            unmatched.append(fn)

    with open(RECIPE_PATH, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(recipe.items())), f, indent=1)
    plain = sum(1 for v in recipe.values() if "patch" not in v)
    print(f"{len(recipe)} of {len(names)} preserved scripts traced to a game script ({plain} plain copies, {len(recipe) - plain} with byte patches)")
    print(f"wrote {RECIPE_PATH}")
    if unmatched:
        print("NOT traced (ours, or built from something else):", ", ".join(unmatched))


if __name__ == "__main__":
    main()
