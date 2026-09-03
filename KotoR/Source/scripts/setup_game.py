r"""
Deploys this project's base mod content into a KOTOR install's Override
folder. This is the tester-facing counterpart to package_dist.py -- it
needs nothing beyond the Python standard library (no pykotor, no
nwnnsscomp.exe, no third-party packages at all), since everything it
copies was already compiled ahead of time and checked into dist/Override.

Run this once per game install, after extender/install.ps1 -Install and
before generating/connecting to a seed. It only covers the always-on base
layer (area trampolines, heartbeat, companion suppression, store markers)
-- item suppression and door randomization are separate, seed-gated steps,
see patch_item_suppression.py / patch_door_randomizer.py.

Usage:
  python setup_game.py --game-dir "C:\...\swkotor"
"""
import argparse
import os
import shutil
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
DIST_OVERRIDE = os.path.join(REPO_ROOT, "dist", "Override")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--game-dir", default=DEFAULT_GAME_DIR,
                         help=r"Your KOTOR install folder, the one with swkotor.exe (default: the standard Steam location).")
    args = parser.parse_args()

    if not os.path.isdir(args.game_dir):
        sys.exit(f"No such game folder: {args.game_dir}")
    if not os.path.isdir(DIST_OVERRIDE):
        sys.exit(f"{DIST_OVERRIDE} doesn't exist -- this looks like an incomplete checkout/release, "
                  f"missing the packaged base mod content.")

    dest_override = os.path.join(args.game_dir, "Override")
    os.makedirs(dest_override, exist_ok=True)

    copied = 0
    for fname in os.listdir(DIST_OVERRIDE):
        shutil.copy2(os.path.join(DIST_OVERRIDE, fname), os.path.join(dest_override, fname))
        copied += 1

    print(f"Copied {copied} files -> {dest_override}")
    print("Base mod deployed. Item suppression and door randomization (if enabled in your")
    print("seed) are separate steps -- see patch_item_suppression.py / patch_door_randomizer.py.")


if __name__ == "__main__":
    main()
