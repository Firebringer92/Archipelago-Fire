"""
Puts the published repository files where the tests expect them, for the GitHub workflow (and for anyone who wants to run the tests from a plain checkout).

The tests were written against the development folder: the Archipelago core with our world in it, and client/, tools/, data/ and nss/ next to it. The published repository keeps the
same files under KotoR2/Source. This script copies them into place:

  work/Archipelago/worlds/kotor2/     <- Source/worlds/kotor2 (the world and its tests), with the data files from Source/data in its data/ folder
  work/client, work/tools, work/data, work/nss, work/worlds/kotor2   <- the same folders in Source (the layout of the development folder)
  work/docs/KotOR2_TEMPLATE.yaml   <- Docs/KotOR2_TEMPLATE.yaml (next to Source)

  python ci_layout.py --source KotoR2/Source --work work      (work/Archipelago must already hold an Archipelago checkout)
"""
import argparse
import os
import shutil
import sys

# the data files the world loads (tools/run_world_tests.py copies the same list)
WORLD_DATA = ("gates.json", "locations.json", "extra_companions.json", "shops.json", "shop_pool.json", "enemies.json", "doors.json", "crafting.json", "peragus.json")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--source", required=True, help="the repository's KotoR2/Source folder")
    ap.add_argument("--work", required=True, help="the folder that holds (or will hold) Archipelago/")
    args = ap.parse_args()
    source, work = os.path.abspath(args.source), os.path.abspath(args.work)
    core = os.path.join(work, "Archipelago")
    if not os.path.isfile(os.path.join(core, "Generate.py")):
        sys.exit(f"{core} does not hold an Archipelago checkout (Generate.py is missing)")
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    for folder in ("client", "tools", "data", "nss"):
        shutil.rmtree(os.path.join(work, folder), ignore_errors=True)
        shutil.copytree(os.path.join(source, folder), os.path.join(work, folder), ignore=ignore)
    for target in (os.path.join(work, "worlds", "kotor2"), os.path.join(core, "worlds", "kotor2")):
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(os.path.join(source, "worlds", "kotor2"), target, ignore=ignore)
    os.makedirs(os.path.join(work, "docs"), exist_ok=True)           # the template test looks for docs/KotOR2_TEMPLATE.yaml next to the core
    shutil.copy2(os.path.join(os.path.dirname(source), "Docs", "KotOR2_TEMPLATE.yaml"), os.path.join(work, "docs"))
    world_data = os.path.join(core, "worlds", "kotor2", "data")
    os.makedirs(world_data, exist_ok=True)
    for name in WORLD_DATA:
        shutil.copy2(os.path.join(source, "data", name), world_data)
    print(f"laid out {source} under {work}")


if __name__ == "__main__":
    main()
