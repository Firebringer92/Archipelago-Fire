"""Tells the Archipelago Launcher's "KOTOR 2 Client" button where this development copy of the client is.

Writes the three marker files that worlds/kotor2/ClientLauncher.py reads, to %LOCALAPPDATA%\\KotorTwoAP and to %PROGRAMDATA%\\KotorTwoAP. The second is where the
Launcher finds them even when this script ran inside a packaged app (such as the Claude desktop app), whose new files in AppData are redirected out of the
Launcher's sight.
  install_path.txt   this project's client folder
  core_path.txt      this project's scratch Archipelago core (ap_core), which holds CommonClient.py and the rest
  python_path.txt    the interpreter that runs this script (a real python.exe, not the Launcher)
The installer does this for players. Usage: python tools/register_dev_client.py
"""
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def main() -> int:
    folders = [os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "KotorTwoAP")]
    if os.environ.get("PROGRAMDATA"):
        folders.append(os.path.join(os.environ["PROGRAMDATA"], "KotorTwoAP"))
    client = os.path.join(ROOT, "client")
    core = os.path.join(ROOT, "ap_core")
    for path, what in ((os.path.join(client, "KotorTwoClient.py"), "the client"), (os.path.join(core, "CommonClient.py"), "the Archipelago core")):
        if not os.path.isfile(path):
            print("%s was not found at %s" % (what, path))
            return 1
    values = (("install_path.txt", client), ("core_path.txt", core), ("python_path.txt", sys.executable))
    for folder in folders:
        try:
            os.makedirs(folder, exist_ok=True)
            for name, value in values:
                with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
                    f.write(value)
            print("written to %s" % folder)
        except OSError as e:
            print("could not write to %s: %s" % (folder, e))
    for name, value in values:
        print("  %-16s %s" % (name, value))
    return 0


if __name__ == "__main__":
    sys.exit(main())
