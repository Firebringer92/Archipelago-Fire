"""Builds the story-gate script wrappers (kind S in data/gates.json) from the player's own game files.

For each gated script name N:
  * every copy of N the game has (one per module that carries its own, plus the shared one) is written as N_orig.ncs, or N_orig_1, N_orig_2 ... when the
    bodies differ; the copies come from the player's install, nothing from the game is kept in the project;
  * an Override script N.ncs replaces it: in a gated module it asks the gate (nss/k2ap_gate.nss) and runs the original only when the gate is open, in every
    other module it just runs that module's original.
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
#   106PER a_load003ebo: loads the 107PER hangar turret. Setting the minigame as finished first makes 107PER take its own "return from the boarders"
#     path: Kreia is brought back, the talk about her hand plays and the movie leads to the Hawk. 25 is the number of targets (the script constant
#     that 107PER/c_check_alldead compares the dead count with).
#   003EBO a_to_421dxn: the Dxun blockade turret; its exit sets 401DXN_STARTED to 4 and loads the Hawk, which starts the Dxun landing.
#   504OND a_505turret: the Onderon palace turret; its exit only returns to 504OND, so the conversation simply ends there.
TURRETS = {
    "a_load003ebo": {"106PER": 'SetGlobalNumber("107PER_MG_FINISHED", 1); SetGlobalNumber("107PER_MG_DEAD", 25); SetGlobalNumber("107PER_MG_EBON", 0); '
                               'ExecuteScript("{orig}", OBJECT_SELF);'},
    "a_to_421dxn": {"003EBO": 'SetGlobalNumber("401DXN_STARTED", 4); StartNewModule("003EBO");'},
    "a_505turret": {"504OND": 'SetGlobalNumber("500OND_Turret", 1);'},
}
# ap_jedi_inc: the Masters' +1 on the Jedi count waits for the token; the three conversations are pointed at it by client/k2_dialogues.py (nss/ap_jedi_inc.nss, nss/k2ap_master.nss)
SPECIAL = ("ap_jedi_inc",)
PARAM_SCRIPTS = {"a_201shuttle", "a_to851"}      # read GetScriptParameter: whether ExecuteScript keeps the parameters is a live test (TEST_QUEUE)

FAMILY_KEY = {"Telos": "telos", "Nar Shaddaa": "nar", "Dxun/Onderon": "dxn", "Dantooine": "dan", "Korriban": "kor", "Endgame": "endgame"}


def gate_table():
    with open(os.path.join(ROOT, "data", "gates.json"), encoding="utf-8") as f:
        return {g["id"]: g for g in json.load(f)["gates"]}


def wrapper_source(name, gated, variants, default):
    """gated: {module: gate id}; variants: [(orig name, [modules])]; default: orig name for every other module, or None."""
    gates = gate_table()
    by_module = {}
    for orig, mods in variants:
        for m in mods:
            by_module[m.lower()] = orig
    lines = ["// generated by tools/build_gate_wrappers.py -- story gate wrapper for %s" % name, '#include "k2ap_gate"', "", "void main()", "{",
             "    string sMod = GetStringLowerCase(GetModuleName());"]
    for module, entry in sorted(gated.items()):
        gate_id, when, cleanup = (tuple(entry) + (None, None))[:3] if isinstance(entry, tuple) else (entry, None, None)
        g = gates[gate_id]
        orig = by_module.get(module.lower(), default)
        test = '!K2AP_GateOpen("%s", "%s", "%s", %d)' % (gate_id, FAMILY_KEY[g["family"]], g["family"], g["tokens_needed"])
        body = ['K2AP_Trace("%s", "reached, gate %s");' % (name, gate_id),
                'if (%s) { K2AP_Trace("%s", "held back by %s"); %sreturn; }' % (test, name, gate_id, (cleanup + " ") if cleanup else ""),
                'K2AP_Trace("%s", "gate %s open, running the original");' % (name, gate_id)]
        lines += ['    if (sMod == "%s")' % module.lower(), "    {"]
        if when:
            lines += ["        if (%s)" % when, "        {"] + ["            " + b for b in body] + ["        }"]
        else:
            lines += ["        " + b for b in body]
        lines += ['        ExecuteScript("%s", OBJECT_SELF);' % orig, "        return;", "    }"]
    for module, orig in sorted(by_module.items()):
        if module in {m.lower() for m in gated}:
            continue
        if orig != default:
            lines.append('    if (sMod == "%s") { ExecuteScript("%s", OBJECT_SELF); return; }' % (module, orig))
    if default:
        lines.append('    ExecuteScript("%s", OBJECT_SELF);' % default)
    lines += ["}", ""]
    return "\n".join(lines)


def replace_source(name, bodies, variants, default, conds=None):
    """bodies: {module: code}. In that module the code runs instead of the script when the condition holds (the seed skips turrets, or conds[module]);
    otherwise (and in every other module) the module's original runs."""
    by_module = {}
    for orig, mods in variants:
        for m in mods:
            by_module[m.lower()] = orig
    lines = ["// generated by tools/build_gate_wrappers.py -- %s: replaced in one module while a condition holds" % name, '#include "k2ap_gate"', "",
             "void main()", "{", "    string sMod = GetStringLowerCase(GetModuleName());"]
    for module, code in sorted(bodies.items()):
        orig = by_module.get(module.lower(), default)
        cond = (conds or {}).get(module, "K2AP_SkipTurrets()")
        lines.append('    if (sMod == "%s" && (%s)) { K2AP_Trace("%s", "replaced: %s"); %s return; }' % (
            module.lower(), cond, name, "held" if conds else "turret sequence skipped", code.replace("{orig}", orig or "")))
    for module, orig in sorted(by_module.items()):
        if orig != default:
            lines.append('    if (sMod == "%s") { ExecuteScript("%s", OBJECT_SELF); return; }' % (module, orig))
    if default:
        lines.append('    ExecuteScript("%s", OBJECT_SELF);' % default)
    lines += ["}", ""]
    return "\n".join(lines)


