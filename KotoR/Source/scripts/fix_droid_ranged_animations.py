"""
Gives the Mark Two droid model (appearance row 61, c_drdmktwo) the ranged attack animations it lacks, so a companion
using that look can fire an equipped blaster instead of only meleeing.

Why: the creature droids shoot with the `b0a1`-`b0a4` animations (their ranged attacks) and melee with `g0a1`/`g0a2`.
c_drdmktwo has ONLY `g0a1`/`g0a2`, so with a blaster equipped its only available attack is the melee one. The other
droids' `b0a*` clips are 1.5 s long with no timing events (the engine times the shot itself), and Mark Two's melee
clips are also 1.5 s long, so duplicating them under the ranged names lines up. The result is a lunge in place of a
shot, which is acceptable for this spider-legged model.

Method: same as fix_malak_basic_attack_animations.py -- decompile with MDLOps, duplicate animation blocks inside the
SAME model file (no cross-model data, so the skeleton mismatch between droid models does not matter), recompile with
MDLOps. pykotor's write_mdl is NOT used: it crashes the game whenever the animation count changes.

Usage:
  python fix_droid_ranged_animations.py                 -- build into extender/raw_override_files only
  python fix_droid_ranged_animations.py --deploy        -- also copy the .mdl/.mdx into <game-dir>/Override
  python fix_droid_ranged_animations.py --restore       -- remove the deployed copies from <game-dir>/Override
  options: --game-dir=PATH
"""
import glob
import os
import re
import shutil
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
RAW_OVERRIDE_DIR = os.path.join(REPO_ROOT, "extender", "raw_override_files")
MDLOPS_EXE = os.path.join(REPO_ROOT, "tools", "mdlops", "mdlops.exe")
WORK_DIR = os.path.join(REPO_ROOT, "tools", "mdlops", "work_droid_ranged")

RESOURCE = "c_drdmktwo"
# (new animation name, existing animation to duplicate): four ranged attacks from the two melee ones.
ALIASES = (("b0a1", "g0a1"), ("b0a2", "g0a2"), ("b0a3", "g0a1"), ("b0a4", "g0a2"))


def _arg(flag, default=None):
    for a in sys.argv[1:]:
        if a.startswith(flag + "="):
            return a.split("=", 1)[1]
    return default


def _decompile(game_dir):
    from pykotor.extract.installation import Installation
    from pykotor.resource.type import ResourceType
    inst = Installation(game_dir)
    os.makedirs(WORK_DIR, exist_ok=True)
    for f in os.listdir(WORK_DIR):
        os.remove(os.path.join(WORK_DIR, f))
    mdl = inst.resource(RESOURCE, ResourceType.MDL)
    mdx = inst.resource(RESOURCE, ResourceType.MDX)
    work_mdl = os.path.join(WORK_DIR, RESOURCE + ".mdl")
    open(work_mdl, "wb").write(mdl.data)
    open(os.path.join(WORK_DIR, RESOURCE + ".mdx"), "wb").write(mdx.data)
    subprocess.run([MDLOPS_EXE, "-k1", work_mdl], cwd=WORK_DIR, check=True, capture_output=True, text=True)
    ascii_path = os.path.join(WORK_DIR, RESOURCE + "-ascii.mdl")
    if not os.path.isfile(ascii_path):
        raise RuntimeError("MDLOps did not produce the ascii model")
    return ascii_path


def build(game_dir):
    ascii_path = _decompile(game_dir)
    text = open(ascii_path, "r", encoding="utf-8", errors="surrogateescape").read()
    model = re.search(r"^newmodel (\S+)", text, re.M).group(1)  # the model's own name, original casing

    def block(name):
        start = text.index(f"newanim {name} {model}")
        end_marker = f"doneanim {name} {model}"
        return text[start:text.index(end_marker, start) + len(end_marker)]

    if re.search(rf"^newanim b0a1 {re.escape(model)}", text, re.M):
        raise RuntimeError("the model already has b0a1 -- nothing to do (is an already-fixed copy in Override?)")

    new_blocks = []
    for new_name, source_name in ALIASES:
        b = block(source_name)
        b = b.replace(f"newanim {source_name} {model}", f"newanim {new_name} {model}", 1)
        b = b.replace(f"doneanim {source_name} {model}", f"doneanim {new_name} {model}", 1)
        new_blocks.append(b)
        print(f"  duplicated {source_name} -> {new_name}")

    anchor = f"doneanim g0a2 {model}"
    at = text.index(anchor) + len(anchor)
    text = text[:at] + "\n\n" + "\n\n".join(new_blocks) + text[at:]
    open(ascii_path, "w", encoding="utf-8", errors="surrogateescape").write(text)

    subprocess.run([MDLOPS_EXE, "-k1", ascii_path], cwd=WORK_DIR, check=True, capture_output=True, text=True)
    bins = glob.glob(os.path.join(WORK_DIR, f"{RESOURCE}-ascii-*bin.mdl"))
    if not bins:
        raise RuntimeError("MDLOps did not produce a recompiled binary model")
    os.makedirs(RAW_OVERRIDE_DIR, exist_ok=True)
    for ext, src in (("mdl", bins[0]), ("mdx", bins[0][:-4] + ".mdx")):
        shutil.copy2(src, os.path.join(RAW_OVERRIDE_DIR, f"{RESOURCE}.{ext}"))
        print(f"  wrote {os.path.join(RAW_OVERRIDE_DIR, RESOURCE + '.' + ext)} ({os.path.getsize(src)} bytes)")


def deploy(game_dir):
    for ext in ("mdl", "mdx"):
        shutil.copy2(os.path.join(RAW_OVERRIDE_DIR, f"{RESOURCE}.{ext}"), os.path.join(game_dir, "Override", f"{RESOURCE}.{ext}"))
    print(f"  deployed to {game_dir}\\Override")


def restore(game_dir):
    for ext in ("mdl", "mdx"):
        path = os.path.join(game_dir, "Override", f"{RESOURCE}.{ext}")
        if os.path.exists(path):
            os.remove(path)
            print(f"  removed {path}")


if __name__ == "__main__":
    game = _arg("--game-dir", DEFAULT_GAME_DIR)
    if "--restore" in sys.argv:
        restore(game)
    else:
        build(game)
        if "--deploy" in sys.argv:
            deploy(game)
