"""
Generates the companion-suppression wrapper pair (preserved original + wrapper
.nss/.ncs) for each companion's real, live, first-time recruitment script,
using the same proven pattern validated live on Carth and Canderous:

    ExecuteScript(<preserved original>, OBJECT_SELF);
    RemoveAvailableNPC(<NPC_X>);
    KSE_Diag(<code>, "AP|SUPPRESSED|companion_<name>");

The preserved original is a byte-exact copy of the real compiled .ncs (no
decompile/recompile round-trip), deployed under a new resref so
ExecuteScript can still invoke the untouched vanilla behavior.

Requires nwnnsscomp.exe (KotOR Scripting Tool) to compile the wrappers.
"""
import os
import subprocess
import sys
from pykotor.resource.formats.rim import read_rim
from pykotor.resource.type import ResourceType

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
MOD_DIR = os.path.join(GAME, "modules")
OVERRIDE = os.path.join(GAME, "Override")
from nwnnsscomp_path import resolve_nwnnsscomp, compile_nss  # noqa: E402 -- see that module's docstring
NWNNSSCOMP = resolve_nwnnsscomp()
SRC_DIR = os.path.join(REPO_ROOT, "extender", "scripts_src")

# name, module, resref, npc_const, diag_code, npc_idx
# npc_idx matches the NPC_* index order used everywhere else (Locations.py's
# COMPANIONS table, CheckCompanions()'s IsAvailableCreature(i) loop): 0
# Bastila, 1 Canderous, 2 Carth, 3 HK-47, 4 Jolee, 5 Juhani, 6 Mission,
# 7 T3-M4, 8 Zaalbar.
COMPANIONS = [
    # Confirmed module is tar_m03af, NOT tar_m03aa -- tar03_bastila.dlg
    # (the real join conversation) only exists in tar_m03af; tar_m03aa's
    # copy of k_ptar_bastpart is unused leftover content.
    ("bastila", "tar_m03af", "k_ptar_bastpart", "NPC_BASTILA", 29, 0),
    ("jolee",   "kas_m24aa", "k_pkas_joleejoin", "NPC_JOLEE",   30, 4),
    ("juhani",  "danm13",    "k_pdan_vandar02",  "NPC_JUHANI",  31, 5),
    ("mission", "tar_m04aa", "k_ptar_addmissio", "NPC_MISSION", 32, 6),
    ("t3m4",    "tar_m02ab", "k_ptar_addt3m4",   "NPC_T3_M4",   33, 7),
    ("hk47",    "tat_m17ac", "k_ptat_hk47add",   "NPC_HK_47",   34, 3),
    ("zaalbar", "tar_m05aa", "k_ptar_addzaal",   "NPC_ZAALBAR", 35, 8),
]

# Per-companion extras layered on top of the shared wrapper. Kept out of
# COMPANIONS because other scripts (package_dist.py) unpack that tuple by
# position. Value: (include name, call made after the check fires).
EXTRA_HOOKS = {
    # Zaalbar's recruit node is the end of the cell-door conversation; this
    # reverts the Mission that k_ptar_trigdoor staged so the scene could run.
    # See extender/scripts_src/ap_zaal_mission.nss.
    "zaalbar": ("ap_zaal_mission", "ZaalbarSceneComplete();"),
}

# Companions whose vanilla recruit script is NOT run by the wrapper, with the
# lines run in its place. Jolee's original ends by opening the party-selection
# screen with Jolee as a forced member (ShowPartySelectionGUI("", -1, NPC_JOLEE))
# after queuing it; the wrapper revokes his availability straight after, so the
# screen opened with a forced companion that no longer exists and the game
# crashed (access violation in swkotor.exe, five seconds after the recruit).
# What the original does besides that is set the story flag and remove his
# placed hut instance, which is all that is reproduced here.
REPLACE_ORIGINAL = {
    "jolee": [
        'SetGlobalBoolean("G_JoleeJoined", TRUE);',
        'DelayCommand(1.0, DestroyObject(OBJECT_SELF));',
    ],
}

# What the vanilla script does BESIDES granting availability, replayed by the wrapper's "already recruited" branch. That branch skips the
# vanilla script on purpose (re-running it plus RemoveAvailableNPC would kick an active member), but a companion who joined early through
# an AP item still reaches this story moment, and skipping the whole script also skipped these effects. The worst case was Bastila:
# her script is what loads the Taris Hideout "escape plan" scene, so with her item received before the swoop race the game never moved on.
# Each list was read straight from the compiled vanilla script. The party-selection screens and fades are deliberately left out.
SKIP_BRANCH_RUN = {
    "bastila": [
        'DelayCommand(0.1, StartNewModule("tar_m02af", "tar02_wpcarbascs", "02"));',
    ],
    "juhani": [
        'SetGlobalBoolean("DAN_JUHANI_JOINED", TRUE);',
        'object oPlacedJuhani = GetObjectByTag("dan13_juhani");',
        'if (GetIsObjectValid(oPlacedJuhani)) DestroyObject(oPlacedJuhani);',
    ],
    "t3m4": [
        'SetGlobalNumber("Tar_JaniceDro", 30);',
    ],
    "zaalbar": [
        'SetAreaUnescapable(FALSE);',
    ],
}

