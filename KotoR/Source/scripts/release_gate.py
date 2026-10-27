"""
The release gate: runs every check that can be automated before a release or patch is published, prints the result and saves it as a report. Part of
RELEASE_CHECKLIST.md; it does not replace the steps that need a person (the clean-room install, the in-game test, the sign-off).

  python release_gate.py [--previous OLD_PLAYERBUNDLE.zip] [--mirror C:\\path\\to\\Archipelago-Fire\\KotoR]

Checks (a FAIL exits with status 1):
  1. the poll script kept in extender/scripts_src is the release baseline (the client rewrites it for whatever seed was connected last)
  2. the whole test suite passes on this machine, with the game installed so the tests that read it run too
  3. no file that is derived from the game is in the repository copy (list_game_derived.py applied to the published folder)
  4. check_provenance.py passes on the repository copy and on every release zip in dist/
  5. (information) the non-code files this release adds or changes compared with --previous, for a person to look at
"""
import argparse
import datetime
import glob
import hashlib
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
DEFAULT_MIRROR = r"C:\Users\User\Documents\GitHub\Archipelago-Fire\KotoR"

report = []
failures = []


def say(line=""):
    print(line)
    report.append(line)


def result(name, ok, detail=""):
    say(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def sha1(path):
    with open(path, "rb") as f:
        return hashlib.sha1(f.read()).hexdigest()


def _bundle_version():
    with open(os.path.join(HERE, "package_playerbundle.py"), encoding="utf-8") as f:
        m = re.search(r'^BUNDLE_VERSION\s*=\s*"([^"]+)"', f.read(), re.M)
    return m.group(1) if m else "?"


def check_poll_baseline():
    a = os.path.join(REPO_ROOT, "extender", "scripts_src", "ap_poll_shared.ncs")
    b = os.path.join(REPO_ROOT, "dist", "Override", "ap_poll_shared.ncs")
    ok = os.path.isfile(a) and os.path.isfile(b) and sha1(a) == sha1(b)
    text = ""
    nss = os.path.join(REPO_ROOT, "extender", "scripts_src", "ap_poll_shared.nss")
    if os.path.isfile(nss):
        with open(nss, encoding="utf-8", errors="replace") as f:
            text = f.read()
    leaked = "void CheckBountyCount" in text
    result("poll script is the release baseline", ok and not leaked,
           "" if ok and not leaked else "extender/scripts_src/ap_poll_shared.* is a seed's version (the client rewrote it). Regenerate: "
           "python generate_poll_shared.py --area-randomizer=0 --additional-enemies=0 --no-deploy, then copy dist/Override/ap_poll_shared.ncs over scripts_src's, then package again")


def check_tests():
    proc = subprocess.run([sys.executable, "-m", "pytest", "worlds/kotor/test", "-q", "-p", "no:cacheprovider"],
                          cwd=os.path.join(REPO_ROOT, "Archipelago"), capture_output=True, text=True)
    tail = [ln for ln in proc.stdout.strip().splitlines() if ln.strip()][-1:]
    result("test suite", proc.returncode == 0, tail[0] if tail else "no output")


def check_mirror_has_no_derived(mirror):
    if not os.path.isdir(mirror):
        result("repository copy has no game-derived files", False, f"{mirror} not found")
        return
    import list_game_derived as L
    derived = {os.path.basename(x).lower() for x in L.derived_files()}
    hits = [os.path.relpath(os.path.join(r, f), mirror) for r, _d, fs in os.walk(mirror) if ".git" not in r.split(os.sep) for f in fs if f.lower() in derived]
    result("repository copy has no game-derived files", not hits, ", ".join(hits[:5]))


def check_provenance_everywhere(mirror, zips):
    import check_provenance as cp
    rules = cp.Rules()
    if os.path.isdir(mirror):
        problems, count = cp.check_tree(mirror, rules)
        result(f"provenance: repository copy ({count} files)", not problems, "; ".join(problems[:3]))
    for z in zips:
        problems, count = cp.check_zip(z, rules)
        result(f"provenance: {os.path.basename(z)} ({count} files)", not problems, "; ".join(problems[:3]))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--previous", help="the previous release's PlayerBundle zip, to list what is new")
    ap.add_argument("--mirror", default=DEFAULT_MIRROR, help="the repository's KotoR folder")
    ap.add_argument("--version", help="the release version to check (default: BUNDLE_VERSION in package_playerbundle.py)")
    args = ap.parse_args()
    say(f"Release gate, {datetime.datetime.now():%Y-%m-%d %H:%M}")
    version = args.version or _bundle_version()
    zips = sorted(glob.glob(os.path.join(REPO_ROOT, "dist", f"KOTOR-AP-*-v{version}.zip")))
    say(f"Version {version}; release zips checked: " + (", ".join(os.path.basename(z) for z in zips) or "none found in dist/"))
    if not zips:
        result("release zips exist in dist/", False)
    check_poll_baseline()
    check_tests()
    check_mirror_has_no_derived(args.mirror)
    check_provenance_everywhere(args.mirror, zips)
    bundles = [z for z in zips if "PlayerBundle" in z]
    if args.previous and bundles:
        import check_provenance as cp
        say("")
        say("Non-code files this release adds or changes - a person must look at each and confirm where it came from:")
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cp.compare_zips(args.previous, bundles[-1])
        for ln in buf.getvalue().splitlines():
            say("  " + ln)
    say("")
    say("Still needs a person (see RELEASE_CHECKLIST.md): clean-room install and uninstall from the extracted zip, an in-game test of what changed,")
    say("the history check (paths file) if git history was touched, the licence read for any new third-party file, and the sign-off line in the patch notes.")
    say("")
    say("RESULT: " + ("PASS" if not failures else "FAIL (" + ", ".join(failures) + ")"))
    folder = os.path.join(REPO_ROOT, "docs", "release_reports")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"gate_{datetime.datetime.now():%Y%m%d_%H%M}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(report) + "\n")
    print(f"report saved: {path}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
