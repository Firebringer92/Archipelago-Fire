r"""
The NWScript compiler used by every script in this folder that turns an .nss into an .ncs (generate_poll_shared.py, generate_makejedi_suppressor.py,
generate_trampoline_batch.py, patch_item_suppression.py, the suppressor and console generators and the others).

The compiler is nwnsc (tools/nwnsc/nwnsc.exe, MIT and BSD licensed, shipped with its licence text), run as a separate program. It reads the game's
nwscript.nss from the folder it is told to search; build_game_assets.py writes that file into extender/scripts_src from the player's own install.
On a development machine without tools/nwnsc, the KotOR Scripting Tool's nwnnsscomp.exe is used if it is installed.

Every caller does `compile_nss(nss_path, ncs_path, cwd=SRC_DIR, timeout=30)` and checks for a fresh output file afterwards, as it did with nwnnsscomp
(a failed compile leaves any older .ncs untouched). `NWNNSSCOMP = resolve_nwnnsscomp()` is kept for the callers that only test whether a compiler exists.
"""
import os
import subprocess

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NWNSC = os.path.join(REPO_ROOT, "tools", "nwnsc", "nwnsc.exe")
SCRIPTS_SRC = os.path.join(REPO_ROOT, "extender", "scripts_src")
_STANDALONE_TOOL_DEFAULT = r"C:\Program Files (x86)\KotOR Scripting Tool\nwnnsscomp.exe"


def resolve_nwnnsscomp() -> str:
    """Path of the compiler: the bundled nwnsc, else the KotOR Scripting Tool's nwnnsscomp.exe (development machines)."""
    return NWNSC if os.path.isfile(NWNSC) else _STANDALONE_TOOL_DEFAULT


def compile_nss(nss_path, ncs_path, cwd=None, timeout=None):
    """Compiles nss_path to ncs_path. Include files are searched for in cwd (default: the script's own folder), then in extender/scripts_src, which also
    holds the game's nwscript.nss. Returns the finished process (stdout and stderr captured, text mode)."""
    exe = resolve_nwnnsscomp()
    nss_path, ncs_path = os.path.abspath(nss_path), os.path.abspath(ncs_path)
    if not os.path.basename(exe).lower().startswith("nwnsc"):
        return subprocess.run([exe, "-c", nss_path, "-o", ncs_path], capture_output=True, text=True, cwd=cwd, timeout=timeout)
    folders = [os.path.abspath(cwd or os.path.dirname(nss_path)), SCRIPTS_SRC]
    if not any(os.path.isfile(os.path.join(d, "nwscript.nss")) for d in folders):
        return subprocess.CompletedProcess(
            [exe], 1, stdout=("Error: nwscript.nss (the game's script definitions) is not in " + SCRIPTS_SRC + ". Connect the client once, or run "
                              "scripts/build_game_assets.py, so it is written from your KOTOR install, then try again."), stderr="")
    return subprocess.run([exe, "-q", "-i", ";".join(dict.fromkeys(folders)), "-r", ncs_path, nss_path],
                          capture_output=True, text=True, cwd=cwd, timeout=timeout)
