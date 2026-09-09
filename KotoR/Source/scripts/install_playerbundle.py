r"""
The "Step 2" installer from the 3-step install vision (see FutureDesign.md's
"PLAN: simplified installation" entry). Run this from WITHIN an already-
extracted PlayerBundle folder (the zip package_playerbundle.py builds) --
it does everything a tester used to do by hand across README.md's old
Steps 2-5:

  - Deploys the always-on base mod content (dist/Override/*) into your
    game's Override folder -- same operation as setup_game.py, called
    directly rather than reimplemented.
  - Copies nwnnsscomp.exe into the game folder root (see
    scripts/nwnnsscomp_path.py -- this is now the PREFERRED location the
    3 patch scripts and 4 NWScript generators look for it).
  - Installs the merged binkw32.dll proxy (same operation as
    extender/install.ps1 -Install, reimplemented natively here in Python
    rather than shelling out to PowerShell -- see this project's own Q3
    research in FutureDesign.md for why: Python is already a hard,
    unavoidable dependency for this whole project, PowerShell isn't.
    install.ps1 itself is left in place, untouched, as a standalone
    fallback/dev tool -- this is a deliberate, small, accepted duplication
    of a short, stable, rarely-touched script, not an oversight).
  - Writes ap_repo_root.txt into the game folder (same as install.ps1),
    pointing at THIS PlayerBundle folder, so the compiled extender knows
    where to find scripts\arm_orchestrator.py at runtime.
  - Runs `pip install "setuptools<81" pykotor` for whichever Python
    interpreter runs this installer -- the same interpreter KotorClient.py
    and the 2 pykotor-dependent patch scripts need to run under later.
  - Writes an install-path marker file (%LOCALAPPDATA%\KotorAP\install_path.txt)
    recording where this PlayerBundle folder lives -- not consumed yet
    (this is for the not-yet-built apworld Launcher-button registration,
    Q2 in FutureDesign.md, so that work doesn't need its own coordination
    step once it exists).
  - Records everything it touched into a manifest
    (%LOCALAPPDATA%\KotorAP\install_manifest.json) so --uninstall can
    cleanly reverse it later -- notably, an Override file that already
    existed with the same name before this ran is recorded as
    "pre-existing" and never deleted on uninstall, since Override is
    shared space this project doesn't own exclusively.

Usage:
  python install_playerbundle.py --game-dir "C:\...\swkotor"    -- install
  python install_playerbundle.py --game-dir "C:\...\swkotor" --uninstall
  python install_playerbundle.py                                -- installs to the default Steam location
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"

DIST_OVERRIDE = os.path.join(REPO_ROOT, "dist", "Override")
SETUP_GAME = os.path.join(SCRIPT_DIR, "setup_game.py")
BUNDLED_NWNNSSCOMP = os.path.join(REPO_ROOT, "to_game_folder", "nwnnsscomp.exe")
PROXY_DLL = os.path.join(REPO_ROOT, "extender", "build_new", "binkw32.dll")
INSTALL_PS1_BACKUP_DIR = os.path.join(REPO_ROOT, "extender", "backup")
CAPTURED_ORIG_COPY = os.path.join(INSTALL_PS1_BACKUP_DIR, "binkw32_real_captured.dll")

KOTORAP_STATE_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "KotorAP")
INSTALL_PATH_MARKER = os.path.join(KOTORAP_STATE_DIR, "install_path.txt")
INSTALL_MANIFEST = os.path.join(KOTORAP_STATE_DIR, "install_manifest.json")


def _file_hash(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _install_binkw32(game_dir: str) -> dict:
    """Python port of extender/install.ps1 -Install -- see that file for
    the original, still-maintained-in-parallel version and why both exist
    (this module's own docstring). Same capture-original-once-then-swap
    logic, same backup filenames, so a game folder previously set up via
    install.ps1 is recognized correctly here too (and vice versa)."""
    real_dll = os.path.join(game_dir, "binkw32.dll")
    real_backup = os.path.join(game_dir, "binkw32_real.dll")

    if not os.path.isfile(real_dll):
        sys.exit(f"No binkw32.dll found at {real_dll} -- wrong game dir, or already broken.")
    if not os.path.isfile(PROXY_DLL):
        sys.exit(f"Merged proxy DLL not found at {PROXY_DLL} -- incomplete PlayerBundle.")

    os.makedirs(INSTALL_PS1_BACKUP_DIR, exist_ok=True)

    already_ours = os.path.isfile(real_backup) and _file_hash(real_dll) == _file_hash(PROXY_DLL)
    if already_ours:
        print(f"binkw32.dll: already our merged proxy, {real_backup} present -- nothing to do.")
        return {"captured_original": False, "already_installed": True}

    captured = False
    if os.path.isfile(real_backup):
        print(f"{real_backup} already exists -- not overwriting (assuming a previous install captured it).")
    else:
        shutil.copy2(real_dll, CAPTURED_ORIG_COPY)
        shutil.copy2(real_dll, real_backup)
        print(f"Captured original binkw32.dll -> {real_backup}")
        captured = True

    shutil.copy2(PROXY_DLL, real_dll)
    print(f"Installed merged proxy -> {real_dll}")

    repo_root_file = os.path.join(game_dir, "ap_repo_root.txt")
    with open(repo_root_file, "w", encoding="ascii", newline="") as f:
        f.write(REPO_ROOT)
    print(f"Wrote {repo_root_file} -> {REPO_ROOT}")

    return {"captured_original": captured, "already_installed": False}


def _uninstall_binkw32(game_dir: str) -> None:
    """Python port of extender/install.ps1 -Uninstall."""
    real_dll = os.path.join(game_dir, "binkw32.dll")
    real_backup = os.path.join(game_dir, "binkw32_real.dll")

    if os.path.isfile(CAPTURED_ORIG_COPY):
        shutil.copy2(CAPTURED_ORIG_COPY, real_dll)
        print(f"Restored original binkw32.dll from {CAPTURED_ORIG_COPY}")
    elif os.path.isfile(real_backup):
        shutil.copy2(real_backup, real_dll)
        print(f"Restored original binkw32.dll from {real_backup}")
    else:
        print("WARNING: no backup found anywhere -- cannot restore binkw32.dll automatically. "
              "Verify the game's files through Steam instead.")
        return

    if os.path.isfile(real_backup):
        os.remove(real_backup)
        print(f"Removed {real_backup}")

    repo_root_file = os.path.join(game_dir, "ap_repo_root.txt")
    if os.path.isfile(repo_root_file):
        os.remove(repo_root_file)
        print(f"Removed {repo_root_file}")

    print("Uninstalled merged proxy. Game folder's binkw32.dll is back to the original.")


def _run_setup_game(game_dir: str) -> list[str]:
    """Calls setup_game.py exactly as a tester would, so the Override-copy
    logic itself lives in exactly one place. Returns the list of filenames
    setup_game.py was ABOUT to copy (computed here from DIST_OVERRIDE
    before calling it) plus, for each one, whether it already existed at
    the destination -- needed for the uninstall manifest, since
    setup_game.py itself doesn't report this."""
    if not os.path.isdir(DIST_OVERRIDE):
        sys.exit(f"{DIST_OVERRIDE} doesn't exist -- this looks like an incomplete PlayerBundle.")
    dest_override = os.path.join(game_dir, "Override")
    os.makedirs(dest_override, exist_ok=True)
    pre_existing = {
        fname: os.path.exists(os.path.join(dest_override, fname))
        for fname in os.listdir(DIST_OVERRIDE)
    }

    result = subprocess.run(
        [sys.executable, SETUP_GAME, f"--game-dir={game_dir}"],
        capture_output=True, text=True,
    )
    print(result.stdout.strip())
    if result.returncode != 0:
        sys.exit(f"setup_game.py failed:\n{result.stderr}")

    return pre_existing


def _copy_nwnnsscomp(game_dir: str) -> bool:
    """Returns True if this installer is the one that put nwnnsscomp.exe
    there (False if one was already present, e.g. a tester who'd
    separately installed the standalone KotOR Scripting Tool into their
    game folder by hand -- don't remove THEIRS on uninstall)."""
    if not os.path.isfile(BUNDLED_NWNNSSCOMP):
        print(f"WARNING: {BUNDLED_NWNNSSCOMP} not found in this PlayerBundle -- skipping "
              f"(the 6 scripts that need it will fall back to a standalone KotOR Scripting Tool install).")
        return False
    dest = os.path.join(game_dir, "nwnnsscomp.exe")
    pre_existing = os.path.isfile(dest)
    if not pre_existing:
        shutil.copy2(BUNDLED_NWNNSSCOMP, dest)
        print(f"Copied nwnnsscomp.exe -> {dest}")
    else:
        print(f"{dest} already exists -- leaving it as-is.")
    return not pre_existing


def _pip_install_pykotor() -> None:
    print("Installing pykotor (needed by patch_item_suppression.py/patch_door_randomizer.py/"
          "patch_additional_enemies.py) ...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "setuptools<81", "pykotor"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"WARNING: pip install failed -- you may need to run this by hand:\n"
              f"  {sys.executable} -m pip install \"setuptools<81\" pykotor\n{result.stderr}")
    else:
        print("pykotor installed.")


def _write_state(manifest: dict) -> None:
    os.makedirs(KOTORAP_STATE_DIR, exist_ok=True)
    with open(INSTALL_PATH_MARKER, "w", encoding="utf-8") as f:
        f.write(REPO_ROOT)
    with open(INSTALL_MANIFEST, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)


def _load_manifest() -> dict | None:
    try:
        with open(INSTALL_MANIFEST, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def install(game_dir: str) -> None:
    if not os.path.isdir(game_dir):
        sys.exit(f"No such game folder: {game_dir}")

    print(f"Installing into {game_dir} ...\n")
    override_pre_existing = _run_setup_game(game_dir)
    print()
    nwnnsscomp_installed_by_us = _copy_nwnnsscomp(game_dir)
    print()
    binkw32_result = _install_binkw32(game_dir)
    print()
    _pip_install_pykotor()
    print()

    manifest = {
        "game_dir": game_dir,
        "repo_root": REPO_ROOT,
        "override_files": override_pre_existing,  # {filename: was_pre_existing}
        "nwnnsscomp_installed_by_us": nwnnsscomp_installed_by_us,
        "binkw32": binkw32_result,
    }
    _write_state(manifest)
    print(f"Install complete. Recorded state at {INSTALL_MANIFEST}")
    print("\nNext: connect once with KotorClient.py to your AP server -- item suppression, "
          "door randomization, and additional enemies now apply themselves automatically on "
          "that first connect (see TESTING.md).")


def uninstall() -> None:
    manifest = _load_manifest()
    if manifest is None:
        sys.exit(f"No install manifest found at {INSTALL_MANIFEST} -- nothing recorded to undo. "
                  f"If you installed manually, use extender/install.ps1 -Uninstall and each "
                  f"patch_*.py script's own --restore flag instead.")

    game_dir = manifest["game_dir"]
    print(f"Uninstalling from {game_dir} (recorded at install time) ...\n")

    for name in ("patch_item_suppression.py", "patch_door_randomizer.py", "patch_additional_enemies.py"):
        result = subprocess.run(
            [sys.executable, os.path.join(SCRIPT_DIR, name), "--restore"],
            capture_output=True, text=True,
        )
        print(result.stdout.strip() or f"{name} --restore: done")
        if result.returncode != 0:
            print(f"  (non-fatal) {name} --restore reported an error:\n{result.stderr}")
    print()

    _uninstall_binkw32(game_dir)
    print()

    if manifest.get("nwnnsscomp_installed_by_us"):
        dest = os.path.join(game_dir, "nwnnsscomp.exe")
        if os.path.isfile(dest):
            os.remove(dest)
            print(f"Removed {dest}")
    else:
        print("nwnnsscomp.exe was already present before install -- leaving it in place.")

    dest_override = os.path.join(game_dir, "Override")
    removed = 0
    for fname, was_pre_existing in manifest.get("override_files", {}).items():
        if was_pre_existing:
            continue  # not ours to remove
        path = os.path.join(dest_override, fname)
        if os.path.isfile(path):
            os.remove(path)
            removed += 1
    print(f"Removed {removed} Override file(s) this installer added "
          f"(left anything that already existed before install untouched).")

    for path in (INSTALL_PATH_MARKER, INSTALL_MANIFEST):
        if os.path.isfile(path):
            os.remove(path)
    print(f"\nUninstall complete. {game_dir} should now be back to a vanilla-plus-Steam state, "
          f"modulo any RIM edits a patch script's own --restore couldn't reverse (see its output above).")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--game-dir", default=DEFAULT_GAME_DIR,
                         help=r"Your KOTOR install folder, the one with swkotor.exe (default: the standard Steam location).")
    parser.add_argument("--uninstall", action="store_true", help="Reverse a previous install.")
    args = parser.parse_args()

    if args.uninstall:
        uninstall()
    else:
        install(args.game_dir)


if __name__ == "__main__":
    main()
