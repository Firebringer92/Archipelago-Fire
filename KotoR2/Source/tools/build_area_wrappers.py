"""Builds the area-entry hooks for every module that already has an OnEnter script.

For each distinct OnEnter script name N used by the game's areas, an Override script N.ncs is written that is the game's own compiled script with our code joined on
behind it (tools/ncs_merge.py): the original runs exactly as it always does, then the delivery dispatcher loop starts (k2se_disp.nss). The original is NOT run through
ExecuteScript: a script started that way does not get the event it was started by, and the game's entry scripts decide with GetEnteringObject() (live, 2026-11-14: the
204TEL Ithorian attack never started). When two modules use the same script name with different bodies, both bodies go into the one script and the module name picks.
Override beats the game's copy of a script, so nothing in the game's archives changes. Remove everything this tool wrote with --remove.
Nothing from the game is kept in the project: the files are made on the player's machine from the player's files.

  python tools/build_area_wrappers.py --dry-run
  python tools/build_area_wrappers.py            # build into the game's Override folder
  python tools/build_area_wrappers.py --remove
The area scripts are read from the player's own module files at run time (nothing about them is stored in the project). Compiled with nwnsc through
tools/k2compile.py, the same as every other script. With --game-dir the folder is named explicitly (otherwise K2_GAME_DIR or the usual install place).
Scripts that the research harness owns (a_bet3m4, a_hatchopen) are skipped unless --with-harness is given; the shipped build needs them hooked as well,
because they are the opening module's OnEnter scripts.
"""
import argparse
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
if "--game-dir" in sys.argv[:-1]:                    # tsl_data reads the game folder when it is imported
    os.environ["K2_GAME_DIR"] = os.path.abspath(sys.argv[sys.argv.index("--game-dir") + 1])
import tsl_data  # noqa: E402
import k2compile  # noqa: E402
import ncs_merge  # noqa: E402
from pykotor.resource.type import ResourceType  # noqa: E402

SKIP = {"a_bet3m4", "a_hatchopen"}
# Never hooked, with or without --with-harness: the story script that makes the player T3-M4 on the Peragus trip (106PER). With our hook around it the screen
# faded out and never came back (the switch into T3-M4 did not complete); with the game's own script alone it works. The dispatcher simply starts in the next area.
# (a_106per_cut, 107PER's entry script, was in this list too while the hook ran the original through ExecuteScript, which lost its entering object.)
NEVER_WRAP = {"a_transformt3m4"}
STAGING = os.path.join(ROOT, "compile_staging", "wrappers")
MANIFEST_NAME = "k2se_area_wrappers.txt"

TAIL_SOURCE = ('#include "k2ap_per"\n#include "k2ap_stand"\n\nvoid main()\n{\n    if (!K2SE_IsPresent()) return;\n'
               '    K2AP_PeragusEnter();                      // shortened_peragus: acts only in 101PER and only with the option (nss/k2ap_per.nss)\n'
               '    K2AP_StandEnter();                        // the Party Console\'s standing companions are made again in each area (nss/k2ap_stand.nss)\n'
               '    if (K2SE_ConfigInt("disp_enable", 0) != 0) DispStart();\n}\n')


def area_scripts():
    """{script name (lower case): [modules]}: the OnEnter script of every module's area file, read from the player's own module files."""
    out = {}
    for module in tsl_data.module_bases():
        for r in tsl_data.module_resources(module):
            if r.restype() == ResourceType.ARE:
                gff = tsl_data.read_gff(r.data())
                n = str(gff.root.get_resref("OnEnter")).strip().lower()
                if n:
                    out.setdefault(n, []).append(module.upper())
                break
    return out


def script_bytes(name, module):
    """The compiled script as module `module` sees it, bypassing Override (the game's own copy)."""
    for r in tsl_data.module_resources(module):
        if r.restype() == ResourceType.NCS and r.resname().lower() == name:
            return r.data()
    res = tsl_data.inst().resource(name, ResourceType.NCS, [tsl_data.SearchLocation.CHITIN])
    return res.data if res is not None else None


def picker_source(modules):
    """An int script that answers non-zero in the given modules (nss, for tools/ncs_merge.py)."""
    test = " || ".join('s == "%s"' % m.lower() for m in modules)
    return "int StartingConditional()\n{\n    string s = GetStringLowerCase(GetModuleName());\n    return %s;\n}\n" % test