WRAPPER_TEMPLATE = """// Suppression wrapper for {name}'s real story recruitment script
// (originally {module}'s {resref}, preserved as apo_{name}_orig).
//
// Runs the real script unchanged, then immediately reverses the
// availability grant with RemoveAvailableNPC so the vanilla unlock never
// actually sticks -- the real grant will come from AP later, through the
// existing companion apply script (phase 06).
//
// GUARD: if {npc_const} is ALREADY available when this fires, our own
// companion_{name} AP arm already ran (early item, or an admin re-grant)
// and {name} is already an active party member. Running apo_{name}_orig
// + RemoveAvailableNPC on an already-recruited companion kicks them OUT
// of the active party -- RemoveAvailableNPC is not the harmless no-op on
// an active member that the vanilla script assumes. So skip the vanilla
// script and the
// RemoveAvailableNPC in that case; the AP location check still fires
// either way below, since reaching this trigger is the check regardless
// of whether recruitment logic needs to run.
#include "kse"
#include "ap_recruit_marker"
{hook_include}
void main()
{{
    if (!IsAvailableCreature({npc_const}))
    {{
{run_original}
        RemoveAvailableNPC({npc_const});
        KSE_Diag({diag_code}, "AP|SUPPRESSED|companion_{name}");
    }}
    else
    {{
        KSE_Diag({diag_code}, "AP|SUPPRESSED|companion_{name}|skipped_already_recruited");
{skip_run}    }}
    // The check-fire below is atomic with the guard above within this one
    // script call -- no other script (including the regular poll's
    // CheckCompanions()) needs to observe anything here. Report the AP
    // location check directly from here, the only place that reliably
    // knows recruitment was just reached. RecordRecruit also writes the
    // persistent journal marker for this recruit (ap_recruit_marker.nss) so
    // the check survives a missed relay.
    RecordRecruit("{name}", {npc_idx});
{hook_call}}}
"""

def main():
    only = next((a.split("=", 1)[1].split(",") for a in sys.argv[1:] if a.startswith("--only=")), None)
    for name, module, resref, npc_const, diag_code, npc_idx in COMPANIONS:
        if only and name not in only:
            continue
        print(f"--- {name} ({module}:{resref}) ---")

        r = read_rim(os.path.join(MOD_DIR, f"{module}_s.rim"))
        data = None
        for res in r:
            if res.resref.get() == resref and res.restype == ResourceType.NCS:
                data = res.data
                break
        if data is None:
            print(f"  ERROR: {resref} not found in {module}_s.rim, skipping")
            continue

        orig_path = os.path.join(OVERRIDE, f"apo_{name}_orig.ncs")
        with open(orig_path, "wb") as f:
            f.write(data)
        print(f"  preserved original -> {orig_path} ({len(data)} bytes)")

        replacement = REPLACE_ORIGINAL.get(name)
        if replacement:
            run_original = "\n".join(f"        {line}" for line in replacement)
        else:
            run_original = f'        ExecuteScript("apo_{name}_orig", OBJECT_SELF);'
        skip_lines = REPLACE_ORIGINAL.get(name) or SKIP_BRANCH_RUN.get(name) or []
        skip_run = "".join(f"        {line}\n" for line in skip_lines)
        hook = EXTRA_HOOKS.get(name)
        hook_include = f'#include "{hook[0]}"\n' if hook else ""
        hook_call = f"    {hook[1]}\n" if hook else ""

        nss_path = os.path.join(SRC_DIR, f"{resref}.nss")
        with open(nss_path, "w") as f:
            f.write(WRAPPER_TEMPLATE.format(
                name=name, module=module, resref=resref,
                npc_const=npc_const, diag_code=diag_code, npc_idx=npc_idx,
                hook_include=hook_include, hook_call=hook_call, run_original=run_original, skip_run=skip_run,
            ))
        print(f"  wrote wrapper source -> {nss_path}")

        ncs_path = os.path.join(SRC_DIR, f"{resref}.ncs")
        result = compile_nss(nss_path, ncs_path, cwd=SRC_DIR)
        if not os.path.exists(ncs_path):
            print(f"  COMPILE FAILED:\n{result.stdout}\n{result.stderr}")
            continue
        print(f"  compiled -> {ncs_path}")

        deploy_path = os.path.join(OVERRIDE, f"{resref}.ncs")
        with open(ncs_path, "rb") as f:
            wrapper_bytes = f.read()
        with open(deploy_path, "wb") as f:
            f.write(wrapper_bytes)
        print(f"  deployed -> {deploy_path}")

    print("\nDone.")


if __name__ == "__main__":
    # Guarded so package_dist.py can safely `from generate_companion_suppressors
    # import COMPANIONS` for its own file-list derivation without re-running
    # this (which needs nwnnsscomp.exe and a live game dir) as an import
    # side effect.
    main()
