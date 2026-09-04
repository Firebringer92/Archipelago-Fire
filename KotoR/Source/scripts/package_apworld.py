r"""
Packages Archipelago\worlds\kotor\ into a single kotor.apworld -- the
standard Archipelago distribution format for a world implementation (a
zip containing the world's package plus an archipelago.json manifest),
loaded by dropping it into Archipelago\custom_worlds\ instead of unpacking
loose files into Archipelago\worlds\kotor\ directly.

Why this exists (2026-08-31): Generate.py itself is 100% stock, unmodified
Archipelago -- verified via `git diff` against the exact upstream commit
this repo tracks. The ONLY thing that actually determines a KOTOR seed's
generation (item placement, location mapping, slot_data content) is
worlds/kotor/ itself. KotorClient.py also imports directly from it at
connect/play time (e.g. Items.py's item_table). That means whoever
GENERATES a seed and whoever CONNECTS to play it must be running the
EXACT SAME version of worlds/kotor/ -- a mismatch (different item table,
different Options.py choices, different slot_data schema) can silently
misidentify items or locations. There was previously no versioned,
single-file way to guarantee that -- this script produces the one file a
GitHub Release can pin, so "everyone's using the release's kotor.apworld"
is a real, checkable guarantee instead of "hopefully everyone's
worlds/kotor/ folder is the same."

This does NOT touch or require touching your own dev checkout's
worlds/kotor/ folder -- keep developing directly in that folder as normal
(same as package_dist.py leaves the live game install alone and just
copies FROM it). This only reads from it to build the distributable file.

Usage:
  python package_apworld.py                       -- writes dist/kotor.apworld
  python package_apworld.py --out "C:\...\x.apworld"   -- write somewhere else
  python package_apworld.py --version 0.2.0        -- override WORLD_VERSION below
"""
import argparse
import json
import os
import sys
import zipfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
ARCHIPELAGO_ROOT = os.path.join(REPO_ROOT, "Archipelago")
WORLD_DIR = os.path.join(ARCHIPELAGO_ROOT, "worlds", "kotor")
DEFAULT_OUT = os.path.join(REPO_ROOT, "dist", "kotor.apworld")

# Bump this every time worlds/kotor/ changes in any way that could affect
# a generated seed's output or slot_data schema (new/changed options, item
# table changes, location changes) -- this is the one number a host and a
# player can compare to confirm they're running the same generation logic.
# No existing version tracking anywhere in worlds/kotor/ before this
# script -- starting fresh at 0.1.0 for the first packaged release.
WORLD_VERSION = "0.1.2"

GAME_NAME = "KotOR"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=DEFAULT_OUT, help="Where to write the .apworld file.")
    parser.add_argument("--version", default=WORLD_VERSION,
                         help=f"World version to stamp in the manifest (default: {WORLD_VERSION}).")
    parser.add_argument("--min-ap-version", default=None,
                         help="Override minimum_ap_version instead of auto-detecting this machine's own "
                              "Archipelago core version. Use this to pin against a real tester's actual "
                              "(possibly older) core -- e.g. 2026-09-04: this repo's own core was 0.6.8 "
                              "but a tester's freshly-updated official Archipelago was only 0.6.7, so the "
                              "apworld auto-rejected as 'too old' even though nothing KOTOR-specific "
                              "actually needed 0.6.8. minimum_ap_version is purely a load-time gate, not a "
                              "guarantee the code path was exercised on that exact core -- lowering it is "
                              "low-risk (worst case: a real Python error instead of a clean rejection, if "
                              "something genuinely new IS relied upon), not a correctness claim.")
    args = parser.parse_args()

    if not os.path.isdir(WORLD_DIR):
        sys.exit(f"No such folder: {WORLD_DIR}")

    sys.path.insert(0, ARCHIPELAGO_ROOT)
    from worlds.Files import APWorldContainer
    from Utils import __version__ as ap_core_version

    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    apworld = APWorldContainer(args.out)
    apworld.game = GAME_NAME
    from Utils import tuplize_version
    apworld.world_version = tuplize_version(args.version)
    # Guards against loading this apworld on an Archipelago core too old to
    # understand it -- NOT a guarantee of forward compatibility with a
    # NEWER core, so no maximum_ap_version pin (that would need re-pinning
    # every time this repo's own Archipelago core gets updated, for no
    # real benefit -- the actual cross-machine risk this script exists to
    # solve is world_version skew, not core skew).
    min_ap_version = args.min_ap_version if args.min_ap_version is not None else ap_core_version
    apworld.minimum_ap_version = tuplize_version(min_ap_version)
    manifest = apworld.get_manifest()

    included = []
    with zipfile.ZipFile(args.out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for root, dirs, files in os.walk(WORLD_DIR):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for fname in files:
                if fname == "archipelago.json":
                    continue
                full = os.path.join(root, fname)
                rel = os.path.join("kotor", os.path.relpath(full, WORLD_DIR))
                zf.write(full, rel)
                included.append(rel)
        zf.writestr("kotor/archipelago.json", json.dumps(manifest))

    print(f"Wrote {args.out}")
    print(f"  game={GAME_NAME} world_version={args.version} minimum_ap_version={min_ap_version}"
          f"{' (this machine core is ' + ap_core_version + ')' if min_ap_version != ap_core_version else ''}")
    print(f"  {len(included)} files packaged:")
    for rel in sorted(included):
        print(f"    {rel}")
    print()
    print("Install by dropping this file into Archipelago\\custom_worlds\\")
    print("(create that folder if it doesn't exist) -- NOT into worlds\\kotor\\ directly.")


if __name__ == "__main__":
    main()
