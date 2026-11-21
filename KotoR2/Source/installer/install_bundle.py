r"""
The installer of the KOTOR 2 Archipelago player bundle. Run it from a folder that holds the WHOLE extracted bundle (Install.bat does).

What it does, in order:
  1. Checks the game folder (swkotor2.exe), that the game is closed and that the download is complete.
  2. Puts the extension (extender/version.dll) next to the game's exe. A different version.dll that was already there is kept as version_before_k2ap.dll and comes back on uninstall.
  3. Installs the Python libraries the client's own code needs (pykotor, numpy, pillow). The Archipelago libraries are installed by Install.bat before this runs.
  4. Builds the files that are made from YOUR copy of the game (compiled scripts and area files, tools/build_payload.py) into client/payload. Nothing of the game is in the download.
  5. Sets the extension's switches in %LOCALAPPDATA%\K2SE\config.txt (the delivery loop on), and records the game folder for the client.
  6. Writes the three marker files the Archipelago Launcher's "KOTOR 2 Client" button reads (install_path.txt, core_path.txt, python_path.txt).
  7. Records what it did in %LOCALAPPDATA%\KotorTwoAP\install_manifest.json so that --uninstall can undo exactly that.

  python installer/install_bundle.py [--game-dir DIR]
  python installer/install_bundle.py --uninstall

The uninstall takes the seed's files out of Override, puts back the module files and dialog.tlk the client changed, removes version.dll (or puts the earlier one back), takes
the lines it added out of config.txt and deletes the markers. The extracted bundle folder itself is left for the player to delete.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import textwrap
import typing

HERE = os.path.dirname(os.path.abspath(__file__))
BUNDLE = os.path.normpath(os.path.join(HERE, ".."))
EXE = "swkotor2.exe"
DLL_NAME = "version.dll"
DLL_BACKUP = "version_before_k2ap.dll"
STATE_NAME = "KotorTwoAP"
STEAM_DEFAULTS = (
    r"C:\Program Files (x86)\Steam\steamapps\common\Knights of the Old Republic II",
    r"C:\Program Files\Steam\steamapps\common\Knights of the Old Republic II",
    r"C:\GOG Games\Star Wars - KotOR2",
    r"C:\Program Files (x86)\GOG Galaxy\Games\Star Wars - KotOR2",
)
PIP_PACKAGES = ["setuptools<81", "pykotor", "numpy", "pillow"]
# the extension's switches that must be on in a shipped install (the seed's own numbers are written by the client into a marked block of the same file)
SWITCHES = (("disp_enable", "1"), ("disp_period", "3"))
CONFIG_BEGIN = "# --- k2ap begin"

MODE = "INSTALL"                  # "UNINSTALL" for the failure banner
WARNINGS: typing.List[str] = []
HELP_LINE = "If you are stuck, post a screenshot of this whole window where you downloaded the randomizer. Running this again after a fix is safe."


def local_dir() -> str:
    return os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), STATE_NAME)


def machine_dir() -> typing.Optional[str]:
    base = os.environ.get("PROGRAMDATA")
    return os.path.join(base, STATE_NAME) if base else None


def k2se_dir() -> str:
    return os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "K2SE")


def config_path() -> str:
    return os.path.join(k2se_dir(), "config.txt")


def manifest_path() -> str:
    return os.path.join(local_dir(), "install_manifest.json")


# ---- plain-language output ----------------------------------------------------------------------------------------------------------------
def _wrap(text: str, first: str = "", rest: str = "") -> str:
    return textwrap.fill(text, width=76, initial_indent=first, subsequent_indent=rest)


def _wrap_note(text: str, first: str, rest: str) -> str:
    head, _, tail = text.partition("\n")
    return _wrap(head, first, rest) + ("\n" + tail if tail else "")


def _fail(what: str, steps: typing.List[str], detail: str = "") -> None:
    bar = "=" * 60
    print("\n%s\n%s\n%s" % (bar, _wrap("%s FAILED: %s" % (MODE, what)), bar))
    if detail:
        print(detail.rstrip() + "\n")
    print("What to do:")
    for i, step in enumerate(steps, 1):
        print(_wrap(step, "  %d. " % i, "     "))
    print("\n" + _wrap(HELP_LINE))
    sys.exit(1)


def _warn(text: str) -> None:
    WARNINGS.append(text)
    print(_wrap_note(text, "WARNING: ", "         "))


def _permission_fail(path: str) -> None:
    _fail("Windows would not let the installer change a file.",
          ["Close KOTOR 2 completely (check the Task Manager for swkotor2.exe), and close the Steam overlay or any mod tool that has the game folder open.",
           "Run Install.bat again. It is safe to run it again: it picks up where it stopped.",
           "If it still fails: right-click Install.bat and choose \"Run as administrator\". Games inside C:\\Program Files (x86) can need this.",
           "If that fails too, check that the KOTOR 2 folder (and the file listed above) is not set to read-only: right-click it, Properties, untick Read-only."],
          "The file Windows refused to change:\n  %s" % path)


def _find_folder_steps() -> typing.List[str]:
    return ["Find your KOTOR 2 folder: in Steam, right-click Star Wars: Knights of the Old Republic II, choose Manage, then \"Browse local files\". A Windows Explorer window opens "
            "on the right folder (the one containing swkotor2.exe).",
            "Click the address bar at the top of that window and copy the path.",
            "Run Install.bat again and paste that path when it asks for your KOTOR 2 folder."]


# ---- small helpers ------------------------------------------------------------------------------------------------------------------------
def _hash(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def game_running() -> bool:
    if sys.platform != "win32":
        return False
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq " + EXE, "/NH"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return EXE.lower() in out.lower()


def find_game_dir(given: typing.Optional[str]) -> typing.Optional[str]:
    """The game folder to use: the given one (even if wrong, so that the preflight can say why), else the first usual place that holds swkotor2.exe."""
    if given:
        return given
    for folder in STEAM_DEFAULTS:
        if os.path.isfile(os.path.join(folder, EXE)):
            return folder
    return None


def load_manifest() -> typing.Optional[dict]:
    try:
        with open(manifest_path(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def save_manifest(data: dict) -> None:
    os.makedirs(local_dir(), exist_ok=True)
    tmp = manifest_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, manifest_path())


def _bundle(*parts: str) -> str:
    return os.path.join(BUNDLE, *parts)


# ---- the checks before anything is touched -------------------------------------------------------------------------------------------
def required_files() -> typing.List[str]:
    return [_bundle("extender", DLL_NAME), _bundle("client", "KotorTwoClient.py"), _bundle("core", "CommonClient.py"), _bundle("tools", "build_payload.py"),
            _bundle("tools", "nwnsc", "nwnsc.exe"), _bundle("tools", "mdlops", "mdlops.exe")]


def preflight(game_dir: typing.Optional[str]) -> str:
    if not game_dir:
        _fail("The installer could not find KOTOR 2.", _find_folder_steps(), "It looked in the usual Steam and GOG places.")
    shown = "The folder the installer tried:\n  %s" % game_dir
    if not os.path.isdir(game_dir):
        _fail("That KOTOR 2 folder does not exist.", _find_folder_steps(), shown)
    if not os.path.isfile(os.path.join(game_dir, EXE)):
        if os.path.isfile(os.path.join(game_dir, "swkotor.exe")):
            _fail("That is the KOTOR 1 folder. This randomizer is for the second game (The Sith Lords).",
                  ["Use the folder for Star Wars: Knights of the Old Republic II, the one containing swkotor2.exe."] + _find_folder_steps(), shown)
        _fail("That folder does not look like a KOTOR 2 install (swkotor2.exe is not in it).",
              ["Make sure you chose the folder that directly contains swkotor2.exe, not a folder above or below it (for example not the Override or Modules folder)."]
              + _find_folder_steps(), shown)
    missing = [p for p in required_files() if not os.path.isfile(p)]
    if missing:
        _fail("The download is incomplete: some of its files are missing.",
              ["Download the PlayerBundle zip again and extract ALL of it (right-click the zip, Extract All) before running Install.bat. Do not run it from inside the zip.",
               "If files go missing again, your antivirus may be removing them (version.dll, nwnsc.exe and mdlops.exe in particular): check its quarantine or protection history "
               "and restore them, or add this folder as an exception."],
              "Missing:\n" + "\n".join("  " + p for p in missing))
    if "windowsapps" in sys.executable.lower():
        _fail("This Python comes from the Microsoft Store, which cannot work with the game.",
              ["The Store version keeps its files in a hidden private place, so the game would never see the files the client writes for it. Install Python 3.12 or 3.13 "
               "from https://www.python.org/ instead (you can leave the Store one installed).",
               "Run Install.bat again."], "Python found:\n  %s" % sys.executable)
    if game_running():
        _fail("KOTOR 2 is running.", ["Close the game completely (check the Task Manager for swkotor2.exe).", "Run Install.bat again."])
    return os.path.normpath(game_dir)


# ---- the steps ----------------------------------------------------------------------------------------------------------------------------
def install_dll(game_dir: str) -> dict:
    """Copies our version.dll into the game folder; a different one that is already there is kept under another name."""
    ours = _bundle("extender", DLL_NAME)
    target = os.path.join(game_dir, DLL_NAME)
    backup = os.path.join(game_dir, DLL_BACKUP)
    result = {"backed_up": False, "already_ours": False}
    try:
        if os.path.isfile(target):
            if _hash(target) == _hash(ours):
                print("version.dll: already ours, nothing to do.")
                result["already_ours"] = True
                return result
            if os.path.isfile(backup):
                print("%s already exists: not overwriting it (an earlier install kept the other version.dll there)." % DLL_BACKUP)
                result["backed_up"] = True
            else:
                shutil.copy2(target, backup)
                result["backed_up"] = True
                print("A version.dll was already in the game folder (another mod's?). Kept it as %s; Uninstall.bat puts it back." % DLL_BACKUP)
        shutil.copy2(ours, target)
        print("Installed the extension: %s" % target)
    except PermissionError:
        _permission_fail(target)
    return result


def remove_dll(game_dir: str, info: dict) -> None:
    target = os.path.join(game_dir, DLL_NAME)
    backup = os.path.join(game_dir, DLL_BACKUP)
    try:
        if os.path.isfile(backup):
            shutil.copy2(backup, target)
            os.remove(backup)
            print("Put the earlier version.dll back.")
        elif os.path.isfile(target):
            os.remove(target)
            print("Removed %s" % target)
    except PermissionError:
        _fail("Windows would not let the uninstaller remove version.dll.",
              ["Close KOTOR 2 completely, then run Uninstall.bat again."], "The file:\n  %s" % target)


def pip_install() -> None:
    print("Installing the libraries the client needs (%s) ..." % ", ".join(PIP_PACKAGES))
    result = subprocess.run([sys.executable, "-m", "pip", "install"] + PIP_PACKAGES, capture_output=True, text=True)
    if result.returncode != 0:
        _fail("The libraries the client needs could not be installed.",
              ["Make sure this computer is connected to the internet and turn off any VPN or proxy for a moment. The libraries are downloaded while this runs.",
               "Run Install.bat again. It is safe to run more than once.",
               "If it fails again, open a Command Prompt and run this line, then run Install.bat once more:\n  \"%s\" -m pip install %s"
               % (sys.executable, " ".join('"%s"' % p for p in PIP_PACKAGES))],
              "Technical message:\n" + (result.stdout.strip() + "\n" + result.stderr.strip()).strip()[-1500:])
    print("Installed.")


def build_payload(game_dir: str) -> None:
    print("Building the files that are made from your own copy of the game (about a minute; nothing of the game is in the download) ...")
    result = subprocess.run([sys.executable, _bundle("tools", "build_payload.py"), "--game-dir", game_dir], capture_output=True, text=True, timeout=1800)
    text = (result.stdout.strip() + "\n" + result.stderr.strip()).strip()
    if result.returncode != 0:
        _fail("The files made from your copy of the game could not be built.",
              ["Check that the KOTOR 2 folder is complete: in Steam, right-click the game, Properties, Installed Files, Verify integrity of game files.",
               "Close KOTOR 2, then run Install.bat again.",
               "If the pykotor library failed to install above, fix that first."],
              "Technical message:\n" + text[-1800:])
    print(result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "Built.")


def _outside_block(lines: typing.List[str]) -> typing.List[int]:
    """The indexes of the lines of config.txt that are not inside the client's marked block (the seed's own numbers; they are never touched here)."""
    out, inside = [], False
    for i, line in enumerate(lines):
        if line.startswith(CONFIG_BEGIN):
            inside = True
        elif line.startswith("# --- k2ap end"):
            inside = False
        elif not inside:
            out.append(i)
    return out


def _find_switch(lines: typing.List[str], key: str) -> typing.Optional[int]:
    found = None
    for i in _outside_block(lines):
        if lines[i].replace(" ", "").startswith(key + "="):
            found = i
    return found


def set_config() -> dict:
    """Turns the extension's shipping switches on in config.txt, outside the client's marked block. Returns what was added or changed, for the uninstall."""
    os.makedirs(k2se_dir(), exist_ok=True)
    path = config_path()
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        text = ""
    lines = text.splitlines()
    record: typing.Dict[str, typing.Optional[str]] = {}
    for key, value in SWITCHES:
        found = _find_switch(lines, key)
        if found is None:
            lines.append("%s=%s" % (key, value))
            record[key] = None                                    # was not there
        elif lines[found].replace(" ", "") != "%s=%s" % (key, value):
            record[key] = lines[found]                            # the line as it was
            lines[found] = "%s=%s" % (key, value)
    if record:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines) + "\n")
        os.replace(tmp, path)
        print("Set the extension's switches in %s" % path)
    else:
        print("The extension's switches were already set.")
    return record


def unset_config(record: typing.Dict[str, typing.Optional[str]]) -> None:
    path = config_path()
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return
    for key, old in record.items():
        found = _find_switch(lines, key)
        if found is None:
            continue
        if old is None:
            del lines[found]
        else:
            lines[found] = old
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))


def write_markers() -> typing.List[str]:
    """The files the Launcher's button reads. Written to AppData and to ProgramData (the second is where the Launcher finds them even when AppData is redirected)."""
    values = (("install_path.txt", _bundle("client")), ("core_path.txt", _bundle("core")), ("python_path.txt", sys.executable))
    written = []
    for folder in [local_dir(), machine_dir()]:
        if not folder:
            continue
        try:
            os.makedirs(folder, exist_ok=True)
            for name, value in values:
                with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
                    f.write(value)
            written.append(folder)
        except OSError as e:
            if folder == local_dir():
                _fail("The installer could not save its record of where the client is.",
                      ["Make sure your Windows user folder is writable and the disk is not full.", "Run Install.bat again (safe to repeat)."],
                      "Tried to write to:\n  %s\n(%s)" % (folder, e))
            _warn("Could not write the Launcher markers to %s (%s). The \"KOTOR 2 Client\" button may not find the client; use Start_KOTOR2_Client.bat instead." % (folder, e))
    return written


