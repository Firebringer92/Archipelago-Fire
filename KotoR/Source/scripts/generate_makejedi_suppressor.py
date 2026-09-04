r"""
Suppresses Dantooine's real "become a Jedi" trial-completion script
(danm13's k_pdan_makejedi) whenever this project is managing the PC's own
class itself (Options.py's StartingClass != off) -- otherwise a player who
simply plays through the Dantooine trials normally gets a full,
unconditional Jedi class for free via the vanilla AddMultiClass() call
baked into that script, completely bypassing starting_class's item-gating
(granted mode) or double-granting on top of a class they may not have
gotten yet at all.

Investigated 2026-09-02, not assumed -- decompiled the real k_pdan_makejedi
via pykotor's read_ncs() (see research/scan_globals.py for the global-
dependency half of this): confirmed safe to skip wholesale under any
non-off mode, wrapper style like generate_companion_suppressors.py's
existing-vanilla-script case (Override-resref-wins, no RIM/IFO edit
needed, since this is invoked as an ordinary script call/dialogue action,
not an empty Mod_OnAcquirItem-style slot):
  - DAN_EXTRA/DAN_EXTRA_XP/DAN_EXTRA_XP2: confirmed used ONLY inside this
    one script anywhere in the game (see research/scan_globals.py) --
    nothing downstream depends on them.
  - DAN_PATH_STATE: shared with the k_pdan_saber08-16 trial-dialogue
    scripts, but k_pdan_makejedi only READS it, never writes it -- so
    skipping this script can't corrupt that state for anything else.
  - The Bastila/Carth/dan13_WP_council/g_w_lghtsbr01+03+04/dan_wanderhound
    subroutine call, checked directly: NOT an item grant (no
    CreateItemOnObject anywhere near it, in this script or any other in
    the whole module) -- almost certainly cutscene-setup polish
    (positioning party members, suppressing a wandering kath hound during
    the ceremony), not anything mechanically significant. Its loss is
    cosmetic, not a story/softlock risk.
  - The real class grant (GetGlobalNumber-branched AddMultiClass x3 +
    GiveXPToCreature + ShowLevelUpGUI) is what's being replaced by this
    project's own class_guardian/class_consular/class_sentinel arms (or
    any future PC-class-randomize mechanism) -- the vanilla XP grant is
    also superseded by this project's own XP system when experience_mode
    isn't off.

Usage:
  python generate_makejedi_suppressor.py                          -- read starting_class from the latest generated seed
  python generate_makejedi_suppressor.py --starting-class=2        -- use this value directly (0=off/1=start/2=granted/3+=any future managed mode)
  python generate_makejedi_suppressor.py --game-dir "C:\...\swkotor"
"""
import argparse
import glob
import os
import subprocess
import sys
import zipfile
import zlib

from pykotor.resource.formats.rim import read_rim
from pykotor.resource.type import ResourceType

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
ARCHIPELAGO_ROOT = os.path.join(REPO_ROOT, "Archipelago")
OUTPUT_DIR = os.path.join(ARCHIPELAGO_ROOT, "output")
NWNNSSCOMP = r"C:\Program Files (x86)\KotOR Scripting Tool\nwnnsscomp.exe"
SRC_DIR = os.path.join(REPO_ROOT, "extender", "scripts_src")

MODULE = "danm13_s.rim"
RESREF = "k_pdan_makejedi"
PRESERVED_RESREF = "apo_makejedi_orig"


def _latest_seed_starting_class() -> int:
    """Same zip-reading pattern as generate_poll_shared.py's
    _latest_seed_wants_area_randomizer() -- only used as a fallback for
    someone running this by hand; KotorClient.py passes --starting-class=
    explicitly from the actual connected seed's slot_data, same reasoning
    as why that file stopped guessing loot_mode from the newest zip."""
    zips = sorted(glob.glob(os.path.join(OUTPUT_DIR, "AP_*.zip")), key=os.path.getmtime, reverse=True)
    if not zips:
        return 0
    try:
        sys.path.insert(0, ARCHIPELAGO_ROOT)
        from Utils import restricted_loads
        with zipfile.ZipFile(zips[0]) as z:
            name = next(n for n in z.namelist() if n.endswith(".archipelago"))
            with z.open(name) as f:
                raw = f.read()
        data = restricted_loads(zlib.decompress(raw[1:]))
        for slot_data in data.get("slot_data", {}).values():
            if "starting_class" in slot_data:
                return int(slot_data["starting_class"])
        return 0
    except Exception as e:
        print(f"  (couldn't read latest seed's slot_data for starting_class: {e})")
        return 0


