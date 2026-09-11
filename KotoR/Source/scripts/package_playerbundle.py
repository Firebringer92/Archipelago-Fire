r"""
Packages the "PlayerBundle" zip -- everything a tester needs to install
and play on their own machine, aside from kotor.apworld itself (see
package_apworld.py for that half). This is the counterpart bundle
referenced throughout README.md's Step 1.

Why this exists as a real script (2026-09-04): the first PlayerBundle
zips this project shipped (v0.1.1, v0.1.2) were built from an ad hoc
one-off script that never got checked into the repo -- meaning the exact
file list was undocumented and not reproducible except by re-deriving it
from memory. That's how patch_item_suppression.py and
patch_door_randomizer.py (both explicitly documented in README.md Step 4
as things a tester runs) ended up silently missing from the shipped zip
entirely, along with the extender/scripts_src/ folder those two scripts
need to avoid requiring nwnnsscomp.exe on a tester's machine. This script
is the fix: one real, versioned source of truth for what the PlayerBundle
contains.

Usage:
  python package_playerbundle.py                      -- writes dist/KOTOR-AP-PlayerBundle-vX.Y.Z.zip
  python package_playerbundle.py --version 0.1.3       -- override the version in the output filename
  python package_playerbundle.py --out "C:\...\x.zip"  -- write somewhere else entirely
"""
import argparse
import os
import zipfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)

# Keep this in sync with package_apworld.py's WORLD_VERSION -- every
# release ships both zips together, version-pinned as a set (see README.md
# Step 1). No shared constant between the two scripts on purpose: bumping
# one without the other would be a silent mistake either way, so each
# script's own default should be updated by hand at release time.
BUNDLE_VERSION = "0.1.4"

