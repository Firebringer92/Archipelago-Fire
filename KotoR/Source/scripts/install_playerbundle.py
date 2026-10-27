r"""
The "Step 2" installer of the 3-step install (unzip the PlayerBundle, run
this, drop the apworld into custom_worlds). Run this from WITHIN an already-
extracted PlayerBundle folder (the zip package_playerbundle.py builds) --
it does everything a tester used to do by hand across README.md's old
Steps 2-5:

  - Deploys the always-on base mod content (dist/Override/*) into your
    game's Override folder -- same operation as setup_game.py, called
    directly rather than reimplemented.
  - Checks that the script compiler (tools/nwnsc/nwnsc.exe, run from this
    folder by scripts/nwnnsscomp_path.py) came with the download.
  - Installs the merged binkw32.dll proxy (captures the real DLL once,
    then swaps in the merged proxy -- see _install_binkw32()). This is the
    only tester-facing path that does this: a parallel PowerShell
    equivalent (extender/install.ps1) existed previously but is retired,
    since it never wrote python_path.txt the way this script does below --
    a second install path only matters if it's kept in exact parity with
    this one, and the one thing it was missing is exactly what that
    marker exists to prevent (bare "python" PATH resolution failing
    silently against the orchestrator's own subprocess calls).
  - Writes ap_repo_root.txt into the game folder, pointing at THIS
    PlayerBundle folder, so the compiled extender knows where to find
    scripts\arm_orchestrator.py at runtime.
  - Runs `pip install "setuptools<81" pykotor` for whichever Python
    interpreter runs this installer -- the same interpreter KotorClient.py
    and the 2 pykotor-dependent patch scripts need to run under later.
  - Writes an install-path marker file (%LOCALAPPDATA%\KotorAP\install_path.txt)
    recording where this PlayerBundle folder lives -- consumed by the
    apworld's "KOTOR Client" Launcher button (worlds/kotor/__init__.py's
    launch_kotor_client) to find KotorClient.py.
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
import textwrap

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"

DIST_OVERRIDE = os.path.join(REPO_ROOT, "dist", "Override")
SETUP_GAME = os.path.join(SCRIPT_DIR, "setup_game.py")
BUNDLED_COMPILER = os.path.join(REPO_ROOT, "tools", "nwnsc", "nwnsc.exe")
PROXY_DLL = os.path.join(REPO_ROOT, "extender", "build_new", "binkw32.dll")
INSTALL_PS1_BACKUP_DIR = os.path.join(REPO_ROOT, "extender", "backup")
CAPTURED_ORIG_COPY = os.path.join(INSTALL_PS1_BACKUP_DIR, "binkw32_real_captured.dll")

KOTORAP_STATE_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "KotorAP")
INSTALL_PATH_MARKER = os.path.join(KOTORAP_STATE_DIR, "install_path.txt")
PYTHON_PATH_MARKER = os.path.join(KOTORAP_STATE_DIR, "python_path.txt")
INSTALL_MANIFEST = os.path.join(KOTORAP_STATE_DIR, "install_manifest.json")


MODE = "INSTALL"      # "UNINSTALL" when run with --uninstall; only used for the failure banner
WARNINGS: list[str] = []   # non-fatal problems, repeated in one summary at the very end

HELP_LINE = ("If you are stuck, post a screenshot of this whole window where you downloaded the "
             "randomizer. Running this again after a fix is safe.")


def _wrap(text: str, first: str = "", rest: str = "") -> str:
    """Wraps to fit a normal Command Prompt window, so a sentence is never cut mid-word."""
    return textwrap.fill(text, width=76, initial_indent=first, subsequent_indent=rest)


def _wrap_note(text: str, first: str, rest: str) -> str:
    """Wraps the first paragraph of a warning; anything after the first newline (a command to copy,
    technical output) is kept exactly as written."""
    head, _, tail = text.partition("\n")
    return _wrap(head, first, rest) + ("\n" + tail if tail else "")


def _fail(what: str, steps: list[str], detail: str = "") -> None:
    """Prints a banner naming what went wrong in plain words, then numbered steps to fix it, then
    exits with a failure code (the .bat files turn that into their own 'did NOT finish' message)."""
    bar = "=" * 60
    print(f"\n{bar}\n{_wrap(f'{MODE} FAILED: {what}')}\n{bar}")
    if detail:
        print(detail.rstrip() + "\n")
    print("What to do:")
    for i, step in enumerate(steps, 1):
        print(_wrap(step, f"  {i}. ", "     "))
    print("\n" + _wrap(HELP_LINE))
    sys.exit(1)


def _warn(text: str) -> None:
    """Records a problem that does not stop the install, and prints it where it happened."""
    WARNINGS.append(text)
    print(_wrap_note(text, "WARNING: ", "         "))


def _permission_fail(path: str, err: Exception) -> None:
    _fail("Windows would not let the installer change a file in your game folder.",
          ["Close KOTOR completely (check the Task Manager for swkotor.exe), and close the Steam "
           "overlay or any mod tool that has the game folder open.",
           "Run Install.bat again. It is safe to run it again: it picks up where it stopped.",
           "If it still fails: right-click Install.bat and choose \"Run as administrator\". Games "
           "inside C:\\Program Files (x86) can need this.",
           "If that fails too, check that the KOTOR folder (and the file listed above) is not set to "
           "read-only: right-click it, Properties, untick Read-only."],
          f"The file Windows refused to change:\n  {path}")


PATCHED_SEEDS_MARKER = os.path.join(REPO_ROOT, "extender", "area_trampolines", "_patched_seeds.json")


def _clear_patched_seeds_marker() -> None:
    """The client remembers which seeds it already patched the game for and skips them. An install or an uninstall
    changes the game files that record describes, so the record is dropped and the next connect patches again."""
    if os.path.isfile(PATCHED_SEEDS_MARKER):
        try:
            os.remove(PATCHED_SEEDS_MARKER)
            print("Cleared the client's record of already-patched seeds, so the next connect patches the game again.")
        except OSError as e:
            _warn(f"Could not clear {PATCHED_SEEDS_MARKER} ({e}). Delete that file by hand so the client patches the "
                  f"game again on its next connect.")


def _file_hash(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _install_binkw32(game_dir: str) -> dict:
    """Captures the real binkw32.dll once (so it can be restored later),
    then swaps in the merged proxy. Same backup filenames the now-retired
    extender/install.ps1 used, so a game folder set up by that script
    before it was retired is still recognized correctly here."""
    real_dll = os.path.join(game_dir, "binkw32.dll")
    real_backup = os.path.join(game_dir, "binkw32_real.dll")

    if not os.path.isfile(real_dll):
        _fail("KOTOR's own binkw32.dll file is missing from the game folder.",
              ["In Steam, right-click Star Wars: Knights of the Old Republic, choose Properties, "
               "Installed Files, then \"Verify integrity of game files\". Steam puts the file back.",
               "Run Install.bat again."],
              f"Looked for:\n  {real_dll}")
    if not os.path.isfile(PROXY_DLL):
        _fail("A file this installer needs is missing from the download.",
              ["Your antivirus may have removed it: binkw32.dll is a game-patching file that "
               "antivirus programs sometimes quarantine. Check its quarantine/protection history "
               "and restore it, or add this folder as an exception.",
               "Otherwise download the PlayerBundle zip again and extract ALL of it (right-click the zip, "
               "Extract All) before running Install.bat. Do not run it from inside the zip."],
              f"Missing file:\n  {PROXY_DLL}")

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

    try:
        shutil.copy2(PROXY_DLL, real_dll)
    except PermissionError as e:
        _permission_fail(real_dll, e)
    print(f"Installed merged proxy -> {real_dll}")

    repo_root_file = os.path.join(game_dir, "ap_repo_root.txt")
    with open(repo_root_file, "w", encoding="ascii", newline="") as f:
        f.write(REPO_ROOT)
    print(f"Wrote {repo_root_file} -> {REPO_ROOT}")

    return {"captured_original": captured, "already_installed": False}


def _uninstall_binkw32(game_dir: str) -> None:
    """Restores the real binkw32.dll from whichever backup exists."""
    real_dll = os.path.join(game_dir, "binkw32.dll")
    real_backup = os.path.join(game_dir, "binkw32_real.dll")

    if os.path.isfile(CAPTURED_ORIG_COPY):
        shutil.copy2(CAPTURED_ORIG_COPY, real_dll)
        print(f"Restored original binkw32.dll from {CAPTURED_ORIG_COPY}")
    elif os.path.isfile(real_backup):
        shutil.copy2(real_backup, real_dll)
        print(f"Restored original binkw32.dll from {real_backup}")
    else:
        _warn("The original binkw32.dll backup could not be found, so it was not restored. In Steam, "
              "right-click Star Wars: Knights of the Old Republic, choose Properties, Installed "
              "Files, then \"Verify integrity of game files\" to put the original back.")
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
        _fail("The download is incomplete (its dist\\Override folder is missing).",
              ["Download the PlayerBundle zip again and extract ALL of it (right-click the zip, "
               "Extract All) before running Install.bat. Do not run it from inside the zip.",
               "If it happens again, your antivirus may be deleting files while you extract: check "
               "its quarantine/protection history."],
              f"Missing folder:\n  {DIST_OVERRIDE}")
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
        _fail("Copying the mod files into your game's Override folder failed.",
              ["Close KOTOR if it is running, then run Install.bat again.",
               "If it fails again, right-click Install.bat and choose \"Run as administrator\".",
               "If it still fails, post a screenshot of this window (it includes the technical message above)."],
              f"Technical message:\n{result.stderr.strip()}")

    return pre_existing


def _check_compiler() -> None:
    """The compiler runs from the extracted download, so there is nothing to copy; only say so plainly if it is missing."""
    if not os.path.isfile(BUNDLED_COMPILER):
        _warn(f"The script compiler is missing from the download ({BUNDLED_COMPILER}). Features that compile scripts will not work. "
              f"Extract the whole zip again, then run the installer again.")


def _pip_install_pykotor() -> None:
    print("Installing pykotor (needed by patch_loot_disturb.py/patch_item_suppression.py/"
          "patch_door_randomizer.py/patch_additional_enemies.py) ...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "setuptools<81", "pykotor", "numpy", "pillow"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        _warn("The 'pykotor' helper library could not be installed (usually no internet connection "
              "or a blocked download). Door randomization, item suppression and extra enemies need "
              "it and will not work until it is installed. To fix: connect to the internet, open a "
              "Command Prompt and run this line, then run Install.bat again:\n"
              f"  \"{sys.executable}\" -m pip install \"setuptools<81\" pykotor numpy pillow\n"
              f"Technical message:\n{result.stderr.strip()}")
    else:
        print("pykotor installed.")


def _build_game_assets(game_dir: str) -> None:
    """The download carries no copies of the game's own scripts, dialogs or art; build_game_assets.py makes the files that are
    edits of them from the player's own KOTOR install (about half a minute)."""
    print("Building the files that are made from your own copy of the game (about half a minute) ...")
    result = subprocess.run(
        [sys.executable, os.path.join(SCRIPT_DIR, "build_game_assets.py"), f"--game-dir={game_dir}"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        _warn("Some of the files that are made from your own copy of the game could not be built. The randomizer will not work "
              "correctly until they are. Check that the KOTOR folder is complete (in Steam: right-click the game, Properties, "
              "Installed Files, Verify integrity of game files), close KOTOR, and run Install.bat again. If the pykotor "
              "library failed to install above, fix that first.\nTechnical message:\n"
              + (result.stdout.strip() + "\n" + result.stderr.strip()).strip())
    else:
        print(result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "Built.")


def _write_state(manifest: dict) -> None:
    os.makedirs(KOTORAP_STATE_DIR, exist_ok=True)
    with open(INSTALL_PATH_MARKER, "w", encoding="utf-8") as f:
        f.write(REPO_ROOT)
    # The Launcher's "KOTOR Client" button (worlds/kotor/__init__.py's
    # launch_kotor_client) must not trust sys.executable to find a real
    # python interpreter -- fine when THIS script runs it (a real
    # interpreter, per Install.bat), but the button itself runs inside
    # the compiled Archipelago Launcher .exe, where sys.executable is the
    # FROZEN LAUNCHER'S OWN exe path, not a python interpreter at all
    # (using it there would just relaunch a confused second Launcher
    # instance instead of KotorClient.py). Recording the REAL interpreter
    # that ran this installer (always a genuine python.exe, since
    # Install.bat invokes `py -3`/`python`) so the button can reuse it
    # instead of guessing.
    with open(PYTHON_PATH_MARKER, "w", encoding="utf-8") as f:
        f.write(sys.executable)
    with open(INSTALL_MANIFEST, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)


def _load_manifest() -> dict | None:
    try:
        with open(INSTALL_MANIFEST, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _find_folder_steps() -> list[str]:
    return ["Find your KOTOR folder: in Steam, right-click Star Wars: Knights of the Old Republic, "
            "choose Manage, then \"Browse local files\". A Windows Explorer window opens on the "
            "right folder (the one containing swkotor.exe).",
            "Click the address bar at the top of that window and copy the path.",
            "Run Install.bat again and paste that path when it asks for your KOTOR folder."]


def _preflight(game_dir: str) -> None:
    """Everything that can be checked BEFORE touching the game folder, so a wrong folder or a broken
    download fails cleanly instead of leaving a half-finished install."""
    shown = f"The folder the installer tried:\n  {game_dir}"
    if game_dir.rstrip("\\/").lower() == DEFAULT_GAME_DIR.lower():
        shown += ("\n(That is the standard Steam location, used because you pressed Enter. "
                  "Your game is installed somewhere else, for example on another drive.)")
    if not os.path.isdir(game_dir):
        _fail("That KOTOR folder does not exist.", _find_folder_steps(), shown)
    if not os.path.isfile(os.path.join(game_dir, "swkotor.exe")):
        if os.path.isfile(os.path.join(game_dir, "swkotor2.exe")):
            _fail("That is the KOTOR 2 folder. This randomizer is for the first game.",
                  ["Use the folder for Star Wars: Knights of the Old Republic (the first game), "
                   "the one containing swkotor.exe."] + _find_folder_steps(), shown)
        _fail("That folder does not look like a KOTOR install (swkotor.exe is not in it).",
              ["Make sure you chose the folder that directly contains swkotor.exe, not a folder "
               "above or below it (for example not the Override or Modules folder)."]
              + _find_folder_steps(), shown)
    missing = [p for p in (DIST_OVERRIDE, SETUP_GAME, PROXY_DLL) if not os.path.exists(p)]
    if missing:
        _fail("The download is incomplete: some of its files are missing.",
              ["Download the PlayerBundle zip again and extract ALL of it (right-click the zip, "
               "Extract All) before running Install.bat. Do not run it from inside the zip.",
               "If files go missing again, your antivirus may be removing them (binkw32.dll in "
               "particular): check its quarantine/protection history and restore them."],
              "Missing:\n" + "\n".join(f"  {p}" for p in missing))
    if not os.path.isfile(os.path.join(game_dir, "binkw32.dll")):
        _fail("KOTOR's own binkw32.dll file is missing from the game folder.",
              ["In Steam, right-click Star Wars: Knights of the Old Republic, choose Properties, "
               "Installed Files, then \"Verify integrity of game files\". Steam puts the file back.",
               "Run Install.bat again."],
              f"Looked for:\n  {os.path.join(game_dir, 'binkw32.dll')}")


def install(game_dir: str) -> None:
    _preflight(game_dir)

    print(f"Installing into {game_dir} ...\n")
    override_pre_existing = _run_setup_game(game_dir)
    print()
    _check_compiler()
    print()
    binkw32_result = _install_binkw32(game_dir)
    print()
    _pip_install_pykotor()
    print()
    _build_game_assets(game_dir)
    print()

    manifest = {
        "game_dir": game_dir,
        "repo_root": REPO_ROOT,
        "override_files": override_pre_existing,  # {filename: was_pre_existing}
        "binkw32": binkw32_result,
    }
    try:
        _write_state(manifest)
    except OSError as e:
        _fail("The installer could not save its record of what it changed.",
              ["Make sure your Windows user folder is writable and the disk is not full.",
               "Run Install.bat again (safe to repeat)."],
              f"Tried to write to:\n  {KOTORAP_STATE_DIR}\n({e})")
    _clear_patched_seeds_marker()
    print(f"Install complete. Recorded state at {INSTALL_MANIFEST}")
    if WARNINGS:
        print("\n" + "-" * 60)
        print(f"The install finished, but {len(WARNINGS)} thing(s) need your attention:")
        for i, w in enumerate(WARNINGS, 1):
            print("\n" + _wrap_note(w, f"  {i}. ", "     "))
        print("-" * 60)
    print("\nNext steps:")
    print(_wrap("To generate or host a seed, copy kotor.apworld (the other download) into the custom_worlds folder of your "
                "Archipelago Launcher install (skip this if you already did, or if someone else hosts for you).", "  1. ", "     "))
    print(_wrap("Start the client: double-click \"Start KOTOR Client.bat\" in this folder (or click \"KOTOR Client\" in the "
                "Archipelago Launcher), then connect to your server. The first connect finishes setting up the game files by itself.", "  2. ", "     "))


def uninstall() -> None:
    manifest = _load_manifest()
    if manifest is None:
        _fail("There is no record of an install to undo.",
              ["If you never finished running Install.bat, there is nothing to uninstall.",
               "If you did install it, to get the game back to normal by hand: in Steam, right-click "
               "Star Wars: Knights of the Old Republic, choose Properties, Installed Files, "
               "\"Verify integrity of game files\". That restores the original binkw32.dll.",
               "Then open your KOTOR folder and delete binkw32_real.dll, ap_repo_root.txt and "
               "nwnnsscomp.exe if they are there. The randomizer's files in the Override folder are "
               "harmless; delete them only if you know which ones they are."],
              f"The installer's record should be here, but is not:\n  {INSTALL_MANIFEST}")

    game_dir = manifest["game_dir"]
    if not os.path.isdir(game_dir):
        _fail("The game folder from the install no longer exists.",
              ["If you moved or reinstalled KOTOR, there is nothing left to undo in the old place, "
               "and you can ignore this.",
               "If you moved it by mistake, move it back to the path above and run Uninstall.bat again.",
               "To clear this leftover record so the message stops appearing, delete the folder "
               "%LOCALAPPDATA%\\KotorAP (paste that into the Windows Explorer address bar to open it)."],
              f"Recorded game folder:\n  {game_dir}")
    print(f"Uninstalling from {game_dir} (recorded at install time) ...\n")

    # patch_loot_disturb.py (Loot Mode's static-template-edit mechanism,
    # see its own docstring) must be included here -- omitting it would
    # leave every loose Override template file it generates behind on
    # uninstall. Also passes --game-dir explicitly: omitting it would
    # make --restore target the hardcoded default install path instead of
    # manifest["game_dir"], silently wrong for anyone who installed to a
    # non-default KOTOR location.
    # Every patcher that rewrites a module file or writes Override files of its own must be listed
    # here; the Galactic Shop and area poll hook patchers were missing and left their edits behind, and the story
    # gate and droid asset patchers after them (gate scripts left in Override would keep gating a vanilla game).
    for name in ("patch_loot_disturb.py", "patch_item_suppression.py", "patch_door_randomizer.py", "patch_additional_enemies.py",
                 "patch_bazaar_tokens.py", "patch_boss_datapads.py", "patch_galactic_shop.py", "patch_area_poll_hooks.py", "patch_story_gates.py",
                 "generate_droid_assets.py", "patch_party_console.py", "build_game_assets.py"):
        result = subprocess.run(
            [sys.executable, os.path.join(SCRIPT_DIR, name), "--restore", f"--game-dir={game_dir}"],
            capture_output=True, text=True,
        )
        print(result.stdout.strip() or f"{name} --restore: done")
        if result.returncode != 0:
            _warn(f"Could not fully undo one of the game-file edits ({name}). Usually this means KOTOR "
                  f"was running or the pykotor library is missing. Close KOTOR and run Uninstall.bat "
                  f"again; if it repeats, use Steam's \"Verify integrity of game files\" to restore "
                  f"the original files.\nTechnical message:\n{result.stderr.strip()}")
    print()

    _uninstall_binkw32(game_dir)
    print()

    if manifest.get("nwnnsscomp_installed_by_us"):      # copied there by an earlier version of this installer
        dest = os.path.join(game_dir, "nwnnsscomp.exe")
        if os.path.isfile(dest):
            os.remove(dest)
            print(f"Removed {dest}")

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

    for path in (INSTALL_PATH_MARKER, PYTHON_PATH_MARKER, INSTALL_MANIFEST):
        if os.path.isfile(path):
            os.remove(path)
    _clear_patched_seeds_marker()
    if WARNINGS:
        print("\n" + "-" * 60)
        print(f"The uninstall finished, but {len(WARNINGS)} thing(s) need your attention:")
        for i, w in enumerate(WARNINGS, 1):
            print("\n" + _wrap_note(w, f"  {i}. ", "     "))
        print("-" * 60)
    else:
        print(f"\nUninstall complete. {game_dir} is back to the way it was before the randomizer.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--game-dir", default=DEFAULT_GAME_DIR,
                         help=r"Your KOTOR install folder, the one with swkotor.exe (default: the standard Steam location).")
    parser.add_argument("--uninstall", action="store_true", help="Reverse a previous install.")
    args = parser.parse_args()

    global MODE
    game_dir = args.game_dir.strip().strip('"').rstrip("\\/ ") or args.game_dir
    try:
        if args.uninstall:
            MODE = "UNINSTALL"
            uninstall()
        else:
            install(game_dir)
    except PermissionError as e:
        _fail("Windows would not let the installer change a file.",
              ["Close KOTOR completely (check the Task Manager for swkotor.exe).",
               "Run this again. It is safe to repeat.",
               "If it still fails, right-click the .bat file and choose \"Run as administrator\"."],
              f"The file Windows refused to change:\n  {e.filename}")
    except SystemExit:
        raise
    except Exception:
        import traceback
        _fail("Something unexpected went wrong.",
              ["Close KOTOR if it is running and try again.",
               "If it fails the same way twice, post a screenshot of this window (it includes the technical message above)."],
              "Technical message:\n" + traceback.format_exc())


if __name__ == "__main__":
    main()