def guard_source(name, variants, default):
    """Runs the module's original, then brings the progression tokens back from the lockers."""
    lines = ["// generated by tools/build_gate_wrappers.py -- %s, followed by the return of the progression tokens" % name, '#include "k2ap_gate"', "",
             "void main()", "{", "    string sMod = GetStringLowerCase(GetModuleName());"]
    for orig, mods in variants:
        if orig == default:
            continue
        for m in mods:
            lines.append('    if (sMod == "%s") ExecuteScript("%s", OBJECT_SELF);' % (m.lower(), orig))
    if default:
        others = " && ".join('sMod != "%s"' % m.lower() for orig, mods in variants if orig != default for m in mods)
        lines.append("    %sExecuteScript(\"%s\", OBJECT_SELF);" % ("if (%s) " % others if others else "", default))
    lines += ["    int nBack = K2AP_TokensFromLockers();", '    K2AP_Trace("%s", "original run; tokens returned from the lockers: " + IntToString(nBack));' % name, "}", ""]
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
    for name, gated, kind in work:
        bodies, shared = collect(name)
        # the shared (archive) copy is the default for modules that carry no copy of their own
        variants, default = [], None
        distinct = {}
        for h, (data, mods) in bodies.items():
            distinct[h] = (data, list(mods))
        if shared is not None:
            h = hashlib.sha1(shared).hexdigest()
            distinct.setdefault(h, (shared, []))
        order = sorted(distinct)
        for i, h in enumerate(order):
            data, mods = distinct[h]
            orig = name + "_orig" if len(order) == 1 else "%s_orig_%d" % (name, i + 1)
            variants.append((orig, mods))
            if shared is not None and h == hashlib.sha1(shared).hexdigest():
                default = orig
            if not a.dry_run:
                with open(os.path.join(STAGING, orig + ".ncs"), "wb") as f:
                    f.write(data)
        missing = [m for m in gated if not any(m in mods for _, mods in variants) and default is None]
        print("%-16s gated %-22s %d original(s), default %s%s" % (name, ",".join(sorted(gated)), len(variants), default,
                                                              "  [takes script parameters]" if name in PARAM_SCRIPTS else ""))
        if missing:
            print("  PROBLEM: no original found for %s" % ",".join(missing))
            problems += 1
            continue
        if a.dry_run:
            continue
        src = os.path.join(STAGING, name + ".nss")
        with open(src, "w", newline="\n") as f:
            if kind == "guard":
                f.write(guard_source(name, variants, default))
            elif kind == "replace":
                f.write(replace_source(name, gated, variants, default))
            elif kind == "hold":
                f.write(replace_source(name, gated, variants, default, HOLD[name]))
            else:
                f.write(wrapper_source(name, gated, variants, default))
        ncs = os.path.join(STAGING, name + ".ncs")
        if os.path.exists(ncs):
            os.remove(ncs)
        ok, message = k2compile.compile_script(STAGING, name)
        if not ok:
            print("  PROBLEM: %s did not compile:\n%s" % (name, message[-1200:]))
            problems += 1
    print("%d problem(s); output in %s" % (problems, STAGING))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
