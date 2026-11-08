"""Builds the candidate repository folder for the KotOR 2 project and checks it for game-derived files.

Nothing in the project's own folders is changed and nothing is written to the GitHub folder: the files are copied into a staging folder (default: a new
temporary folder) laid out as the repository will be (Docs/ and Source/), then tools/check_provenance.py runs on it. The user copies from the staging
folder to the GitHub folder and commits.

The map below is also the path map between the project and the repository. What is NOT staged, and why:
  ap_core, build*, dist, logs, game_backups, yaml_check   not ours / build output / local
  research, compile_staging                               results and tools built from the game's own data and scripts
  docs/ notes other than PUBLIC_DOCS                      working notes (plans, research, story detail); published only once rewritten for readers
  yaml/                                                   generated template and personal test YAMLs; docs/KotOR2_TEMPLATE.yaml is the published template
  assets                                                  templates built from game templates; they are made on the player's machine instead
  nss/nwscript_k2_vanilla.nss, nss/nwscript_k2se.nss      the game's nwscript.nss (the second with our routines appended)
  nss/k2se_classrb_data.nss                               class and feat tables generated from the game's own 2DAs; made on the player's machine
  worlds/kotor2/data                                      a copy of data/*.json made by tools/package_world.py (staged from data/ once)

  python tools/stage_publish.py [--out DIR]
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SKIP_DIRS = {"__pycache__", ".git"}
SKIP_NAMES = {"nwscript_k2_vanilla.nss", "nwscript_k2se.nss", "k2se_classrb_data.nss"}
SKIP_SUFFIX = (".pyc", ".ncs", ".pcode", ".log")
# docs/ holds working notes (research, plans, story detail with spoilers). Only these are published; add a name here when a note has been rewritten for readers.
# Research products and harnesses: kept local. The data files are curated analysis made from the research folder (inputs of the build tools, not read by the world or the
# client); the address table is the extension author's reverse-engineering data (its licence is an open item); the scripts are the in-game research batteries.
RESEARCH_ONLY = {"data": {"area_locations.csv", "location_gate_requirements.csv", "quest_items.json", "k2se_addresses.csv"},
                 "nss": {"a_bet3m4_research.nss", "a_bet3m4_companion_test.nss", "a_bet3m4_poc_wrapper.nss", "k2se_poc_test.nss"}}
PUBLIC_DOCS = {"README.md", "SECURITY.md", "PROVENANCE.md", "RELEASE_CHECKLIST.md"}

# (project folder, file pattern suffixes or None for all, repository folder)
MAP = [
    ("docs", (".md",), "Docs"),
    ("client", (".py",), "Source/client"),
    ("tools", (".py", ".json"), "Source/tools"),
    ("worlds/kotor2", (".py",), "Source/worlds/kotor2"),
    ("worlds/kotor2/test", (".py",), "Source/worlds/kotor2/test"),
    ("data", (".json", ".csv"), "Source/data"),
    ("nss", (".nss",), "Source/nss"),
    ("src", (".cpp", ".h", ".inc", ".def"), "Source/extender/src"),
    ("tests", (".cpp",), "Source/extender/tests"),
]
# the player template (written by hand, checked against the options by worlds/kotor2/test/test_template.py) is the one YAML published; the generated yaml/KotOR 2 TSL.yaml and the test YAMLs are not; the compiler's licence and credits go with the repository, its program does not
SINGLE = [("CMakeLists.txt", "Source/extender/CMakeLists.txt"),
          ("docs/KotOR2_TEMPLATE.yaml", "Docs/KotOR2_TEMPLATE.yaml"),
          ("tools/nwnsc/CREDITS.txt", "Source/tools/nwnsc/CREDITS.txt"),
          ("tools/nwnsc/LICENSE.txt", "Source/tools/nwnsc/LICENSE.txt")]


def stage(out: str):
    count = 0
    for folder, suffixes, dest in MAP:
        src = os.path.join(ROOT, folder)
        if not os.path.isdir(src):
            continue
        for name in sorted(os.listdir(src)):
            p = os.path.join(src, name)
            if not os.path.isfile(p) or name in SKIP_NAMES or name.endswith(SKIP_SUFFIX):
                continue
            if suffixes and not name.lower().endswith(suffixes):
                continue
            if folder == "docs" and name not in PUBLIC_DOCS:
                continue
            if name in RESEARCH_ONLY.get(folder, ()):
                continue
            target = os.path.join(out, dest, name)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(p, target)
            count += 1
    for rel, dest in SINGLE:
        p = os.path.join(ROOT, rel)
        if os.path.isfile(p):
            target = os.path.join(out, dest)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(p, target)
            count += 1
    return count


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None, help="staging folder (must be empty or new); default: a new temporary folder")
    a = ap.parse_args()
    out = a.out or tempfile.mkdtemp(prefix="k2_publish_")
    if os.path.isdir(out) and os.listdir(out):
        print("The staging folder is not empty: %s" % out)
        return 2
    n = stage(out)
    print("staged %d files in %s" % (n, out))
    rc = subprocess.call([sys.executable, os.path.join(ROOT, "tools", "check_provenance.py"), "--root", out,
                          "--manifest", os.path.join(ROOT, "tools", "provenance.json")])
    return rc


if __name__ == "__main__":
    sys.exit(main())
