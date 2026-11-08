"""Compiles the class-rebuild script (nss/k2se_rb.nss) with its data include (nss/k2se_classrb_data.nss) into compile_staging/classrb.

The data include is made from the game's own tables by research/classrebuild/build_class_rebuild.py (run it first, or with --regen here); it is game-derived
and never published, so on a player's machine the installer has to generate it from that player's install (the header of the include holds the sha1 of
every source table, so a changed table, for example from TSLRCM, is noticed). Output goes to compile_staging, not the game.

  python tools/build_class_script.py [--regen]
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
STAGING = os.path.join(ROOT, "compile_staging", "classrb")
COMPILER = os.path.join(ROOT, "compile_staging", "research", "nwnnsscomp.exe")
RESEARCH = os.path.join(ROOT, "research", "classrebuild")


def main() -> int:
    if "--regen" in sys.argv:
        subprocess.check_call([sys.executable, os.path.join(RESEARCH, "build_class_rebuild.py")], cwd=RESEARCH)
        shutil.copy(os.path.join(RESEARCH, "k2se_classrb_data.nss"), os.path.join(ROOT, "nss", "k2se_classrb_data.nss"))
    os.makedirs(STAGING, exist_ok=True)
    for name in ("k2se.nss", "k2se_rb.nss", "k2se_classrb_data.nss"):
        shutil.copy(os.path.join(ROOT, "nss", name), os.path.join(STAGING, name))
    shutil.copy(os.path.join(ROOT, "nss", "nwscript_k2se.nss"), os.path.join(STAGING, "nwscript.nss"))
    ncs = os.path.join(STAGING, "k2se_rb.ncs")
    if os.path.exists(ncs):
        os.remove(ncs)
    out = subprocess.run([COMPILER, "-c", "-o", "k2se_rb.ncs", "k2se_rb.nss"], cwd=STAGING, capture_output=True, text=True, timeout=120)
    if not os.path.exists(ncs):
        print("k2se_rb did not compile:\n" + (out.stdout + out.stderr)[-1500:])
        return 1
    print("k2se_rb.ncs: %d bytes in %s" % (os.path.getsize(ncs), STAGING))
    return 0


if __name__ == "__main__":
    sys.exit(main())
