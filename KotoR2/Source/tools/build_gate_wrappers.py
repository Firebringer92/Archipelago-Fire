"""Builds the story-gate scripts (kind S in data/gates.json) from the player's own game files.

Story scenes that need a companion (data/companion_scenes.json) are built here too: the scene's own script gets a check joined on (nss/k2ap_scene.nss) that brings the
companion into the party before the scene's dialogue starts; the dispatcher is not involved.

For each gated script name N, an Override script N.ncs replaces the game's: our check (nss/k2ap_gate.nss) joined onto the game's own compiled script
(tools/ncs_merge.py). In a gated module the check runs first and the original runs only when the gate is open; in every other module just that module's original runs.
The original is NOT run through ExecuteScript: a script started that way does not get the event it was started by (GetEnteringObject(), GetScriptParameter(1)), and the gated
scripts read them: the Telos shuttle gave a black screen live on 2026-11-14 because its dialogue option never reached it. Joined this way the original keeps the engine's own event.
When the modules carry different bodies of the script, all of them go into the one file and the module name picks. Nothing from the game is kept in the project: the files
are made from the player's install.
Override beats the game's copy of a script, so no game archive changes. Output goes to compile_staging/gates (not the game): deploying is a separate,
deliberate step with the game closed.

  python tools/build_gate_wrappers.py --dry-run
  python tools/build_gate_wrappers.py
"""
import argparse
import shutil
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

# --out DIR writes the wrappers and the copies of the originals there (default compile_staging/gates); --game-dir D reads the originals from that install
STAGING = os.path.join(ROOT, "compile_staging", "gates")
COMPILER = os.path.join(ROOT, "compile_staging", "research", "nwnnsscomp.exe")