def remove_markers() -> None:
    for folder in [local_dir(), machine_dir()]:
        if not folder:
            continue
        for name in ("install_path.txt", "core_path.txt", "python_path.txt"):
            try:
                os.remove(os.path.join(folder, name))
            except OSError:
                pass


def record_game_dir(game_dir: str) -> None:
    folder = os.path.join(k2se_dir(), "ap")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "game_dir.txt"), "w", encoding="utf-8") as f:
        f.write(game_dir)


# ---- install / uninstall -------------------------------------------------------------------------------------------------------------------
def install(game_dir: typing.Optional[str]) -> None:
    game_dir = preflight(find_game_dir(game_dir))
    print("Installing into %s ...\n" % game_dir)
    manifest = {"game_dir": game_dir, "bundle": BUNDLE, "dll": {}, "config": {}}
    manifest["dll"] = install_dll(game_dir)
    save_manifest(manifest)                                       # recorded at once: an install that stops later can still be undone
    print()
    pip_install()
    print()
    build_payload(game_dir)
    print()
    manifest["config"] = set_config()
    record_game_dir(game_dir)
    manifest["markers"] = write_markers()
    save_manifest(manifest)
    print("\nInstall complete. Recorded at %s" % manifest_path())
    if WARNINGS:
        print("\n" + "-" * 60)
        print("The install finished, but %d thing(s) need your attention:" % len(WARNINGS))
        for i, w in enumerate(WARNINGS, 1):
            print("\n" + _wrap_note(w, "  %d. " % i, "     "))
        print("-" * 60)
    print("\nNext steps:")
    print(_wrap("To generate or host a seed, copy kotor2.apworld (the other download) into the custom_worlds folder of your Archipelago Launcher install "
                "(skip this if someone else hosts for you).", "  1. ", "     "))
    print(_wrap("Start the client: double-click Start_KOTOR2_Client.bat in this folder (or click \"KOTOR 2 Client\" in the Archipelago Launcher), then connect to the server. "
                "The first connect writes the seed's files into the game; if the game is running then, close it and start it again.", "  2. ", "     "))


