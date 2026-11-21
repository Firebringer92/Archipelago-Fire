"""Runs the client tests. The context test needs the Archipelago core and the K2 world: both come from the scratch copy in ap_core (run
tools/run_world_tests.py once first so the world is synced there). Usage: python tools/run_client_tests.py [suite.py ...]

On GitHub (GITHUB_ACTIONS is set) a failing suite also prints an error annotation with the names of the failed tests, so the reason can be read without opening the log."""
import os
import subprocess
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
CORE = os.environ.get("K2_CORE") or os.path.join(ROOT, "ap_core")      # GitHub's workflow points this at its Archipelago checkout
SUITES = ("test_dispatcher.py", "test_tracker.py", "test_patch.py", "test_gates.py", "test_ncs_merge.py", "test_companions.py", "test_extras.py", "test_bazaar.py", "test_modules.py", "test_shop.py", "test_loot.py", "test_enemies.py", "test_doors.py", "test_crafting.py", "test_assets.py", "test_partycon.py", "test_journal.py", "test_dialogues.py", "test_vendor.py", "test_k2_droid.py", "test_payload.py", "test_status.py", "test_bundle.py", "test_droid_models.py", "test_context.py")


def failure_lines(output: str, limit: int = 12):
    """The lines that name what failed: 'FAIL: test_x (...)', 'ERROR: ...', the last line of each traceback, and a crash that ended the run."""
    lines = output.splitlines()
    found = [l.strip() for l in lines if l.startswith(("FAIL:", "ERROR:"))]
    for i, l in enumerate(lines):
        if l.startswith("Traceback") or l.startswith("FAILED"):
            tail = [x.strip() for x in lines[i:] if x.strip()][-2:]
            found.extend(tail)
    seen, out = set(), []
    for l in found:
        if l not in seen:
            seen.add(l)
            out.append(l)
    return out[:limit]


def main():
    env = dict(os.environ)
    env["PYTHONPATH"] = CORE + os.pathsep + os.path.join(ROOT, "client")
    on_github = bool(os.environ.get("GITHUB_ACTIONS"))
    rc = 0
    for test in sys.argv[1:] or SUITES:
        print("== " + test, flush=True)
        run = subprocess.run([sys.executable, os.path.join(ROOT, "client", test)], cwd=CORE, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
        print(run.stdout, end="", flush=True)
        if run.returncode:
            rc = 1
            names = failure_lines(run.stdout) or ["exit code %d, no failure line found" % run.returncode]
            print("FAILED SUITE %s (exit code %d)" % (test, run.returncode), flush=True)
            if on_github:
                print("::error title=Client test failed: %s::%s" % (test, " | ".join(names).replace("%", "%25").replace("\r", "").replace("\n", "%0A")), flush=True)
    return rc


sys.exit(main())