# script -> {module: gate}. Only the gates whose hook is a plain script that can be wrapped. Deferred on purpose (see docs/FIRST_RUN_BUILD_PLAN.md):
#   TEL2 (a_baodur_join, tr_baodurpad) and DXN1 (a_to_iziz) are also companion joins with forced party screens, NAR2 (a_305switch) is large and takes script
#   parameters: they are built together with the companion work (package 2), kinds T and D are built separately.
GATED = {
    "a_201shuttle": {"201TEL": "TEL1"},        # takes script parameters 1 and 2
    "a_load351real": {"301NAR": "NAR1"},
    "a_dhagon": {"502OND": "DXN2", "512OND": "DXN2"},
    "a_begin_battle": {"602DAN": "DAN1"},
    "a_load262": {"006EBO": "FIN2"},
    "a_to851": {"222TEL": "FIN3"},             # takes script parameters 1 and 2
    # Kind T: scripts a trigger or a dialogue entry runs. Held back, the script does nothing, so the trigger fires again on the next visit.
    "a_open_door_ente": {"702KOR": "KOR1"},    # opens the Korriban Academy entrance (dlg kreia_si)
    "tr_vash": {"702KOR": ("KOR2", "GetIsPartyLeader(GetEnteringObject())")},             # the walk-in that finds Vash (+1 on the Jedi count) and starts her conversation
    # The gates that sit next to companion joins: the join itself stays vanilla ("story joins stay vanilla"), the gate holds the story beat in front of it.
    "tr_baodurpad": {"233TEL": ("TEL2", "GetIsPartyLeader(GetEnteringObject())")},       # Bao-Dur taps the shield network (231TEL_Shield_Network)
    "a_to_iziz": {"403DXN": "DXN1"},                                                      # the trip to Iziz, which is also Mandalore's join
    # The Nar Shaddaa fork (Hanharr side and Mira side). Held back, the screen could stay black after the scene's fade-out, so a fade-in is sent as well.
    "a_305switch": {"305NAR": ("NAR2", None, "SetGlobalFadeIn(0.0, 0.5, 0.0, 0.0, 0.0);")},
    "a_fadeto_304": {"303NAR": ("NAR2", None, "SetGlobalFadeIn(0.0, 0.5, 0.0, 0.0, 0.0);")},
    # Kind D, the three whose hook is a plain action script (the Master gates NAR3, DXN3 and DAN2 need dialogue edits and are not built):
    "a_setup_ebo2": {"262TEL": ("TEL3", 'GetGlobalNumber("262TEL_CNPC_Freed") == 1')},      # the Ebon Hawk leaves the Telos academy: opens the galaxy
    "a_to_701kor": {"702KOR": "KOR3"},                                                      # the flight out of the Academy after Sion
    "a_sensor_end": {"902MAL": ("FIN4", "GetScriptParameter(1) == 0")},                     # parameter 0: the way on to 903MAL
    # The Enclave: only the branch that opens the way to the Council is held; the "ruined Enclave" talk before it is not.
    "tr_enclave_cam": {"605DAN": ("FIN1", 'GetIsPartyLeader(GetEnteringObject()) && GetGlobalNumber("650DAN_Rebuilt") != 0')},
}
# Scripts that must do nothing while a condition holds, with no gate message. script -> {module: condition}.
#   701KOR tr_exit702_end locks the Academy door behind the player once Sion has appeared (702KOR_Sion >= 3). While the Vash gate holds her trigger back, the
#   door has to stay open, or the Jedi count could never reach 4 (the hard softlock the gating plan names for KOR2).
HOLD = {
    "tr_exit702_end": {"701KOR": 'K2AP_StoryGates() && !K2AP_GateOff("KOR2") && !K2AP_GateReleased("KOR2") && GetGlobalNumber("702KOR_Vash") != 1'},
}
# Scripts that are not gates but must be followed by the token return: the first visit to 202TEL puts the whole inventory into lockers.
GUARDED = {"my_clear_inv": ["202TEL"]}
# Turret sequences, skipped when the seed says so (K2AP_SkipTurrets, as in KotOR 1). script -> {module: code run instead of the script}. {orig} is the
# module's original script. See docs/MINIGAME_SKIPS.md for what each exit of the minigame would have set.
#   106PER a_load003ebo: loads the 107PER hangar turret. The module load is made here (what the original does at its end: 003EBO_BACKGROUND=0 and StartNewModule
#     107PER at From106PER); running the original through ExecuteScript did not load the module live (the Hawk could not be entered). Setting the minigame as finished first makes 107PER take its own "return from the boarders"
#     path: Kreia is brought back, the talk about her hand plays and the movie leads to the Hawk. 25 is the number of targets (the script constant
#     that 107PER/c_check_alldead compares the dead count with).
#   003EBO a_to_421dxn: the Dxun blockade turret; its exit sets 401DXN_STARTED to 4 and loads the Hawk, which starts the Dxun landing.
#   504OND a_505turret: the Onderon palace turret; its exit only returns to 504OND, so the conversation simply ends there.
TURRETS = {
    "a_load003ebo": {"106PER": 'SetGlobalNumber("107PER_MG_FINISHED", 1); SetGlobalNumber("107PER_MG_DEAD", 25); SetGlobalNumber("107PER_MG_EBON", 0); '
                               'SetGlobalNumber("003EBO_BACKGROUND", 0); StartNewModule("107PER", "From106PER");'},
    "a_to_421dxn": {"003EBO": 'SetGlobalNumber("401DXN_STARTED", 4); StartNewModule("003EBO");'},
    "a_505turret": {"504OND": 'SetGlobalNumber("500OND_Turret", 1);'},
}
# ap_jedi_inc: the Masters' +1 on the Jedi count waits for the token; the three conversations are pointed at it by client/k2_dialogues.py (nss/ap_jedi_inc.nss, nss/k2ap_master.nss)
SPECIAL = ("ap_jedi_inc",)
# Game scripts that get one of our checks joined on (an int script of nss/ that answers non-zero when it did the whole job; the game's script then does not run for that
# call). script -> nss name of the check. k_sp1_generic is the script every Force power runs; nss/k2ap_revit.nss takes over Improved and Master Revitalize only.
SPELLS = {"k_sp1_generic": "k2ap_revit"}
PARAM_SCRIPTS = {"a_201shuttle", "a_to851"}      # read GetScriptParameter: kept, because the original runs in the engine's own call of the script

FAMILY_KEY = {"Telos": "telos", "Nar Shaddaa": "nar", "Dxun/Onderon": "dxn", "Dantooine": "dan", "Korriban": "kor", "Endgame": "endgame"}


def gate_table():
    with open(os.path.join(ROOT, "data", "gates.json"), encoding="utf-8") as f:
        return {g["id"]: g for g in json.load(f)["gates"]}


