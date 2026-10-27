"""
Builds the models and textures that are made from the game's own models (the spliced Malak model, the HK-47 variant, the war and assassin droids, the
Mark Two droid fix), on the player's machine, from the player's own copy of the game. Each is made by one of this folder's scripts with MDLOps (tools/mdlops,
GPL, shipped with its licence): decompile the game's model, change it, compile it again. A build takes about a minute and is kept in
%LOCALAPPDATA%\\KotorAP\\models\\<kind>, so it runs once.

  ensure(kind, game_dir) -> folder that holds the finished files for that kind ("malak", "hk47" or "droids")
"""
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO_ROOT, "scripts")
MDLOPS_EXE = os.path.join(REPO_ROOT, "tools", "mdlops", "mdlops.exe")
CACHE_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "KotorAP", "models")

# kind -> (files that must exist afterwards, [(script, extra arguments)])
KINDS = {
    "malak": (["N_DarthMalak.mdl", "N_DarthMalak.mdx"],
              [("fix_malak_basic_attack_animations.py", [])]),
    "hk47": (["ap_hk47v.mdl", "ap_hk47v.mdx", "ap_hk47v_01.tga"],
             [("build_hk47_variant_texture.py", []), ("build_hk47_human_rig.py", [])]),
    "droids": (["ap_drdwar.mdl", "ap_drdwar.mdx", "ap_drdassn.mdl", "ap_drdassn.mdx", "c_drdmktwo.mdl", "c_drdmktwo.mdx"],
               [("build_droid_human_rig.py", ["war"]), ("build_droid_human_rig.py", ["assassin"]),
                ("fix_droid_ranged_animations.py", [])]),
}


class ModelBuildError(RuntimeError):
    pass


def ensure(kind, game_dir):
    outputs, steps = KINDS[kind]
    out = os.path.join(CACHE_DIR, kind)
    if all(os.path.isfile(os.path.join(out, f)) for f in outputs):
        return out
    if not os.path.isfile(MDLOPS_EXE):
        raise ModelBuildError(f"the model tool is missing ({MDLOPS_EXE}); reinstall the KOTOR AP download")
    os.makedirs(out, exist_ok=True)
    env = dict(os.environ, KOTOR_AP_MODEL_OUT=out)
    for script, extra in steps:
        cmd = [sys.executable, os.path.join(SCRIPTS, script)] + extra + [f"--game-dir={game_dir}"]
        result = subprocess.run(cmd, cwd=SCRIPTS, env=env, capture_output=True, text=True, timeout=1200)
        if result.returncode != 0:
            tail = (result.stdout + result.stderr).strip().splitlines()[-6:]
            raise ModelBuildError(f"{script} failed (exit {result.returncode}): " + " | ".join(tail))
    missing = [f for f in outputs if not os.path.isfile(os.path.join(out, f))]
    if missing:
        raise ModelBuildError(f"the {kind} models were not built: missing {', '.join(missing)}")
    return out