# REMINDER: this list does not update itself. Every time a NEW file (not
# just an edit to an existing one) becomes something a tester needs to run
# -- a new patch_*.py script, a new persisted _*.json data table under
# extender/area_trampolines/, a new precompiled fallback .ncs -- it has to
# be added here by hand, or it silently ships without it (see the docstring
# above: this has already happened twice for real, both times to scripts
# README.md itself documented as tester-run steps). Check this list as part
# of finishing any feature, not just at release time.
#
# Individual files (not whole folders) copied in as-is.
FILES = [
    # Destination is deliberately NOT under "extender/" like the rest of
    # this list -- every other entry here lands in the merged PlayerBundle
    # folder, but this one file specifically needs to end up in the real
    # Steam KOTOR game folder ROOT (see scripts/nwnnsscomp_path.py's
    # resolve_nwnnsscomp(), which checks <game-dir>/nwnnsscomp.exe first).
    # The Step-2 installer script is the thing that actually knows to copy
    # this one to a different place than everything else in this list --
    # not a generic "unzip everything into the same folder" operation.
    # Redistribution permission confirmed directly with the tool's dev,
    # 2026-09-08 (see FutureDesign.md's Q1).
    (("extender", "nwnnsscomp.exe"), "to_game_folder/nwnnsscomp.exe"),
    (("scripts", "nwnnsscomp_path.py"), "scripts/nwnnsscomp_path.py"),
    (("extender", "install.ps1"), "extender/install.ps1"),
    (("extender", "build_new", "binkw32.dll"), "extender/build_new/binkw32.dll"),
    (("extender", "area_trampolines", "_graph.json"), "extender/area_trampolines/_graph.json"),
    (("extender", "area_trampolines", "_idx_to_name.json"), "extender/area_trampolines/_idx_to_name.json"),
    (("extender", "area_trampolines", "_mapping.json"), "extender/area_trampolines/_mapping.json"),
    (("extender", "area_trampolines", "_shop_map.json"), "extender/area_trampolines/_shop_map.json"),
    # Found missing 2026-09-10 via a real tester's extender.log: EVERY
    # trampoline compile failed with `Error: Unable to open the include
    # file "kse"`, forever -- generate_trampoline_batch.py's SRC_DIR is
    # extender/area_trampolines (that's the nwnnsscomp cwd, so that's
    # where a bare #include "kse" resolves from), but only a SEPARATE
    # copy under extender/scripts_src/ (via the whole-DIRS copy below)
    # was ever being shipped. kse.nss was never missing from the zip
    # entirely -- just missing from the ONE specific folder the live
    # compile step actually reads includes from. Symptom on the tester's
    # end: KotorClient reports items "armed" (staged for delivery) since
    # that part genuinely succeeds, but nothing is ever actually granted,
    # because every regenerated trampoline silently fails to compile and
    # the stale (or absent) .ncs never changes -- no KSE_Diag call is
    # possible for a compile that never produced a running script. All 3
    # dev-tree copies (extender/kse.nss, extender/area_trampolines/kse.nss,
    # extender/scripts_src/kse.nss) confirmed byte-identical before fixing
    # this, so shipping the area_trampolines one is not a version-drift risk.
    (("extender", "area_trampolines", "kse.nss"), "extender/area_trampolines/kse.nss"),
    # 2026-09-08 fix: these 4 used to land in a "KotorClient/" subfolder,
    # requiring a manual "open it, move the 4 files out, delete the empty
    # folder" step (README.md's old Step 1) -- easy to get wrong, and
    # directly undercuts the whole point of the new 3-step simplified
    # install (install_playerbundle.py doesn't do this move either, so
    # without this fix it would've been the ONE remaining manual step left
    # over from the old process). KotorClient.py needs to sit directly
    # next to CommonClient.py either way (it does `from CommonClient
    # import ...`), so these now extract straight to the Client folder
    # root, same level as every other zip entry here -- no subfolder, no
    # move-and-delete step, matching a plain "extract the zip into your
    # Client folder" instruction.
    (("Archipelago", "KotorClient.py"), "KotorClient.py"),
    (("Archipelago", "kotor_extender_bridge.py"), "kotor_extender_bridge.py"),
    (("Archipelago", "kotor_location_tracker.py"), "kotor_location_tracker.py"),
    (("Archipelago", "kotor_reconciliation.py"), "kotor_reconciliation.py"),
    # 2026-09-09: double-clickable installer -- testers don't run command
    # prompt commands. Ships at the Client folder root (sibling of
    # CommonClient.py, same level as scripts\) so `cd /d "%~dp0"` inside it
    # resolves to the Client folder itself and `scripts\install_playerbundle.py`
    # is a direct, correct relative path from there.
    (("scripts", "Install.bat"), "Install.bat"),
    (("scripts", "Uninstall.bat"), "Uninstall.bat"),
    (("scripts", "arm_orchestrator.py"), "scripts/arm_orchestrator.py"),
    (("scripts", "generate_makejedi_suppressor.py"), "scripts/generate_makejedi_suppressor.py"),
    (("scripts", "generate_poll_shared.py"), "scripts/generate_poll_shared.py"),
    (("scripts", "generate_trampoline_batch.py"), "scripts/generate_trampoline_batch.py"),
    (("scripts", "setup_game.py"), "scripts/setup_game.py"),
    (("scripts", "install_playerbundle.py"), "scripts/install_playerbundle.py"),
    # Found missing entirely from v0.1.1/v0.1.2 (2026-09-04) -- both are
    # explicitly documented as tester-run steps in README.md Step 4, but
    # the ad hoc script those releases were built from never included them.
    (("scripts", "patch_item_suppression.py"), "scripts/patch_item_suppression.py"),
    (("scripts", "patch_door_randomizer.py"), "scripts/patch_door_randomizer.py"),
    # Same gap, caught this time before release (2026-09-08): Additional
    # Enemies' tester-run patch script and its 4 persisted reference tables
    # (Tables A/B/C + the safe pool) were both missing here entirely.
    (("scripts", "patch_additional_enemies.py"), "scripts/patch_additional_enemies.py"),
    (("extender", "area_trampolines", "_enemy_spawn_points.json"), "extender/area_trampolines/_enemy_spawn_points.json"),
    (("extender", "area_trampolines", "_enemy_cr_bands.json"), "extender/area_trampolines/_enemy_cr_bands.json"),
    (("extender", "area_trampolines", "_enemy_category_pools.json"), "extender/area_trampolines/_enemy_category_pools.json"),
    (("extender", "area_trampolines", "_enemy_safe_pool.json"), "extender/area_trampolines/_enemy_safe_pool.json"),
    # patch_item_suppression.py's item whitelist -- found broken 2026-09-04:
    # a real tester's checkout only ever has kotor.apworld as a zip in
    # custom_worlds/, never an extracted worlds/kotor/gear_items.json file
    # on disk, so this can't be read from the Archipelago checkout at all.
    # This is a fixed classification tied to the apworld's own version, not
    # per-seed data, so shipping a static copy here (kept in sync with
    # worlds/kotor/gear_items.json whenever that changes, same as any other
    # release-versioned artifact) is safe.
    (("Archipelago", "worlds", "kotor", "gear_items.json"), "scripts/gear_items.json"),
]

# Whole directories, copied recursively.
DIRS = [
    (("dist", "Override"), "dist/Override"),
    # patch_item_suppression.py's compile_and_deploy() falls back to these
    # precompiled .ncs files whenever nwnnsscomp.exe isn't present on the
    # tester's machine -- ship the whole folder (5MB, mostly other dev-only
    # test scripts alongside the ones actually needed) rather than hand-
    # picking exact filenames per loot_mode, which risks missing one.
    (("extender", "scripts_src"), "extender/scripts_src"),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", default=BUNDLE_VERSION)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    out_path = args.out or os.path.join(REPO_ROOT, "dist", f"KOTOR-AP-PlayerBundle-v{args.version}.zip")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    included = 0
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for parts, arcname in FILES:
            full = os.path.join(REPO_ROOT, *parts)
            if not os.path.exists(full):
                raise SystemExit(f"Missing expected file: {full}")
            zf.write(full, arcname)
            included += 1

        for parts, arc_root in DIRS:
            full_root = os.path.join(REPO_ROOT, *parts)
            if not os.path.isdir(full_root):
                raise SystemExit(f"Missing expected folder: {full_root}")
            for root, dirs, files in os.walk(full_root):
                dirs[:] = [d for d in dirs if d != "__pycache__"]
                for fname in files:
                    full = os.path.join(root, fname)
                    rel = os.path.relpath(full, full_root).replace(os.sep, "/")
                    zf.write(full, f"{arc_root}/{rel}")
                    included += 1

    print(f"Wrote {out_path}")
    print(f"  {included} files packaged")


if __name__ == "__main__":
    main()