def scene_table():
    """{script: {MODULE: entry}} from data/companion_scenes.json: the companions a script's scene needs (entry: slots, optional when, again)."""
    with open(os.path.join(ROOT, "data", "companion_scenes.json"), encoding="utf-8") as f:
        scenes = json.load(f)["scenes"]
    out = {}
    for e in scenes:
        if e["module"].upper() in out.setdefault(e["script"].lower(), {}):
            raise ValueError("scene %s/%s is listed twice" % (e["script"], e["module"]))
        out[e["script"].lower()][e["module"].upper()] = e
    return out


def scene_lines(name, module, indent):
    """The lines of the scene check of script `name` in `module` (none when the script has no scene there)."""
    entry = scene_table().get(name, {}).get(module.upper())
    if entry is None:
        return []
    if entry.get("mode") == "unlock":                                                      # unlock: a door that fails to open is unlocked and opened; the original does not run
        test = "if (K2AP_SceneUnlockDoor()) return TRUE;"
        body = ["if (%s)" % entry["when"], "{", "    " + test, "}"] if entry.get("when") else [test]
        return [indent + b for b in body]
    mask = sum(1 << int(slot) for slot in entry["slots"])
    check = "K2AP_SceneLend" if entry.get("mode") == "lend" else "K2AP_SceneEnsure"       # lend: the scene's own script brings the companions in
    body = ['K2AP_Trace("%s", "scene: companions needed (mask %d)");' % (name, mask), "%s(%d);" % (check, mask)]
    if entry.get("mode") == "stage":                                                       # stage: the actor the area lacks is made from the party template
        body = ['K2AP_Trace("%s", "scene: actor needed (slot %d)");' % (name, int(entry["slots"][0])),
                "K2AP_SceneStage(%d, %.2f, %.2f, %.2f, %.2f);" % (int(entry["slots"][0]), entry["x"], entry["y"], entry["z"], entry["facing"])]
        if "reset_flag" in entry:                                                          # a local boolean of the script's owner that marks the scene as played: cleared once
            body.append("K2AP_SceneReset(%d, %d);" % (int(entry["reset_flag"]), int(entry["marker"])))
    if entry.get("mode") == "ring":                                                        # ring: the duel ring's opponent is put at the ring after the fight start
        body = ['K2AP_Trace("%s", "scene: duel ring opponent check");' % name, "K2AP_SceneRing();"]
    body += ["K2AP_SceneEnsureAgain(%d, %.2f);" % (mask, float(d)) for d in entry.get("again", [])]
    if entry.get("when"):
        body = ["if (%s)" % entry["when"], "{"] + ["    " + b for b in body] + ["}"]
    return [indent + b for b in body]


def scene_source(name, modules):
    """The check of a script that only carries a scene (an int script; always FALSE: the original always runs)."""
    lines = ["// generated by tools/build_gate_wrappers.py -- companion scene check for %s (the original always runs)" % name, '#include "k2ap_gate"', '#include "k2ap_scene"', "",
             "int StartingConditional()", "{", "    string sMod = GetStringLowerCase(GetModuleName());"]
    for module in sorted(modules):
        lines += ['    if (sMod == "%s")' % module.lower(), "    {"] + scene_lines(name, module, "        ") + ["        return FALSE;", "    }"]
    lines += ["    return FALSE;", "}", ""]
    return "\n".join(lines)


def wrapper_source(name, gated, variants=None, default=None):
    """The gate check of script `name` as an int script (nss): TRUE = the gate is held and the original must not run. gated: {module: gate id}. `variants`/`default`
    are not needed any more (which original runs is decided by tools/ncs_merge.py) and are accepted only for the callers that still pass them."""
    gates = gate_table()
    lines = ["// generated by tools/build_gate_wrappers.py -- story gate check for %s (TRUE = held back)" % name, '#include "k2ap_gate"'] + (
        ['#include "k2ap_scene"'] if scene_table().get(name) else []) + ["", "int StartingConditional()", "{",
             "    string sMod = GetStringLowerCase(GetModuleName());"]
    for module, entry in sorted(gated.items()):
        gate_id, when, cleanup = (tuple(entry) + (None, None))[:3] if isinstance(entry, tuple) else (entry, None, None)
        g = gates[gate_id]
        test = '!K2AP_GateOpen("%s", "%s", "%s", %d)' % (gate_id, FAMILY_KEY[g["family"]], g["family"], g["tokens_needed"])
        body = ['K2AP_Trace("%s", "reached, gate %s");' % (name, gate_id),
                'if (%s) { K2AP_Trace("%s", "held back by %s"); %sreturn TRUE; }' % (test, name, gate_id, (cleanup + " ") if cleanup else ""),
                'K2AP_Trace("%s", "gate %s open, running the original");' % (name, gate_id)]
        lines += ['    if (sMod == "%s")' % module.lower(), "    {"]
        if when:
            lines += ["        if (%s)" % when, "        {"] + ["            " + b for b in body] + ["        }"]
        else:
            lines += ["        " + b for b in body]
        lines += scene_lines(name, module, "        ")
        lines += ["        return FALSE;", "    }"]
    lines += ["    return FALSE;", "}", ""]
    return "\n".join(lines)


