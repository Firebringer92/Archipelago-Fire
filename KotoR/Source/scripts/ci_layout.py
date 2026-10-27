"""
Puts the published repository files where the world's tests expect them, for the GitHub workflow (and for anyone who wants to run the tests from a plain checkout).

The tests were written against the development folder: the Archipelago source with our world and client files in it, and scripts/, extender/ and tools/ next to it.
The published repository keeps the same files under KotoR/Source. This script copies them into place:

  work/Archipelago/worlds/kotor/      <- Source/kotor_ap/worlds/kotor (the world and its tests)
  work/Archipelago/*.py               <- Source/kotor_ap/*.py (the client modules)
  work/scripts, work/extender, work/tools, work/*.json   <- the same folders in Source

  python ci_layout.py --source KotoR/Source --work work      (work/Archipelago must already hold an Archipelago checkout)
"""
import argparse
import os
import shutil
import sys


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--source", required=True, help="the repository's KotoR/Source folder")
    ap.add_argument("--work", required=True, help="the folder that holds (or will hold) Archipelago/")
    args = ap.parse_args()
    source, work = os.path.abspath(args.source), os.path.abspath(args.work)
    core = os.path.join(work, "Archipelago")
    if not os.path.isfile(os.path.join(core, "Generate.py")):
        sys.exit(f"{core} does not hold an Archipelago checkout (Generate.py is missing)")
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    world = os.path.join(core, "worlds", "kotor")
    shutil.rmtree(world, ignore_errors=True)
    shutil.copytree(os.path.join(source, "kotor_ap", "worlds", "kotor"), world, ignore=ignore)
    client = os.path.join(source, "kotor_ap")
    for name in os.listdir(client):
        if os.path.isfile(os.path.join(client, name)) and name.endswith((".py", ".json")):
            shutil.copy2(os.path.join(client, name), core)
    for folder in ("scripts", "extender", "tools"):
        shutil.rmtree(os.path.join(work, folder), ignore_errors=True)
        shutil.copytree(os.path.join(source, folder), os.path.join(work, folder), ignore=ignore)
    for name in os.listdir(source):
        if name.endswith(".json"):
            shutil.copy2(os.path.join(source, name), work)
    print(f"laid out {source} under {work}")


if __name__ == "__main__":
    main()