def revert_seed(game_dir: str) -> typing.List[str]:
    """Takes the seed's files out of the game (the client's own revert: Override, module files, dialog.tlk, the seed's block of config.txt). Returns problems to show."""
    sys.path.insert(0, _bundle("client"))
    try:
        from k2_patch import Patcher
        result = Patcher(game_dir, os.path.join(k2se_dir(), "ap"), config_path=config_path()).revert()
    except Exception as e:                                           # the library may be missing; the rest of the uninstall still runs
        return ["The seed's files could not be taken out of the game (%s). Start the client and type /k2_unpatch, or use Steam's \"Verify integrity of game files\".\n" % e]
    print(result.summary().replace("KOTOR 2 patch:", "Took the seed's files out of the game:"))
    return ["Could not fully undo: %s" % problem for problem in result.errors]


def uninstall() -> None:
    manifest = load_manifest()
    if manifest is None:
        _fail("There is no record of an install to undo.",
              ["If you never finished running Install.bat, there is nothing to uninstall.",
               "If you did install it: in the client type /k2_unpatch, then delete version.dll from your KOTOR 2 folder (put version_before_k2ap.dll back under the name "
               "version.dll if that file is there). In Steam, \"Verify integrity of game files\" restores everything else."],
              "The installer's record should be here, but is not:\n  %s" % manifest_path())
    game_dir = manifest["game_dir"]
    if not os.path.isdir(game_dir):
        _fail("The game folder from the install no longer exists.",
              ["If you moved or reinstalled KOTOR 2, there is nothing left to undo in the old place, and you can ignore this.",
               "If you moved it by mistake, move it back to the path above and run Uninstall.bat again.",
               "To clear this leftover record so the message stops appearing, delete the folder %LOCALAPPDATA%\\KotorTwoAP (paste that into the Explorer address bar)."],
              "Recorded game folder:\n  %s" % game_dir)
    if game_running():
        _fail("KOTOR 2 is running.", ["Close the game completely (check the Task Manager for swkotor2.exe).", "Run Uninstall.bat again."])
    print("Uninstalling from %s ...\n" % game_dir)
    for problem in revert_seed(game_dir):
        _warn(problem)
    print()
    remove_dll(game_dir, manifest.get("dll", {}))
    unset_config(manifest.get("config", {}))
    remove_markers()
    for path in (manifest_path(), os.path.join(k2se_dir(), "ap", "game_dir.txt")):
        try:
            os.remove(path)
        except OSError:
            pass
    if WARNINGS:
        print("\n" + "-" * 60)
        print("The uninstall finished, but %d thing(s) need your attention:" % len(WARNINGS))
        for i, w in enumerate(WARNINGS, 1):
            print("\n" + _wrap_note(w, "  %d. " % i, "     "))
        print("-" * 60)
    else:
        print("\nUninstall complete. %s is back to the way it was before the randomizer. You can delete the extracted bundle folder." % game_dir)


def main() -> None:
    global MODE
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--game-dir", default=None, help="Your KOTOR 2 folder, the one with swkotor2.exe (default: the usual Steam and GOG places).")
    parser.add_argument("--uninstall", action="store_true", help="Reverse a previous install.")
    args = parser.parse_args()
    game_dir = args.game_dir.strip().strip('"').rstrip("\\/ ") if args.game_dir else None
    try:
        if args.uninstall:
            MODE = "UNINSTALL"
            uninstall()
        else:
            install(game_dir or None)
    except PermissionError as e:
        _fail("Windows would not let the installer change a file.",
              ["Close KOTOR 2 completely (check the Task Manager for swkotor2.exe).", "Run this again. It is safe to repeat.",
               "If it still fails, right-click the .bat file and choose \"Run as administrator\"."], "The file Windows refused to change:\n  %s" % e.filename)
    except SystemExit:
        raise
    except Exception:
        import traceback
        _fail("Something unexpected went wrong.",
              ["Close KOTOR 2 if it is running and try again.", "If it fails the same way twice, post a screenshot of this window (it includes the technical message above)."],
              "Technical message:\n" + traceback.format_exc())


if __name__ == "__main__":
    main()