def replace_source(name, bodies, variants=None, default=None, conds=None):
    """The check of script `name` as an int script: TRUE = the original must not run because the code here ran instead. bodies: {module: code}. In that module the code
    runs instead of the script when the condition holds (the seed skips turrets, or conds[module]); otherwise (and in every other module) the module's original runs."""
    lines = ["// generated by tools/build_gate_wrappers.py -- %s: replaced in one module while a condition holds (TRUE = replaced)" % name, '#include "k2ap_gate"', "",
             "int StartingConditional()", "{", "    string sMod = GetStringLowerCase(GetModuleName());"]
    for module, code in sorted(bodies.items()):
        cond = (conds or {}).get(module, "K2AP_SkipTurrets()")
        lines.append('    if (sMod == "%s" && (%s)) { K2AP_Trace("%s", "replaced: %s"); %s return TRUE; }' % (
            module.lower(), cond, name, "held" if conds else "turret sequence skipped", code))
    lines += ["    return FALSE;", "}", ""]
    return "\n".join(lines)


def guard_source(name, variants=None, default=None):
    """What runs after the module's original: the progression tokens come back from the lockers (a void script)."""
    lines = ["// generated by tools/build_gate_wrappers.py -- %s, followed by the return of the progression tokens" % name, '#include "k2ap_gate"', "",
             "void main()", "{",
             "    int nBack = K2AP_TokensFromLockers();", '    K2AP_Trace("%s", "original run; tokens returned from the lockers: " + IntToString(nBack));' % name, "}", ""]
    return "\n".join(lines)


def collect(name):
    """({sha: (bytes, [modules])}, shared copy bytes or None) for every copy of the script the game has."""
    import tsl_data
    from pykotor.resource.type import ResourceType
    bodies = {}
    for base in tsl_data.module_bases():
        for r in tsl_data.module_resources(base):
            if r.restype() == ResourceType.NCS and r.resname().lower() == name:
                data = r.data()
                bodies.setdefault(hashlib.sha1(data).hexdigest(), (data, []))[1].append(base)
    res = tsl_data.inst().resource(name, ResourceType.NCS, [tsl_data.SearchLocation.CHITIN])
    return bodies, (res.data if res is not None else None)


