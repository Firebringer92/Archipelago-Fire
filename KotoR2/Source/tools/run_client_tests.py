"""Runs the client tests. The context test needs the Archipelago core and the K2 world: both come from the scratch copy in ap_core (run
tools/run_world_tests.py once first so the world is synced there). Usage: python tools/run_client_tests.py"""
import os
import subprocess
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
CORE = os.environ.get("K2_CORE") or os.path.join(ROOT, "ap_core")      # GitHub's workflow points this at its Archipelago checkout


def main():
    env = dict(os.environ)
    env["PYTHONPATH"] = CORE + os.pathsep + os.path.join(ROOT, "client")
    rc = 0
    for test in ("test_dispatcher.py", "test_tracker.py", "test_patch.py", "test_gates.py", "test_companions.py", "test_extras.py", "test_bazaar.py", "test_modules.py", "test_shop.py", "test_loot.py", "test_enemies.py", "test_doors.py", "test_crafting.py", "test_assets.py", "test_journal.py", "test_dialogues.py", "test_vendor.py", "test_payload.py", "test_context.py"):
        print("== " + test)
        rc |= subprocess.call([sys.executable, os.path.join(ROOT, "client", test)], cwd=CORE, env=env)
    return rc


sys.exit(main())