WRAPPER_TEMPLATE_VANILLA = f"""// Suppression wrapper for Dantooine's real "become a Jedi" trial-completion
// script (originally danm13's {RESREF}, preserved as {PRESERVED_RESREF}).
//
// starting_class is "off" this seed -- runs the real vanilla script unchanged.
#include "kse"

void main()
{{
    ExecuteScript("{PRESERVED_RESREF}", OBJECT_SELF);
}}
"""

WRAPPER_TEMPLATE_SUPPRESSED = f"""// Suppression wrapper for Dantooine's real "become a Jedi" trial-completion
// script (originally danm13's {RESREF}, preserved as {PRESERVED_RESREF}).
//
// starting_class is project-managed this seed (not "off") -- the vanilla
// AddMultiClass()/XP grant/cutscene-polish is skipped entirely here. The
// real class grant comes from this project's own class_guardian/
// class_consular/class_sentinel arms (or any future PC-class-randomize
// mechanism) instead -- see generate_makejedi_suppressor.py's module
// docstring for the full investigation into why skipping this wholesale
// is safe (every global it touches is either internal-only or read-only
// here, and the Bastila/Carth/lightsaber-resref/dan_wanderhound block is
// confirmed cosmetic cutscene setup, not an item grant).
#include "kse"

void main()
{{
}}
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--game-dir", default=DEFAULT_GAME_DIR,
                         help=r"Your KOTOR install folder, the one with swkotor.exe (default: the standard Steam location).")
    parser.add_argument("--starting-class", type=int, default=None,
                         help="Options.py's StartingClass value to use directly (0=off, anything else=project-managed), "
                              "instead of guessing from the latest AP_*.zip in Archipelago/output/.")
    args = parser.parse_args()

    starting_class = args.starting_class if args.starting_class is not None else _latest_seed_starting_class()
    game_dir = args.game_dir
    mod_dir = os.path.join(game_dir, "modules")
    override_dir = os.path.join(game_dir, "Override")

    preserved_path = os.path.join(override_dir, f"{PRESERVED_RESREF}.ncs")
    if not os.path.exists(preserved_path):
        rim_path = os.path.join(mod_dir, MODULE)
        r = read_rim(rim_path)
        data = None
        for res in r:
            if res.resref.get() == RESREF and res.restype == ResourceType.NCS:
                data = res.data
                break
        if data is None:
            sys.exit(f"ERROR: {RESREF} not found in {rim_path}")
        with open(preserved_path, "wb") as f:
            f.write(data)
        print(f"Preserved original -> {preserved_path} ({len(data)} bytes)")
    else:
        print(f"Preserved original already present -> {preserved_path}")

    body = WRAPPER_TEMPLATE_VANILLA if starting_class == 0 else WRAPPER_TEMPLATE_SUPPRESSED
    nss_path = os.path.join(SRC_DIR, f"{RESREF}.nss")
    with open(nss_path, "w") as f:
        f.write(body)
    print(f"Wrote {nss_path} (starting_class={starting_class}, {'vanilla' if starting_class == 0 else 'suppressed'})")

    ncs_path = os.path.join(SRC_DIR, f"{RESREF}.ncs")
    result = subprocess.run([NWNNSSCOMP, "-c", nss_path, "-o", ncs_path], capture_output=True, text=True, cwd=SRC_DIR)
    if not os.path.exists(ncs_path):
        print(f"COMPILE FAILED:\n{result.stdout}\n{result.stderr}")
        sys.exit(1)
    print(f"Compiled -> {ncs_path}")

    deploy_path = os.path.join(override_dir, f"{RESREF}.ncs")
    with open(ncs_path, "rb") as f:
        wrapper_bytes = f.read()
    with open(deploy_path, "wb") as f:
        f.write(wrapper_bytes)
    print(f"Deployed -> {deploy_path}")


if __name__ == "__main__":
    main()
