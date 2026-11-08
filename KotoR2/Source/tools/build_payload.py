"""Builds the payload: every compiled script and area file the game needs in its Override folder, from the player's own game files, in one flat folder that the
client copies into Override when it patches (client/k2_patch.py payload_files). Nothing here may be published: the wrappers embed copies of the game's own
scripts and the area files are copies of the game's own area files. It runs on the player's machine (and on the developer's, into client/payload).

  python tools/build_payload.py [--game-dir DIR] [--out DIR] [--k1-dir DIR]

The steps (each is a tool of its own, run into a work folder under OUT/_build, then the results are collected):
  1. project scripts      the conversation, console and Master scripts that hold no game content          (compiled from nss/)
  2. prepare_game_scripts the class rebuild, the story-gate wrappers, the Bazaar's and the Vendor's conversation scripts
  3. area wrappers        every module's area OnEnter script, wrapped so the delivery dispatcher starts (the harness scripts a_bet3m4 and a_hatchopen too)
  4. area hooks           a copy of the area file for the modules that have no OnEnter script, with ours
Only *.ncs and *.are files are collected (the compiler's side files and sources stay in _build). A name made twice with different content is a problem, and a
file left over from an earlier build that this build no longer makes is removed. OUT/_build/report.json lists everything with its sha1.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

# scripts of nss/ that are compiled as they are (they hold nothing from the game). The roster console's scripts (k2se_rp, k2se_ps*, k_plev_spcsuit) are not here:
# the roster console is not part of this build yet.
PROJECT_SCRIPTS = ("k2se_ap_enter", "k2se_cwb", "k2se_cup", "k2se_clab", "k2se_cok_bench", "k2se_cok_up", "k2se_cok_lab", "ap_jedi_inc", "k_ptat_sandper")
COLLECT = (".ncs", ".are")


def sha1_of(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def run(args, env) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable] + args, capture_output=True, text=True, env=env, timeout=1800)


def collect(folder: str, found: dict, problems: list, step: str) -> None:
    """Add every *.ncs and *.are of the folder (and its subfolders, except _work) to `found` {name: bytes}."""
    for base, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if not d.startswith("_")]
        for name in sorted(files):
            low = name.lower()
            if not low.endswith(COLLECT) or low.endswith(".nwnsc.ncs"):
                continue
            with open(os.path.join(base, name), "rb") as f:
                data = f.read()
            if low in found and found[low][1] != data:
                problems.append("%s: %s was made by an earlier step with different content" % (step, name))
                continue
            found[low] = (name, data)


def build(game: str, out: str, k1_dir: str = None) -> dict:
    game, out = os.path.abspath(game), os.path.abspath(out)
    work = os.path.join(out, "_build")
    previous = []                                                  # the files an earlier build made (a flat folder is read by the client, so the list lives in _build)
    try:
        with open(os.path.join(work, "files.json")) as f:
            previous = json.load(f)
    except (OSError, ValueError):
        pass
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work, exist_ok=True)
    env = dict(os.environ, K2_GAME_DIR=game)
    report = {"game_dir": game, "steps": {}, "problems": [], "files": {}}
    found: dict = {}

    # 1. the project's own scripts
    import k2compile
    src = os.path.join(work, "project")
    k2compile.prepare_include_dir(src, game)
    built = []
    for name in PROJECT_SCRIPTS:
        shutil.copy(os.path.join(ROOT, "nss", name + ".nss"), os.path.join(src, name + ".nss"))
        ok, message = k2compile.compile_script(src, name)
        if ok:
            built.append(name)
        else:
            report["problems"].append("project script %s did not compile: %s" % (name, message[-300:]))
    collect(src, found, report["problems"], "project scripts")
    report["steps"]["project scripts"] = built

    # 2. class rebuild, gate wrappers, Bazaar and Vendor scripts
    prepared = os.path.join(work, "prepared")
    args = [os.path.join(HERE, "prepare_game_scripts.py"), "--game-dir", game, "--out", prepared]
    if k1_dir:
        args += ["--k1-dir", k1_dir]
    r = run(args, env)
    if r.returncode != 0:
        report["problems"].append("prepare_game_scripts: " + (r.stdout + r.stderr)[-800:])
    collect(prepared, found, report["problems"], "prepare_game_scripts")
    report["steps"]["prepare_game_scripts"] = r.stdout.strip().splitlines()[-1:] if r.stdout.strip() else []

    # 3. area wrappers
    wrapped = os.path.join(work, "wrappers")
    r = run([os.path.join(HERE, "build_area_wrappers.py"), "--game-dir", game, "--out", wrapped, "--work", os.path.join(work, "wrappers_src"),
             "--with-harness", "--no-manifest"], env)
    if r.returncode != 0:
        report["problems"].append("area wrappers: " + (r.stdout + r.stderr)[-800:])
    collect(wrapped, found, report["problems"], "area wrappers")
    report["steps"]["area wrappers"] = r.stdout.strip().splitlines()[-2:]

    # 4. area hooks
    hooked = os.path.join(work, "hooks")
    r = run([os.path.join(HERE, "build_area_hooks.py"), "--all-empty", "--game-dir", game, "--out", hooked], env)
    if r.returncode != 0:
        report["problems"].append("area hooks: " + (r.stdout + r.stderr)[-800:])
    collect(hooked, found, report["problems"], "area hooks")
    report["steps"]["area hooks"] = ["%d area files" % sum(1 for n in found if n.endswith(".are"))]

    # the collected files go flat into OUT; files of an earlier build that are not made now are removed
    for name in previous:
        if name.lower() not in found:
            try:
                os.remove(os.path.join(out, name))
            except OSError:
                pass
    for low, (name, data) in sorted(found.items()):
        with open(os.path.join(out, name), "wb") as f:
            f.write(data)
        report["files"][name] = sha1_of(data)
    with open(os.path.join(work, "files.json"), "w") as f:
        json.dump(sorted(report["files"]), f)
    with open(os.path.join(work, "report.json"), "w") as f:
        json.dump(report, f, indent=1)
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-dir", default=None)
    ap.add_argument("--out", default=os.path.join(ROOT, "client", "payload"))
    ap.add_argument("--k1-dir", default=None)
    a = ap.parse_args()
    sys.path.insert(0, os.path.join(ROOT, "client"))
    game = a.game_dir
    if not game:
        from k2_patch import find_game_dir
        game = find_game_dir(None, os.path.join(os.environ.get("LOCALAPPDATA", ""), "K2SE", "ap", "game_dir.txt"))
    if not game or not os.path.isfile(os.path.join(game, "swkotor2.exe")):
        print("The game folder was not found. Use --game-dir <the folder that contains swkotor2.exe>.")
        return 2
    os.makedirs(a.out, exist_ok=True)
    report = build(game, a.out, a.k1_dir)
    n = len(report["files"])
    print("payload: %d files in %s" % (n, os.path.abspath(a.out)))
    for step, info in report["steps"].items():
        print("  %-22s %s" % (step, info if isinstance(info, str) else (", ".join(info) if info and isinstance(info[0], str) else info)))
    for p in report["problems"]:
        print("PROBLEM:", p)
    return 1 if report["problems"] or n == 0 else 0


if __name__ == "__main__":
    sys.exit(main())
