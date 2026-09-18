"""
Generates the Dantooine Jedi Council companion-gate trampoline family --
see extender/scripts_src/ap_companion_gate.nss's own header for the full
root-cause story (multiple dialogue-branch variants of the Council
wrap-up scene all reposition Bastila+Carth to the courtyard, and get
stuck under companion_mode=ap_gated/none if neither has actually been
received yet).

Each entry is (resref, {module: needs_gate}) -- needs_gate=True means
that module's copy of this resref is part of the companion-gate family
(references bastila/carth/dan13_WP_council, confirmed via disassembly);
False means that module has an unrelated script under the SAME resref
name (a real cross-module naming collision -- e.g. danm14ab's own
k_pdan_cut04/cut05 are different cutscenes, not part of this family) and
must be left running completely untouched via a plain pass-through.

For any resref present in more than one module, the deployed trampoline
uses GetModuleFileName() at runtime to pick the correct preserved
original -- Override resolves by resref name only, with no per-module
scoping, so a single compiled file has to serve every module that
happens to share this name.
"""
import os
import subprocess

from pykotor.resource.formats.rim import read_rim
from pykotor.resource.type import ResourceType

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
MOD_DIR = os.path.join(GAME, "Modules")
OVERRIDE = os.path.join(GAME, "Override")
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nwnnsscomp_path import resolve_nwnnsscomp  # noqa: E402
NWNNSSCOMP = resolve_nwnnsscomp()
SRC_DIR = os.path.join(REPO_ROOT, "extender", "scripts_src")

# resref -> {module: needs_gate}
FAMILY = {
    "k_pdan_cut01": {"danm13": True, "danm14ab": True},
    "k_pdan_cut02": {"danm13": True, "danm14ab": True},
    "k_pdan_cut03": {"danm13": True, "danm14ab": True},
    "k_pdan_cut04": {"danm13": True, "danm14ab": False},
    "k_pdan_cut05": {"danm13": True, "danm14ab": False},
    "k_pdan_cut06": {"danm13": True, "danm14ab": True},
}


def read_module_ncs(module, resref):
    """Reads resref's real compiled bytes directly from module's own RIM
    pair (main .rim first, then _s.rim) -- NOT Installation.resource(),
    which has no module context and can't reliably distinguish two
    different modules' own scripts that happen to share a resref name."""
    for suffix in ("", "_s"):
        path = os.path.join(MOD_DIR, f"{module}{suffix}.rim")
        if not os.path.exists(path):
            continue
        for res in read_rim(path):
            if res.restype == ResourceType.NCS and res.resref.get().lower() == resref.lower():
                return bytes(res.data)
    return None


def orig_name(module, resref):
    return f"apo_{module}_{resref[len('k_pdan_'):]}_orig"


def build_trampoline_source(resref, modules):
    lines = [
        f"// Trampoline for {resref} -- part of the Dantooine Jedi Council",
        "// companion-gate family, see ap_companion_gate.nss's own header for",
        "// the full root-cause story. This exact resref exists identically-",
        "// named but with DIFFERENT real content in more than one module",
        "// (Override resolves by name only, no per-module scoping), so this",
        "// checks GetModuleFileName() to pick the right preserved original.",
        '#include "kse"',
        '#include "ap_companion_gate"',
        "",
        "void main()",
        "{",
        '    string sModule = GetModuleFileName();',
    ]
    mod_list = sorted(modules.keys())
    for i, module in enumerate(mod_list):
        needs_gate = modules[module]
        keyword = "if" if i == 0 else "else if"
        lines.append(f'    {keyword} (sModule == "{module}")')
        lines.append("    {")
        if needs_gate:
            lines.append(f'        HandleBastilaCarthGate("{orig_name(module, resref)}", "{resref}_{module}");')
        else:
            lines.append(f'        ExecuteScript("{orig_name(module, resref)}", OBJECT_SELF);')
        lines.append("    }")
    # Safe fallback: unexpected module context (shouldn't happen in
    # practice) -- prefer to just run whichever original is a real
    # gate-needing one untouched via plain ExecuteScript rather than
    # silently doing nothing.
    fallback_module = mod_list[0]
    lines.append("    else")
    lines.append("    {")
    lines.append(f'        ExecuteScript("{orig_name(fallback_module, resref)}", OBJECT_SELF);')
    lines.append("    }")
    lines.append("}")
    return "\n".join(lines) + "\n"


def main():
    os.makedirs(SRC_DIR, exist_ok=True)
    deployed = []
    for resref, modules in FAMILY.items():
        for module in modules:
            data = read_module_ncs(module, resref)
            if data is None:
                print(f"  MISSING: {module}'s {resref} not found in its own RIM pair -- skipping this module.")
                continue
            oname = orig_name(module, resref)
            opath = os.path.join(SRC_DIR, f"{oname}.ncs")
            with open(opath, "wb") as f:
                f.write(data)
            print(f"  preserved {module}'s {resref} ({len(data)} bytes) -> {oname}.ncs")
            deployed.append(oname)

        nss_path = os.path.join(SRC_DIR, f"{resref}.nss")
        ncs_path = os.path.join(SRC_DIR, f"{resref}.ncs")
        with open(nss_path, "w") as f:
            f.write(build_trampoline_source(resref, modules))
        result = subprocess.run([NWNNSSCOMP, "-c", nss_path, "-o", ncs_path],
                                 capture_output=True, text=True, cwd=SRC_DIR)
        if not os.path.exists(ncs_path):
            print(f"  COMPILE FAILED: {resref}\n{result.stdout}\n{result.stderr}")
            continue
        print(f"  compiled trampoline -> {resref}.ncs")
        deployed.append(resref)

    print()
    for name in deployed:
        src = os.path.join(SRC_DIR, f"{name}.ncs")
        dst = os.path.join(OVERRIDE, f"{name}.ncs")
        with open(src, "rb") as f:
            data = f.read()
        with open(dst, "wb") as f:
            f.write(data)
        print(f"  deployed -> {dst}")

    print(f"\n{len(deployed)} files deployed total.")


if __name__ == "__main__":
    main()