def build_spells(parts, staging, dry_run):
    """The SPELLS scripts: the check joined in front of the game's own compiled script (from the base archives; a mod's copy in Override is not read). Returns the number of problems."""
    import build_area_wrappers as AW
    import ncs_merge
    problems = 0
    for name, check in sorted(SPELLS.items()):
        _, shared = collect(name)
        print("%-16s check %-12s original %s" % (name, check, "found" if shared is not None else "MISSING"))
        if shared is None:
            print("  PROBLEM: the game has no %s" % name)
            problems += 1
            continue
        if dry_run:
            continue
        try:
            with open(os.path.join(ROOT, "nss", check + ".nss"), encoding="utf-8") as f:
                pre = AW.compile_source(parts, check, f.read())
            data = ncs_merge.merge([(shared, None)], pre=pre)
        except (RuntimeError, ncs_merge.MergeError) as e:
            print("  PROBLEM: %s: %s" % (name, e))
            problems += 1
            continue
        with open(os.path.join(staging, name + ".ncs"), "wb") as f:
            f.write(data)
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--game-dir", default=None)
    a = ap.parse_args()
    global STAGING
    if a.out:
        STAGING = os.path.abspath(a.out)
    if a.game_dir:
        os.environ["K2_GAME_DIR"] = a.game_dir
    import k2compile
    import tsl_data
    k2compile.prepare_include_dir(STAGING, os.environ.get("K2_GAME_DIR", tsl_data.GAME))
    problems = 0
    # scripts that are written out in nss/ and compiled as they are
    for special in SPECIAL:
        shutil.copy(os.path.join(ROOT, "nss", special + ".nss"), os.path.join(STAGING, special + ".nss"))
        ok, message = k2compile.compile_script(STAGING, special)
        print("%-16s special replacement %s" % (special, "compiled" if ok else "DID NOT COMPILE"))
        if not ok:
            print("  PROBLEM: %s\n%s" % (special, message[-800:]))
            problems += 1
    work = ([(name, gated, "gate") for name, gated in sorted(GATED.items())]
            + [(name, {m: None for m in mods}, "guard") for name, mods in sorted(GUARDED.items())]
            + [(name, bodies, "replace") for name, bodies in sorted(TURRETS.items())]
            + [(name, {m: "" for m in conds}, "hold") for name, conds in sorted(HOLD.items())])
    other = {n for n, _, _ in work}
    for name, modules in sorted(scene_table().items()):
        modules = {m: e for m, e in modules.items() if not e.get("area")}                 # an area entry script's scene is joined by build_area_wrappers.py
        if not modules:
            continue
        if name in other:
            if name not in GATED:
                raise ValueError("scene script %s is also a guard/replace/hold script: not supported" % name)
            missing_modules = set(modules) - {m.upper() for m in GATED[name]}
            if missing_modules:
                raise ValueError("scene script %s has scenes in %s, which its gate does not cover" % (name, ", ".join(sorted(missing_modules))))
        else:
            work.append((name, {m: None for m in modules}, "scene"))
    import build_area_wrappers as AW
    import ncs_merge
    parts = os.path.join(STAGING, "_parts")                     # the check scripts and the module pickers: parts of the result, not files for Override
    k2compile.prepare_include_dir(parts, os.environ.get("K2_GAME_DIR", tsl_data.GAME))
    for name, gated, kind in work:
        bodies, shared = collect(name)
        # the shared (archive) copy is the default for modules that carry no copy of their own
        distinct = {}
        for h, (data, mods) in bodies.items():
            distinct[h] = (data, list(mods))
        default_hash = None
        if shared is not None:
            default_hash = hashlib.sha1(shared).hexdigest()
            distinct.setdefault(default_hash, (shared, []))
        order = sorted(distinct)
        print("%-16s gated %-22s %d original(s), default %s%s" % (name, ",".join(sorted(gated)), len(order), "yes" if default_hash else "none",
                                                              "  [takes script parameters]" if name in PARAM_SCRIPTS else ""))
        missing = [m for m in gated if not any(m in distinct[h][1] for h in order) and default_hash is None]
        if missing:
            print("  PROBLEM: no original found for %s" % ",".join(missing))
            problems += 1
            continue
        if a.dry_run:
            continue
        try:
            chain = [(distinct[h][0], distinct[h][1]) for h in order if h != default_hash]
            members = []
            for i, (data, mods) in enumerate(chain):
                members.append((data, AW.compile_source(parts, "%s__pick%d" % (name, i + 1), AW.picker_source(mods))))
            if default_hash is not None:
                members.append((distinct[default_hash][0], None))
            pre = post = None
            if kind == "guard":
                post = AW.compile_source(parts, name + "__post", guard_source(name))
            elif kind == "scene":
                pre = AW.compile_source(parts, name + "__pre", scene_source(name, gated))
            elif kind in ("replace", "hold"):
                pre = AW.compile_source(parts, name + "__pre", replace_source(name, gated, None, None, HOLD[name] if kind == "hold" else None))
            else:
                pre = AW.compile_source(parts, name + "__pre", wrapper_source(name, gated))
            data = ncs_merge.merge(members, pre=pre, post=post)
        except (RuntimeError, ncs_merge.MergeError) as e:
            print("  PROBLEM: %s: %s" % (name, e))
            problems += 1
            continue
        with open(os.path.join(STAGING, name + ".ncs"), "wb") as f:
            f.write(data)
    problems += build_spells(parts, STAGING, a.dry_run)
    print("%d problem(s); output in %s" % (problems, STAGING))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
