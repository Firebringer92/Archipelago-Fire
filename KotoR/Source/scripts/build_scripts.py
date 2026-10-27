"""
Compiles the project's NWScript sources (.nss) into the compiled scripts (.ncs) the game runs.

The repository holds source only; the compiled scripts are build output that goes into the release zips. After cloning the repository, run this once (and again after
changing a script) to produce them:

  python build_scripts.py [--game-dir PATH] [--src extender/scripts_src] [--out DIR] [--only name ...] [--strict]

It needs nwnsc (tools/nwnsc/nwnsc.exe, see PROVENANCE.md) and the game's own script definitions, which it writes into the source folder from your KOTOR install first
(build_game_assets.ensure_compiler_support). Files with no main() or StartingConditional() are includes and are skipped. A script that does not compile is listed and
the rest still build; --strict makes that an error. The compiler writes to a temporary file first, so a failed compile never leaves a stale or half-written .ncs behind.
"""
import argparse
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

ENTRY_POINT = re.compile(r"\b(?:void|int)\s+(?:main|StartingConditional)\s*\(")
NEVER_COMPILE = {"nwscript", "kse"}


def entry_points(folder, only=None):
    """Names (without extension) of the .nss files in folder that are scripts the game can run, not includes."""
    names = []
    for fn in sorted(os.listdir(folder)):
        stem, ext = os.path.splitext(fn)
        if ext.lower() != ".nss" or stem.lower() in NEVER_COMPILE or stem.lower().startswith("k_inc_"):
            continue
        if only and stem not in only:
            continue
        with open(os.path.join(folder, fn), encoding="utf-8-sig", errors="replace") as f:
            text = re.sub(r"//[^\n]*", "", f.read())
        if ENTRY_POINT.search(text):
            names.append(stem)
    return names


def build(src, out, only=None, timeout=60):
    from nwnnsscomp_path import compile_nss
    built, failed = [], []
    os.makedirs(out, exist_ok=True)
    for name in entry_points(src, only):
        tmp = os.path.join(out, ".building", name + ".ncs")      # the compiler decides the extension, so the temporary file keeps .ncs
        os.makedirs(os.path.dirname(tmp), exist_ok=True)
        if os.path.exists(tmp):
            os.remove(tmp)
        try:
            result = compile_nss(os.path.join(src, name + ".nss"), tmp, cwd=src, timeout=timeout)
            ok = os.path.isfile(tmp) and result.returncode == 0
        except Exception as e:      # a timeout or a missing compiler
            result, ok = None, False
            failed.append((name, str(e)))
            continue
        if ok:
            shutil.move(tmp, os.path.join(out, name + ".ncs"))
            built.append(name)
        else:
            if os.path.exists(tmp):
                os.remove(tmp)
            failed.append((name, ((result.stdout or "") + (result.stderr or "")).strip().replace("\n", " | ")[:200]))
    return built, failed


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--game-dir", default=r"C:\Program Files (x86)\Steam\steamapps\common\swkotor")
    ap.add_argument("--src", default=os.path.join(REPO_ROOT, "extender", "scripts_src"))
    ap.add_argument("--out", default=None, help="where the .ncs files go (default: next to the sources)")
    ap.add_argument("--only", nargs="*", default=None, help="script names to build")
    ap.add_argument("--strict", action="store_true", help="exit with status 1 if any script fails")
    args = ap.parse_args()
    src = os.path.abspath(args.src)
    out = os.path.abspath(args.out or src)
    if not os.path.isfile(os.path.join(src, "nwscript.nss")):
        import build_game_assets
        build_game_assets.ensure_compiler_support(build_game_assets.GameData(args.game_dir))
        print("wrote nwscript.nss and the game's include scripts from your KOTOR install")
    built, failed = build(src, out, args.only)
    shutil.rmtree(os.path.join(out, ".building"), ignore_errors=True)
    print(f"build_scripts: {len(built)} compiled, {len(failed)} failed")
    for name, why in failed[:40]:
        print(f"  FAILED {name}: {why}")
    sys.exit(1 if failed and args.strict else 0)


if __name__ == "__main__":
    main()
