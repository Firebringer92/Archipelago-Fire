"""Compiles K2 scripts the way the game needs them, from the player's own game files.

  * The compiler's include folder holds the EXTENDED nwscript.nss: the game's own file (read from the install, never stored in the project) followed by our
    declarations of the extender routines (nss/k2se_routines.nss), plus our include files.
  * The compiler is nwnsc (tools/nwnsc, MIT/BSD) when it is present, else the older nwnnsscomp of the development tree. nwnsc puts NOP instructions at some
    jump landing spots and the game stops a script that reaches one, so every script it writes is passed through ncs_nops.strip_nops_file before it is kept.

  prepare_include_dir(folder, game_dir)   write nwscript.nss and copy the include files into folder
  compile_script(folder, name)            folder/name.nss -> folder/name.ncs; returns (ok, message)
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
NWNSC = os.path.join(HERE, "nwnsc", "nwnsc.exe")
NWNNSSCOMP = os.path.join(ROOT, "compile_staging", "research", "nwnnsscomp.exe")
INCLUDES = ("k2se.nss", "k2se_disp.nss", "k2se_poll.nss", "k2ap_seed.nss", "k2ap_gate.nss", "k2ap_comp.nss", "k2ap_master.nss", "k2ap_bazaar.nss", "k2ap_craft.nss", "k2ap_vendor.nss", "k2se_rb.nss")


def game_nwscript(game_dir: str) -> bytes:
    """The game's own nwscript.nss, read from the install (the base archives)."""
    from pykotor.extract.installation import Installation, SearchLocation
    from pykotor.resource.type import ResourceType
    res = Installation(game_dir).resource("nwscript", ResourceType.NSS, [SearchLocation.CHITIN])
    if res is None:
        raise FileNotFoundError("nwscript.nss was not found in the game files at %s" % game_dir)
    return res.data


def extended_nwscript(game_dir: str) -> bytes:
    with open(os.path.join(ROOT, "nss", "k2se_routines.nss"), "rb") as f:
        routines = f.read()
    base = game_nwscript(game_dir)
    # the game's file declares SetAvailableNPCId with upper-case type names, which nwnsc refuses (the old compiler let it through); routine ids are positional
    base = base.replace(b"void SetAvailableNPCId(INT nNPC, OBJECT_ID oidNPC);", b"void SetAvailableNPCId(int nNPC, object oidNPC);")
    return base.rstrip() + b"\r\n\r\n" + routines


def prepare_include_dir(folder: str, game_dir: str, extra: tuple = ()) -> None:
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "nwscript.nss"), "wb") as f:
        f.write(extended_nwscript(game_dir))
    for name in INCLUDES + tuple(extra):
        src = os.path.join(ROOT, "nss", name)
        if os.path.isfile(src):
            shutil.copy(src, os.path.join(folder, name))


def compile_script(folder: str, name: str):
    nss, ncs = os.path.join(folder, name + ".nss"), os.path.join(folder, name + ".ncs")
    if os.path.exists(ncs):
        os.remove(ncs)
    if os.path.isfile(NWNSC):
        side = os.path.join(folder, name + ".nwnsc.ncs")
        if os.path.exists(side):
            os.remove(side)
        out = subprocess.run([NWNSC, "-q", "-i", folder, "-r", side, nss], capture_output=True, text=True, cwd=folder, timeout=300)
        if out.returncode != 0 or not os.path.isfile(side):
            return False, (out.stdout + out.stderr).strip()[-1500:]
        import ncs_nops
        try:
            ncs_nops.strip_nops_file(side)
            os.replace(side, ncs)
        except Exception as e:
            if os.path.isfile(side):
                os.remove(side)
            return False, "NOP removal failed for %s: %s" % (name, e)
        return True, "nwnsc"
    if os.path.isfile(NWNNSSCOMP):
        out = subprocess.run([NWNNSSCOMP, "-c", "-o", name + ".ncs", name + ".nss"], capture_output=True, text=True, cwd=folder, timeout=300)
        return (os.path.isfile(ncs), "nwnnsscomp" if os.path.isfile(ncs) else (out.stdout + out.stderr).strip()[-1500:])
    return False, "no script compiler found (tools/nwnsc/nwnsc.exe)"
