"""Generates a seed from each player YAML given (default: the alpha template, the test slot and the full template) with the scratch core (ap_core),
so a YAML that does not generate is found before it is handed out. Run tools/package_world.py first so the world in ap_core is current.
Usage: python tools/check_yamls.py [yaml files]"""
import glob
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
CORE = os.path.join(ROOT, "ap_core")
DEFAULT = ["KotOR 2 TSL - Alpha Template.yaml", "KotOR2_test_slot.yaml", "KotOR 2 TSL.yaml"]


def main() -> int:
    files = sys.argv[1:] or [os.path.join(ROOT, "yaml", n) for n in DEFAULT]
    failed = 0
    for f in files:
        players, out = tempfile.mkdtemp(), tempfile.mkdtemp()
        shutil.copy(f, os.path.join(players, "player.yaml"))
        p = subprocess.run([sys.executable, "Generate.py", "--player_files_path", players, "--outputpath", out, "--skip_prog_balancing"],
                           cwd=CORE, capture_output=True, text=True)
        ok = p.returncode == 0 and glob.glob(os.path.join(out, "*.zip"))
        print(("OK    " if ok else "FAILED"), os.path.basename(f))
        if not ok:
            failed += 1
            print("\n".join((p.stdout + p.stderr).strip().splitlines()[-8:]))
        shutil.rmtree(players, ignore_errors=True)
        shutil.rmtree(out, ignore_errors=True)
    return failed


sys.exit(main())
