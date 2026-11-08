"""The "KOTOR 2 Client" button of the Archipelago Launcher.

The client is not part of the apworld: it works with a separately installed folder (the client's scripts, the payload of compiled game files and the K2SE state
folder), and it cannot be imported from inside the zip. So the button starts it as a subprocess, from where the installer (or tools/register_dev_client.py on a
development machine) recorded it. Three marker files say where things are. They are looked for in %LOCALAPPDATA%\\KotorTwoAP and then in %PROGRAMDATA%\\KotorTwoAP
(a machine-wide install, and the place a program running inside a packaged app can write to: such an app's new files in AppData are redirected where the Launcher cannot see them):
  install_path.txt   the folder that holds KotorTwoClient.py (required)
  core_path.txt      a folder with the Archipelago core (CommonClient.py ...) when the client does not carry its own (optional)
  python_path.txt    a real python.exe: the Launcher is a frozen program whose own sys.executable is not an interpreter (optional; falls back to sys.executable)
Every step is written to %LOCALAPPDATA%\\KotorTwoAP\\launcher.log, and a failure is also shown in a message box: the Launcher has no console to print to.
"""
import os
import subprocess
import sys
import time
import traceback
import typing

STATE_DIR_NAME = "KotorTwoAP"
CLIENT_FILE = "KotorTwoClient.py"


def state_dir() -> str:
    """Where the log is written and the markers are looked for first."""
    return os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), STATE_DIR_NAME)


def marker_dirs() -> typing.List[str]:
    """The folders the markers are looked for in, in order."""
    out = [state_dir()]
    machine = os.environ.get("PROGRAMDATA")
    if machine:
        out.append(os.path.join(machine, STATE_DIR_NAME))
    return out


def read_marker(folder: typing.Union[str, typing.Sequence[str]], name: str) -> typing.Optional[str]:
    """The text of the marker file in the first of the folder(s) that has a non-empty one."""
    for one in [folder] if isinstance(folder, str) else folder:
        try:
            with open(os.path.join(one, name), encoding="utf-8") as f:
                text = f.read().strip()
        except OSError:
            continue
        if text:
            return text
    return None


def plan_launch(folder: typing.Union[str, typing.Sequence[str]], args: typing.Sequence[str], kivy_ok: typing.Callable[[str], bool],
                base_env: typing.Optional[typing.Mapping[str, str]] = None) -> typing.Tuple[typing.Optional[dict], typing.List[str]]:
    """(plan, messages). plan = {command, env, cwd} or None when the client cannot be started; messages are for the player and the log.
    kivy_ok(python) says whether that interpreter can show the client window; if not, --nogui is added (unless --gui or --nogui was given)."""
    messages: typing.List[str] = []
    install = read_marker(folder, "install_path.txt")
    if install is None:
        where = [folder] if isinstance(folder, str) else list(folder)
        return None, ["KOTOR 2 Client: no client install was found (no install_path.txt in %s). Run the installer first, then use this button again." %
                      " or ".join(where)]
    client = os.path.join(install, CLIENT_FILE)
    if not os.path.isfile(client):
        return None, ["KOTOR 2 Client: the recorded install folder (%s) has no %s any more. Was it moved or deleted? Run the installer again." % (install, CLIENT_FILE)]
    python = sys.executable
    recorded = read_marker(folder, "python_path.txt")
    if recorded and os.path.isfile(recorded):
        python = recorded
    else:
        messages.append("KOTOR 2 Client: no usable recorded python (%r); trying %r, which does not work from the frozen Launcher." % (recorded, python))
    core = read_marker(folder, "core_path.txt")
    if core and not os.path.isdir(core):
        messages.append("KOTOR 2 Client: the recorded Archipelago core folder (%s) does not exist; ignoring it." % core)
        core = None
    env = dict(base_env if base_env is not None else os.environ)
    paths = [p for p in (core, install) if p]
    if env.get("PYTHONPATH"):
        paths.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(paths)
    arguments = list(args)
    if "--nogui" not in arguments and "--gui" not in arguments and not kivy_ok(python):
        arguments.append("--nogui")
    # cmd /K keeps the console open after the client ends, so a crash at start can be read; the client runs from the core folder when there is one
    return {"command": ["cmd", "/K", python, client] + arguments, "env": env, "cwd": core or install}, messages


def _kivy_ok(python: str) -> bool:
    try:
        return subprocess.run([python, "-c", "import kivy, kivymd"], capture_output=True, timeout=60,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def show(text: str, error: bool = True) -> None:
    """Tell the player in a window (the Launcher has no console); never raises."""
    try:
        from Utils import messagebox
        messagebox("KOTOR 2 Client", text, error=error)
    except Exception:
        pass


def launch_k2_client(*args: str) -> None:
    folder = state_dir()

    def log(message: str) -> None:
        try:
            os.makedirs(folder, exist_ok=True)
            with open(os.path.join(folder, "launcher.log"), "a", encoding="utf-8") as f:
                f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), message))
        except OSError:
            pass

    try:
        plan, messages = plan_launch(marker_dirs(), args, _kivy_ok)
        for message in messages:
            log(message)
            print(message)
        if plan is None:
            show("\n".join(messages))
            return
        log("starting: %s (cwd %s)" % (" ".join(plan["command"]), plan["cwd"]))
        subprocess.Popen(plan["command"], env=plan["env"], cwd=plan["cwd"], creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
        log("process started")
    except Exception as e:
        log("FAILED:\n" + traceback.format_exc())
        show("The client could not be started: %s\nDetails: %s" % (e, os.path.join(folder, "launcher.log")))
        raise
