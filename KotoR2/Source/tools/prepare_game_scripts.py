"""Builds, from the player's own game files, every script that carries game-derived content, and leaves them ready to be copied into Override.

Nothing built here may be published: the class script embeds tables read from the game's feat, power and class files, and the gate wrappers need copies of the
game's own scripts (kept as <name>_orig). So this runs on the player's machine, once per install (and again when the game's tables change: the class include
carries the sha1 of each source table).

  python tools/prepare_game_scripts.py --game-dir "C:\\...\\Knights of the Old Republic II" --out DIR

Output in DIR: k2se_rb.ncs (the class rebuild), the gate wrappers with the originals they call, extra_assets (with --k1-dir: the K1 companions' models,
textures and portraits) and prepare_report.json (what was built, tool hashes).
Steps: 1. generate the class tables include (tools/build_class_tables.py --include-only)   2. compile k2se_rb with nwnsc, NOPs stripped
       3. build the gate wrappers (tools/build_gate_wrappers.py).
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


def sha1_of(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha1(f.read()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--k1-dir", default=None, help="the player's KotOR 1 folder: its companions' models, textures and portraits are copied for the extra companions")
    a = ap.parse_args()
    game = os.path.abspath(a.game_dir)
    out = os.path.abspath(a.out)
    if not os.path.isfile(os.path.join(game, "swkotor2.exe")):
        print("swkotor2.exe is not in %s: that is not a KOTOR 2 folder." % game)
        return 2
    os.makedirs(out, exist_ok=True)
    env = dict(os.environ, K2_GAME_DIR=game)
    report = {"game_dir": game, "built": [], "problems": []}

    # 1. the class tables, from this install
    work = os.path.join(out, "_classrb")
    os.makedirs(work, exist_ok=True)
    r = subprocess.run([sys.executable, os.path.join(HERE, "build_class_tables.py"), "--include-only", "--game-dir", game, "--out", work],
                       capture_output=True, text=True, env=env)
    include = os.path.join(work, "k2se_classrb_data.nss")
    if r.returncode != 0 or not os.path.isfile(include) or "ALL OK" not in r.stdout:
        report["problems"].append("class tables: " + (r.stdout + r.stderr)[-600:])
    else:
        # 2. the class script
        import k2compile
        k2compile.prepare_include_dir(work, game)
        shutil.copy(os.path.join(ROOT, "nss", "k2se_rb.nss"), os.path.join(work, "k2se_rb.nss"))      # the generated include is already in work
        ok, message = k2compile.compile_script(work, "k2se_rb")
        if ok:
            shutil.copy(os.path.join(work, "k2se_rb.ncs"), os.path.join(out, "k2se_rb.ncs"))
            report["built"].append("k2se_rb.ncs (%s)" % message)
            report["class_include_sha1"] = sha1_of(include)
        else:
            report["problems"].append("k2se_rb did not compile: " + message)

    # 3. the gate wrappers
    r = subprocess.run([sys.executable, os.path.join(HERE, "build_gate_wrappers.py"), "--out", os.path.join(out, "gates"), "--game-dir", game],
                       capture_output=True, text=True, env=env)
    if r.returncode != 0:
        report["problems"].append("gate wrappers: " + (r.stdout + r.stderr)[-800:])
    else:
        report["built"].append("gate wrappers in gates/")
    # 3b. the Bazaar Jawa's conversation scripts (no game content: they could also ship with the client)
    r = subprocess.run([sys.executable, os.path.join(HERE, "build_bazaar.py"), "--game-dir", game, "--out", os.path.join(out, "bazaar")], capture_output=True, text=True, env=env)
    if r.returncode != 0:
        report["problems"].append("Bazaar scripts: " + (r.stdout + r.stderr)[-600:])
    else:
        report["built"].append("Bazaar scripts in bazaar/")
    # 3c. the Archipelago Vendor's conversation scripts (no game content either)
    r = subprocess.run([sys.executable, os.path.join(HERE, "build_vendor.py"), "--game-dir", game, "--out", os.path.join(out, "vendor")], capture_output=True, text=True, env=env)
    if r.returncode != 0:
        report["problems"].append("Vendor scripts: " + (r.stdout + r.stderr)[-600:])
    else:
        report["built"].append("Vendor scripts in vendor/")
    # 4. the KotOR 1 companions' models, textures and portraits (optional: without them the extra companions use K2 looks)
    if a.k1_dir:
        r = subprocess.run([sys.executable, os.path.join(HERE, "build_extra_assets.py"), "--game-dir", game, "--k1-dir", os.path.abspath(a.k1_dir),
                            "--out", os.path.join(out, "extra_assets")], capture_output=True, text=True, env=env)
        if r.returncode != 0:
            report["problems"].append("K1 companion assets: " + (r.stdout + r.stderr)[-500:])
        else:
            report["built"].append("K1 companion assets in extra_assets/")
    with open(os.path.join(out, "prepare_report.json"), "w") as f:
        json.dump(report, f, indent=1)
    print("built:", ", ".join(report["built"]) or "nothing")
    for p in report["problems"]:
        print("PROBLEM:", p)
    return 1 if report["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
