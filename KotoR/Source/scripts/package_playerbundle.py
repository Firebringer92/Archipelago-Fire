r"""
Packages the "PlayerBundle" zip -- everything a tester needs to install
and play on their own machine, aside from kotor.apworld itself (see
package_apworld.py for that half). This is the counterpart bundle
referenced throughout README.md's Step 1.

Why this exists as a real script: the first PlayerBundle
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
import json
import re
import zipfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)

# Keep this in sync with package_apworld.py's WORLD_VERSION -- every
# release ships both zips together, version-pinned as a set (see README.md
# Step 1). No shared constant between the two scripts on purpose: bumping
# one without the other would be a silent mistake either way, so each
# script's own default should be updated by hand at release time.
BUNDLE_VERSION = "0.1.9"

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
    # Redistribution permission confirmed directly with the tool's dev.
    (("extender", "nwnnsscomp.exe"), "to_game_folder/nwnnsscomp.exe"),
    (("scripts", "nwnnsscomp_path.py"), "scripts/nwnnsscomp_path.py"),
    # extender/install.ps1 is retired, not shipped here -- a parallel
    # PowerShell install path never wrote python_path.txt the way
    # install_playerbundle.py does, reintroducing the PATH-resolution bug
    # that marker exists to prevent for anyone who used it instead of
    # Install.bat. One tester-facing install path only.
    (("extender", "build_new", "binkw32.dll"), "extender/build_new/binkw32.dll"),
    (("extender", "area_trampolines", "_graph.json"), "extender/area_trampolines/_graph.json"),
    (("extender", "area_trampolines", "_idx_to_name.json"), "extender/area_trampolines/_idx_to_name.json"),
    (("extender", "area_trampolines", "_mapping.json"), "extender/area_trampolines/_mapping.json"),
    (("extender", "area_trampolines", "_shop_map.json"), "extender/area_trampolines/_shop_map.json"),
    # Found missing via a real tester's extender.log: EVERY
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
    # These 4 used to land in a "KotorClient/" subfolder,
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
    # Found missing entirely via a scratch-directory test install:
    # KotorClient.py imports from entitlement.py directly (HEAVY_ARMS,
    # PROGRESSION_ITEM_RESREFS, etc.) -- every real tester's install would
    # hit an ImportError on the very first run without it. Same class of
    # gap as the other files in this list, just never caught until now.
    (("Archipelago", "entitlement.py"), "entitlement.py"),
    # Double-clickable installer -- testers don't run command
    # prompt commands. Ships at the Client folder root (sibling of
    # CommonClient.py, same level as scripts\) so `cd /d "%~dp0"` inside it
    # resolves to the Client folder itself and `scripts\install_playerbundle.py`
    # is a direct, correct relative path from there.
    (("scripts", "Install.bat"), "Install.bat"),
    (("scripts", "Uninstall.bat"), "Uninstall.bat"),
    (("scripts", "arm_orchestrator.py"), "scripts/arm_orchestrator.py"),
    (("scripts", "generate_makejedi_suppressor.py"), "scripts/generate_makejedi_suppressor.py"),
    (("scripts", "generate_poll_shared.py"), "scripts/generate_poll_shared.py"),
    # Found missing entirely -- a real player hit
    # FileNotFoundError on this exact path on every Connect, since
    # generate_poll_shared.py's REPO_ROOT (dirname(dirname(__file__)),
    # i.e. the PlayerBundle root itself once shipped) needs this file
    # sitting right next to it. Static feat.2da/spells.2da reference data
    # (122 feats, 44 real force powers) the Traps feature's CheckFeats()/
    # force-power reporting reads -- same for every player, not
    # per-seed-generated, so one copy ships with the bundle rather than
    # being regenerated on the player's own machine.
    (("force_powers_and_feats.json",), "force_powers_and_feats.json"),
    (("scripts", "generate_trampoline_batch.py"), "scripts/generate_trampoline_batch.py"),
    (("scripts", "setup_game.py"), "scripts/setup_game.py"),
    (("scripts", "install_playerbundle.py"), "scripts/install_playerbundle.py"),
    # Found missing entirely from v0.1.1/v0.1.2 -- both are
    # explicitly documented as tester-run steps in README.md Step 4, but
    # the ad hoc script those releases were built from never included them.
    (("scripts", "patch_item_suppression.py"), "scripts/patch_item_suppression.py"),
    (("scripts", "patch_door_randomizer.py"), "scripts/patch_door_randomizer.py"),
    # Progression System story gates: run from KotorClient.py on Connect (apply_story_gates()). The gate and
    # helper scripts (ap_gate.nss, sg_*.nss and their precompiled .ncs) ship with the extender/scripts_src copy below.
    (("scripts", "patch_story_gates.py"), "scripts/patch_story_gates.py"),
    # The dialog edits patch_story_gates.py deploys (imported by name, so they must sit next to it).
    (("scripts", "story_gate_dialogs_unknown.py"), "scripts/story_gate_dialogs_unknown.py"),
    (("scripts", "story_gate_dialogs_korriban.py"), "scripts/story_gate_dialogs_korriban.py"),
    # Same gap: patch_loot_disturb.py
    # replaces patch_item_suppression.py's old Mod_OnAcquirItem mechanism
    # for Loot Mode entirely -- it's called automatically from
    # KotorClient.py's on_package Connect handler (not something a tester
    # runs by hand), but install_playerbundle.py --uninstall still needs
    # the actual file present to call its --restore.
    (("scripts", "patch_loot_disturb.py"), "scripts/patch_loot_disturb.py"),
    # Same gap: Additional
    # Enemies' tester-run patch script and its 4 persisted reference tables
    # (Tables A/B/C + the safe pool) were both missing here entirely.
    (("scripts", "patch_additional_enemies.py"), "scripts/patch_additional_enemies.py"),
    # Galactic Shop's tester-run module/template patch (runs
    # from KotorClient.py on Connect, same as the three above), and the
    # TSL Force Power port pilot installer (dev/tester-run by hand only --
    # it needs a local KOTOR 2 install to copy assets from).
    (("scripts", "patch_galactic_shop.py"), "scripts/patch_galactic_shop.py"),
    # Boss datapads: runs from KotorClient.py on every Connect (apply_boss_datapads()).
    (("scripts", "patch_boss_datapads.py"), "scripts/patch_boss_datapads.py"),
    # Player ID: runs from KotorClient.py on every Connect (apply_player_id()).
    (("scripts", "patch_player_id.py"), "scripts/patch_player_id.py"),
    (("scripts", "patch_tsl_powers.py"), "scripts/patch_tsl_powers.py"),
    # Found missing entirely -- runs automatically from KotorClient.py's
    # Connect handler (apply_shop_item_costs()), universal/not seed-gated,
    # but had never actually been wired into the PlayerBundle or the
    # Connect flow at all before this, so no real tester ever received the
    # fix despite it being built and verified once on the dev's own
    # machine. Same class of gap as the ones documented above.
    (("scripts", "patch_shop_item_costs.py"), "scripts/patch_shop_item_costs.py"),
    # Runs from KotorClient.py's Connect handler (apply_area_poll_hooks()),
    # universal/not seed-gated: gives areas with no OnEnter script of their
    # own (Tomb of Marka Ragnos) the poll hook so polling restarts there.
    # Its handler ap_area_poll ships with extender/scripts_src below.
    (("scripts", "patch_area_poll_hooks.py"), "scripts/patch_area_poll_hooks.py"),
    # Runs automatically from KotorClient.py's Connect handler
    # (apply_ap_tracker_quest()), universal/not seed-gated, same class of
    # gap as patch_shop_item_costs.py above if missed -- without this file
    # present, every tester's Connect would hit FileNotFoundError trying
    # to subprocess it. Must run per-install (see its own docstring), so
    # it ships as a script here rather than a pre-baked global.jrl.
    (("scripts", "build_ap_tracker_quest.py"), "scripts/build_ap_tracker_quest.py"),
    # Same gap as loot_disturb/galactic_shop above -- runs
    # automatically from KotorClient.py's Connect handler
    # (apply_new_companion_assets()), not something a tester runs by hand,
    # but missing here would mean the subprocess call fails outright the
    # first time a real tester connects with new_companion=on. The 3
    # precompiled trigger variants it deploys (apo_hk47_vanilla.ncs/
    # apo_hk47_new.ncs/.nss) are already covered by the whole-directory
    # extender/scripts_src copy below -- only this script itself needed
    # adding.
    (("scripts", "generate_new_companion_assets.py"), "scripts/generate_new_companion_assets.py"),
    # Droid options: run on every Connect from KotorClient.py (apply_droid_assets()). Installs or removes the droid models,
    # appearance rows, Battle Droid class tables and companion templates; its models live in extender/raw_override_files.
    (("scripts", "generate_droid_assets.py"), "scripts/generate_droid_assets.py"),
    (("extender", "area_trampolines", "_enemy_spawn_points.json"), "extender/area_trampolines/_enemy_spawn_points.json"),
    (("extender", "area_trampolines", "_enemy_cr_bands.json"), "extender/area_trampolines/_enemy_cr_bands.json"),
    (("extender", "area_trampolines", "_enemy_category_pools.json"), "extender/area_trampolines/_enemy_category_pools.json"),
    (("extender", "area_trampolines", "_enemy_safe_pool.json"), "extender/area_trampolines/_enemy_safe_pool.json"),
    # patch_item_suppression.py's item whitelist -- a real tester's
    # checkout only ever has kotor.apworld as a zip in
    # custom_worlds/, never an extracted worlds/kotor/gear_items.json file
    # on disk, so this can't be read from the Archipelago checkout at all.
    # This is a fixed classification tied to the apworld's own version, not
    # per-seed data, so shipping a static copy here (kept in sync with
    # worlds/kotor/gear_items.json whenever that changes, same as any other
    # release-versioned artifact) is safe.
    (("Archipelago", "worlds", "kotor", "gear_items.json"), "worlds/kotor/gear_items.json"),
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
    # Found missing entirely: generate_new_companion_assets.py reads
    # p_malakh.mdl/.mdx, n_darthmalak_ap.mdl/.mdx, and po_malak.tpc
    # straight from this folder (RAW_OVERRIDE_DIR) at Connect time when
    # new_companion=malak -- but nothing shipped it, so a real tester
    # selecting that option would hit FileNotFoundError on Connect. Ship
    # the whole folder rather than hand-picking filenames, same reasoning
    # as scripts_src above -- it's the same checked-in-source-of-truth
    # convention any future feature's static assets will also land in.
    (("extender", "raw_override_files"), "extender/raw_override_files"),
]


# extender/scripts_src ships whole (the precompiled .ncs files are the fallback when a tester's compiler is missing), but it also
# holds scripts that were only ever used to probe or test the game. Those are left out of the bundle. Vendor scripts are kept
# only if the vendor manifest or the packaged dist/Override lists them (older vendor designs left others behind).
DEV_ONLY_SCRIPT_FAMILIES = re.compile(
    r"^(ap_(captest|localtest|singletest|test|tv|verify_|simulate_|stress_|castspell_diag|grant_test_items|"
    r"force_mission_party|prep_companions|set_xp_marker|pending|area_heartbeat|civilbag_open|rubble_open|"
    r"partpile|pp001|mb001_dist)|ap_heartbeat_)")


def _script_stems_in_json(path):
    names = set()

    def walk(x):
        if isinstance(x, str):
            names.add(os.path.splitext(x)[0])
        elif isinstance(x, dict):
            for v in list(x.values()) + list(x.keys()):
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            walk(json.load(f))
    return names


def _dev_only_filter():
    """Returns a function(stem) -> True for scripts_src files that must not ship."""
    scripts_src = os.path.join(REPO_ROOT, "extender", "scripts_src")
    keep = _script_stems_in_json(os.path.join(scripts_src, "_vendor_manifest.json"))
    keep |= _script_stems_in_json(os.path.join(scripts_src, "_location_manifest.json"))
    dist_override = os.path.join(REPO_ROOT, "dist", "Override")
    if os.path.isdir(dist_override):
        keep |= {os.path.splitext(f)[0] for f in os.listdir(dist_override)}

    def is_dev_only(stem):
        if stem in keep:
            return False
        return bool(DEV_ONLY_SCRIPT_FAMILIES.match(stem)) or stem.startswith("ap_v")

    # Guard: nothing the package itself needs may be matched by the families above.
    wrongly = sorted(k for k in keep if DEV_ONLY_SCRIPT_FAMILIES.match(k))
    if wrongly:
        raise SystemExit(f"dev-only filter would drop needed scripts: {wrongly}")
    return is_dev_only


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", default=BUNDLE_VERSION)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    out_path = args.out or os.path.join(REPO_ROOT, "dist", f"KOTOR-AP-PlayerBundle-v{args.version}.zip")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    included = 0
    left_out = 0
    is_dev_only = _dev_only_filter()
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
                dirs[:] = [d for d in dirs if d not in ("__pycache__", "logs")]
                for fname in files:
                    if arc_root == "extender/scripts_src" and is_dev_only(os.path.splitext(fname)[0]):
                        left_out += 1
                        continue
                    full = os.path.join(root, fname)
                    rel = os.path.relpath(full, full_root).replace(os.sep, "/")
                    zf.write(full, f"{arc_root}/{rel}")
                    included += 1

    print(f"Wrote {out_path}")
    print(f"  {included} files packaged, {left_out} dev/test script files left out of extender/scripts_src")


if __name__ == "__main__":
    main()
