"""
Generates the store-open marker wrapper pair (preserved original + wrapper
.nss/.ncs) for every script in the game that calls the OpenStore action,
found via a raw bytecode scan (routine 378 / 0x017A).

Unlike companion suppression, these wrappers don't reverse a grant -- there's
nothing to "undo" at store-open time. They just preserve the real script
unchanged (which shows the store UI), then report a snapshot marker
(current credits) via KSE_Diag. The actual purchase-vs-loot correlation and
item suppression happens later, client-side, by diffing this snapshot
against the next poll's reported inventory/credits state -- see
AP_WORLD_NOTES.md for the full design.

Preserved-original resrefs use a short apo_stNN scheme (NN = 00-30) since
Aurora-engine resrefs are capped at 16 characters and some real store script
resrefs are already close to that limit.
"""
import os
import subprocess
from pykotor.resource.formats.rim import read_rim
from pykotor.resource.type import ResourceType

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
MOD_DIR = os.path.join(GAME, "modules")
OVERRIDE = os.path.join(GAME, "Override")
from nwnnsscomp_path import resolve_nwnnsscomp  # noqa: E402 -- see that module's docstring
NWNNSSCOMP = resolve_nwnnsscomp()
SRC_DIR = os.path.join(REPO_ROOT, "extender", "scripts_src")

# (module, resref) pairs -- every script found to call OpenStore via the
# routine-378 byte scan.
STORES = [
    ("danm13", "k_pdan_droids"),
    ("danm13", "k_pdan_generals"),
    ("danm13", "k_pdan_pazaak"),
    ("danm14aa", "k_pdan_adum"),
    ("kas_m22aa", "k_pkas_eli_store"),
    ("kas_m22aa", "k_pkas_jan_store"),
    ("kas_m22ab", "k_pkas_store22ab"),
    ("korr_m33aa", "kor33_czerkstore"),
    ("korr_m33aa", "k_pkor_mikastore"),
    ("korr_m33aa", "k_pkor_weapons"),
    ("liv_m99aa", "yav47_suvam22"),
    ("liv_m99aa", "yav47_suvam23"),
    ("liv_m99aa", "yav47_suvam24"),
    ("manm26aa", "k_pman_openstr"),
    ("manm26ab", "k_pman_yortals"),
    ("manm26ad", "k_pman_merchs"),
    ("manm26ad", "k_pman_merchsk"),
    ("manm26ae", "k_pman_shady"),
    ("manm26ae", "k_pman_tyvarks"),
    ("tar_m02aa", "k_ptar_larrimsto"),
    ("tar_m02ab", "k_ptar_janicesto"),
    ("tar_m02ac", "k_ptar_keblastor"),
    ("tar_m02ac", "k_ptar_zelkastor"),
    ("tar_m03ae", "k_ptar_cardstore"),
    ("tar_m04aa", "k_ptar_igearstor"),
    ("tat_m17ab", "k_ptat_two_store"),
    ("tat_m17ac", "k_ptat_yukastore"),
    ("tat_m17ad", "k_ptat_fazzastor"),
    ("tat_m17af", "k_ptat_junixstor"),
    ("tat_m17ag", "k_ptat_czerkstor"),
    ("tat_m17ag", "k_ptat_gaffistor"),
]

WRAPPER_TEMPLATE = """// Store-open marker wrapper for {resref} (module {module}).
// Not a suppression -- there's nothing to reverse here. Runs the real
// script unchanged (opens the store UI), then reports a credits snapshot
// so the AP client can later correlate "new item + credits dropped since
// this marker" with the next poll's inventory report to infer a purchase
// vs. suppressible loot. See AP_WORLD_NOTES.md.
#include "kse"

void main()
{{
    ExecuteScript("{orig_resref}", OBJECT_SELF);
    object oPC = GetFirstPC();
    KSE_Diag({diag_code}, "AP|STOREOPENED|{resref}|credits=" + IntToString(GetGold(oPC)));
}}
"""

def main():
    for idx, (module, resref) in enumerate(STORES):
        print(f"--- {resref} ({module}) ---")

        r = read_rim(os.path.join(MOD_DIR, f"{module}_s.rim"))
        data = None
        for res in r:
            if res.resref.get() == resref and res.restype == ResourceType.NCS:
                data = res.data
                break
        if data is None:
            print(f"  ERROR: {resref} not found in {module}_s.rim, skipping")
            continue

        orig_resref = f"apo_st{idx:02d}"
        orig_path = os.path.join(OVERRIDE, f"{orig_resref}.ncs")
        with open(orig_path, "wb") as f:
            f.write(data)
        print(f"  preserved original -> {orig_path} ({len(data)} bytes)")

        diag_code = 50 + idx
        nss_path = os.path.join(SRC_DIR, f"{resref}.nss")
        with open(nss_path, "w") as f:
            f.write(WRAPPER_TEMPLATE.format(
                resref=resref, module=module,
                orig_resref=orig_resref, diag_code=diag_code,
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
    # Guarded so package_dist.py can safely `from generate_store_suppressors
    # import STORES` for its own file-list derivation without re-running
    # this (which needs nwnnsscomp.exe and a live game dir) as an import
    # side effect.
    main()
