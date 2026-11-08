"""Copies the KOTOR 2 world (worlds/kotor2 plus the generated data files) into the scratch Archipelago core (ap_core) and runs its tests there.
The K1 project is never touched. Usage: python tools/run_world_tests.py [unittest args]"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
CORE = os.path.join(ROOT, "ap_core")
SRC = os.path.join(ROOT, "worlds", "kotor2")
DST = os.path.join(CORE, "worlds", "kotor2")


def main():
    if not os.path.isdir(CORE):
        sys.exit("ap_core is missing: copy the Archipelago core (without worlds) there first")
    os.makedirs(os.path.join(SRC, "data"), exist_ok=True)
    for name in ("gates.json", "locations.json", "extra_companions.json", "shops.json", "shop_pool.json", "enemies.json", "doors.json", "crafting.json", "peragus.json"):
        shutil.copy(os.path.join(ROOT, "data", name), os.path.join(SRC, "data", name))
    if os.path.isdir(DST):
        shutil.rmtree(DST)
    shutil.copytree(SRC, DST, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    args = sys.argv[1:] or ["discover", "-s", "worlds/kotor2/test", "-t", ".", "-v"]
    return subprocess.call([sys.executable, "-m", "unittest"] + args, cwd=CORE)


sys.exit(main())