def compile_source(work, name, source):
    """Compiles nss text to bytes with nwnsc (NOPs stripped by k2compile); raises RuntimeError with the compiler's message when it fails."""
    with open(os.path.join(work, name + ".nss"), "w", newline="\n") as f:
        f.write(source)
    ncs = os.path.join(work, name + ".ncs")
    if os.path.exists(ncs):
        os.remove(ncs)
    ok, message = k2compile.compile_script(work, name)
    if not ok or not os.path.exists(ncs):
        raise RuntimeError("%s did not compile: %s" % (name, message[-300:]))
    with open(ncs, "rb") as f:
        return f.read()


def scene_pre(work, name):
    """The scene check of an area entry script (data/companion_scenes.json entries marked "area"), compiled to run before the original; None when the script has none."""
    import build_gate_wrappers as GW
    modules = [m for m, e in GW.scene_table().get(name, {}).items() if e.get("area")]
    if not modules:
        return None
    return compile_source(work, name + "__scene", GW.scene_source(name, modules))


def merged(work, name, variants, tail):
    """variants: [(script bytes, [modules])]. The merged script: the scene check (when the script carries one), the original(s), then the tail."""
    bodies = []
    for i, (data, mods) in enumerate(variants):
        picker = None if i == len(variants) - 1 else compile_source(work, "%s__pick%d" % (name, i + 1), picker_source(mods))
        bodies.append((data, picker))
    return ncs_merge.merge(bodies, pre=scene_pre(work, name), post=tail)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--remove", action="store_true")
    ap.add_argument("--out", default=os.path.join(tsl_data.GAME, "override"))
    ap.add_argument("--game-dir", default=None, help="the KOTOR 2 folder (default: K2_GAME_DIR or the usual install place)")
    ap.add_argument("--work", default=STAGING, help="folder for the sources and the compiler's output")
    ap.add_argument("--no-manifest", action="store_true", help="do not write the list of written files (a payload folder holds only files for Override)")
    ap.add_argument("--with-harness", action="store_true", help="hook a_bet3m4 and a_hatchopen too (the shipped build does)")
    a = ap.parse_args()
    skip = set() if a.with_harness else SKIP
    manifest = os.path.join(a.out, MANIFEST_NAME)

    if a.remove:
        if not os.path.exists(manifest):
            print("nothing to remove (no manifest)")
            return 0
        for ln in open(manifest).read().split():
            p = os.path.join(a.out, ln)
            if os.path.exists(p):
                os.remove(p)
                print("removed", ln)
        os.remove(manifest)
        return 0

    os.makedirs(a.out, exist_ok=True)
    work = os.path.abspath(a.work)
    os.makedirs(work, exist_ok=True)
    k2compile.prepare_include_dir(work, tsl_data.GAME)
    wrote = []
    problems = 0
    tail = None
    for name, mods in sorted(area_scripts().items()):
        if name in NEVER_WRAP:
            print("skip %s (the story's own script must run alone)" % name)
            continue
        if name in skip:
            print("skip %s (research harness owns it)" % name)
            continue
        bodies = {}   # sha -> (bytes, [modules])
        for m in mods:
            b = script_bytes(name, m)
            if b is None:
                print("  PROBLEM: %s: script %s not found" % (m, name))
                problems += 1
                continue
            h = hashlib.sha1(b).hexdigest()
            bodies.setdefault(h, (b, []))[1].append(m)
        if not bodies:
            continue
        variants = [bodies[h] for h in sorted(bodies)]
        print("%-22s modules %-18s %d body variant(s)" % (name, ",".join(mods), len(variants)))
        if a.dry_run:
            continue
        try:
            if tail is None:
                tail = compile_source(work, "k2se_ap_tail", TAIL_SOURCE)
            data = merged(work, name, variants, tail)
        except (RuntimeError, ncs_merge.MergeError) as e:
            print("  PROBLEM: %s: %s" % (name, e))
            problems += 1
            continue
        with open(os.path.join(a.out, name + ".ncs"), "wb") as w:
            w.write(data)
        wrote.append(name + ".ncs")
    if not a.dry_run:
        if not a.no_manifest:
            with open(manifest, "w") as f:
                f.write("\n".join(wrote) + "\n")
        print("wrote %d files into %s" % (len(wrote), a.out))
    print("%d problem(s)" % problems)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
