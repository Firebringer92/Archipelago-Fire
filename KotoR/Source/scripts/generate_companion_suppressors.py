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
from pykotor.resource.formats.rim import read_rim
from pykotor.resource.type import ResourceType

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
MOD_DIR = os.path.join(GAME, "modules")
OVERRIDE = os.path.join(GAME, "Override")
NWNNSSCOMP = r"C:\Program Files (x86)\KotOR Scripting Tool\nwnnsscomp.exe"
SRC_DIR = os.path.join(REPO_ROOT, "extender", "scripts_src")

# name, module, resref, npc_const, diag_code, npc_idx
# npc_idx matches the NPC_* index order used everywhere else (Locations.py's
# COMPANIONS table, CheckCompanions()'s IsAvailableCreature(i) loop): 0
# Bastila, 1 Canderous, 2 Carth, 3 HK-47, 4 Jolee, 5 Juhani, 6 Mission,
# 7 T3-M4, 8 Zaalbar.
COMPANIONS = [
    # Confirmed live module is tar_m03af, NOT tar_m03aa -- tar03_bastila.dlg
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

WRAPPER_TEMPLATE = """// Suppression wrapper for {name}'s real story recruitment script
// (originally {module}'s {resref}, preserved as apo_{name}_orig).
//
// Runs the real script unchanged, then immediately reverses the
// availability grant with RemoveAvailableNPC so the vanilla unlock never
// actually sticks -- the real grant will come from AP later, through the
// existing companion apply script (phase 06).
//
// GUARD (added 2026-08-31): if {npc_const} is ALREADY available when this
// fires, our own companion_{name} AP arm already ran (early item, or an
// admin re-grant) and {name} is already an active party member. Confirmed
// live: running apo_{name}_orig + RemoveAvailableNPC on an
// already-recruited companion kicks them OUT of the active party --
// RemoveAvailableNPC is not the harmless no-op on an active member that
// the vanilla script assumes. So skip the vanilla script and the
// RemoveAvailableNPC in that case; the AP location check still fires
// either way below, since reaching this trigger is the check regardless
// of whether recruitment logic needs to run.
#include "kse"

void main()
{{
    if (!IsAvailableCreature({npc_const}))
    {{
        ExecuteScript("apo_{name}_orig", OBJECT_SELF);
        RemoveAvailableNPC({npc_const});
        KSE_Diag({diag_code}, "AP|SUPPRESSED|companion_{name}");
    }}
    else
    {{
        KSE_Diag({diag_code}, "AP|SUPPRESSED|companion_{name}|skipped_already_recruited");
    }}
    // The check-fire below is atomic with the guard above within this one
    // script call -- no other script (including the regular poll's
    // CheckCompanions()) needs to observe anything here. Report the AP
    // location check directly from here, the only place that reliably
    // knows recruitment was just reached.
    KSE_Diag(22, "AP|CHECK|COMPANION|{npc_idx}");
}}
"""

def main():
    for name, module, resref, npc_const, diag_code, npc_idx in COMPANIONS:
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

        nss_path = os.path.join(SRC_DIR, f"{resref}.nss")
        with open(nss_path, "w") as f:
            f.write(WRAPPER_TEMPLATE.format(
                name=name, module=module, resref=resref,
                npc_const=npc_const, diag_code=diag_code, npc_idx=npc_idx,
            ))
        print(f"  wrote wrapper source -> {nss_path}")

        ncs_path = os.path.join(SRC_DIR, f"{resref}.ncs")
        result = subprocess.run(
            [NWNNSSCOMP, "-c", nss_path, "-o", ncs_path],
            capture_output=True, text=True, cwd=SRC_DIR,
        )
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
