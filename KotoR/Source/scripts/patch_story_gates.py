r"""
Deploys the Progression System's story gates: custom progression items plus the Override scripts that hold a
story beat until the player owns enough progression items (design: DEVELOPMENT_HISTORY.md section 17). Active only when the
connected seed has progression_system on; with it off, every gate script is removed so the game runs
its vanilla scripts again.

Two kinds of Override script, both listed in GATES below:
  wrap   - our script takes the vanilla name; the vanilla compiled script is copied out of its module's
           _s.rim to Override/<alias>.ncs and the wrapper runs it with ExecuteScript when the gate is open.
  reimpl - our script replaces a vanilla condition script outright (ExecuteScript cannot return a value).
Aliases are short and distinct (resource names are 16 characters); keep it that way when adding gates.

The progression items themselves (ap_tk_<family><1..3>) are written on every run and never removed: a save that
holds one must still be able to load it after the option is switched off.

Usage:
  python patch_story_gates.py                 -- apply or remove, per the connected seed's slot_data
  python patch_story_gates.py --force         -- apply regardless of slot_data (add --area-randomizer for the rando-only gates)
  python patch_story_gates.py --restore       -- remove every gate script
  python patch_story_gates.py --game-dir D    -- non-default install
  python patch_story_gates.py --override-dir D-- write into D instead of <game>/Override (dry run)
"""
import json
import os
import subprocess
import sys

from pykotor.common.language import LocalizedString
from pykotor.common.misc import ResRef
from pykotor.extract.installation import Installation
from pykotor.resource.formats.gff import read_gff, write_gff
from pykotor.resource.formats.rim import read_rim
from pykotor.resource.generics.uti import construct_uti, dismantle_uti
from pykotor.resource.type import ResourceType

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
SRC_DIR = os.path.join(REPO_ROOT, "extender", "scripts_src")
SLOT_DATA_PATH = os.path.join(REPO_ROOT, "extender", "area_trampolines", "_slot_data.json")
from nwnnsscomp_path import resolve_nwnnsscomp  # noqa: E402 -- see that module's docstring
NWNNSSCOMP = resolve_nwnnsscomp()


def _arg_value(flag, default):
    for i, a in enumerate(sys.argv):
        if a == flag and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
        if a.startswith(flag + "="):
            return a.split("=", 1)[1]
    return default


GAME_DIR = _arg_value("--game-dir", DEFAULT_GAME_DIR)
MOD_DIR = os.path.join(GAME_DIR, "modules")
OVERRIDE = _arg_value("--override-dir", os.path.join(GAME_DIR, "Override"))

# family key -> display name. Tags are ap_tk_<key><1..3>, matching ApTokenCount() in ap_gate.nss.
TOKEN_FAMILIES = {
    "tar": "Taris",
    "dan": "Dantooine",
    "tat": "Tatooine",
    "kas": "Kashyyyk",
    "man": "Manaan",
    "kor": "Korriban",
    "unk": "Unknown World",
    "fin": "Star Forge",
}
TOKENS_PER_FAMILY = 3
TOKEN_BASE_ITEM = "g_i_datapad001"  # same known-good icon and model as the progress marker

# name: the vanilla script resref this gate replaces.
# module: the one module whose _s.rim holds the vanilla script to preserve (wrap only).
# alias: where the preserved original is deployed (wrap only).
# src: source file in extender/scripts_src.
GATES = [
    {"name": "k_ptar_kandtalk", "kind": "reimpl", "src": "sg_k_ptar_kandtalk"},
    {"name": "k_ptar_accelused", "kind": "wrap", "module": "tar_m10ac", "alias": "apo_sg_accel", "src": "sg_k_ptar_accelused"},
    {"name": "k_ptar_candmeet0", "kind": "reimpl", "src": "sg_k_ptar_candmeet0"},
    {"name": "k_ptar_candcode", "kind": "reimpl", "src": "sg_k_ptar_candcode"},
    # Dantooine
    {"name": "k_pdan_saber01", "kind": "reimpl", "src": "sg_k_pdan_saber01"},
    {"name": "ap_dan_d1", "kind": "new", "src": "sg_ap_dan_d1"},
    {"name": "ap_dan_d2", "kind": "new", "src": "sg_ap_dan_d2"},
    {"name": "ap_man_m1x", "kind": "new", "src": "sg_ap_man_m1x"},
    {"name": "k_pdan_14juh_02", "kind": "wrap", "module": "danm14ac", "alias": "apo_sg_juh02", "src": "sg_k_pdan_14juh_02"},
    {"name": "k_pdan_juhani10", "kind": "reimpl", "src": "sg_k_pdan_juhani10"},
    {"name": "k_pdan_planet03", "kind": "reimpl", "src": "sg_k_pdan_planet03"},
    {"name": "k_pdan_planet12", "kind": "reimpl", "src": "sg_k_pdan_planet12"},
    {"name": "k_pdan_planet01", "kind": "reimpl", "src": "sg_k_pdan_planet01"},
    # Tatooine
    {"name": "k_ptat_noambush", "kind": "reimpl", "src": "sg_k_ptat_noambush"},
    {"name": "k_ptat_ambushed", "kind": "reimpl", "src": "sg_k_ptat_ambushed"},
    {"name": "k_ptat_banthardy", "kind": "reimpl", "src": "sg_k_ptat_banthardy"},
    {"name": "k_tat_pla_actmap", "kind": "reimpl", "src": "sg_k_tat_pla_actmap"},
    {"name": "k_ptat_starcut", "kind": "wrap", "module": "tat_m18ac", "alias": "apo_sg_tatstar", "src": "sg_k_ptat_starcut",
     "extra_wraps": [{"module": "kas_m25aa", "alias": "apo_sg_tatstarx"}]},
    {"name": "k_ptat_spwnbanth", "kind": "reimpl", "src": "sg_k_ptat_spwnbanth"},
    {"name": "k_ptat18ac_heart", "kind": "wrap", "module": "tat_m18ac", "alias": "apo_sg_tat18hb", "src": "sg_k_ptat18ac_heart"},
    # Manaan
    {"name": "k_pman_planet25", "kind": "reimpl", "src": "sg_k_pman_planet25"},
    {"name": "k_pman_planet95", "kind": "reimpl", "src": "sg_k_pman_planet95"},
    {"name": "k_pman_planet34", "kind": "reimpl", "src": "sg_k_pman_planet34"},
    {"name": "demo_trig03", "kind": "reimpl", "src": "sg_demo_trig03"},
    {"name": "k_pman_starmap06", "kind": "wrap", "module": "manm28ad", "alias": "apo_sg_mmap06", "src": "sg_k_pman_starmap06"},
    {"name": "k_pman_door08", "kind": "reimpl", "src": "sg_k_pman_door08"},
    # Kashyyyk
    {"name": "k_pkas_poachove2", "kind": "reimpl", "src": "sg_k_pkas_poachove2"},
    {"name": "k_pkas_poachover", "kind": "reimpl", "src": "sg_k_pkas_poachover"},
    {"name": "k_pkas_compudown", "kind": "reimpl", "src": "sg_k_pkas_compudown"},
    {"name": "k_pkas_freydead2", "kind": "reimpl", "src": "sg_k_pkas_freydead2"},
    {"name": "k_pkas_freyyhelp", "kind": "reimpl", "src": "sg_k_pkas_freyyhelp"},
    {"name": "k_pkas_freyydead", "kind": "reimpl", "src": "sg_k_pkas_freyydead"},
    {"name": "k_pkas_chuuntrig", "kind": "reimpl", "src": "sg_k_pkas_chuuntrig"},
    # Korriban
    {"name": "ap_kor_ko1", "kind": "new", "src": "sg_ap_kor_ko1"},
    {"name": "ap_kor_ko1x", "kind": "new", "src": "sg_ap_kor_ko1x"},
    {"name": "k35_uth_presfini", "kind": "reimpl", "src": "sg_k35_uth_presfini"},
    {"name": "k_pkor_star_map", "kind": "wrap", "module": "korr_m39aa", "alias": "apo_sg_korstar", "src": "sg_k_pkor_star_map"},
    {"name": "ap_kor_st_lash", "kind": "new", "src": "sg_ap_kor_st_lash"},
    {"name": "ap_kor_st_mekel", "kind": "new", "src": "sg_ap_kor_st_mekel"},
    {"name": "ap_kor_st_shaa", "kind": "new", "src": "sg_ap_kor_st_shaa"},
    {"name": "ap_kor_st_lashh", "kind": "new", "src": "sg_ap_kor_st_lashh"},
    {"name": "ap_kor_st_shaam", "kind": "new", "src": "sg_ap_kor_st_shaam"},
    # Unknown World and Star Forge
    {"name": "k_punk_shieldoff", "kind": "dispatch", "aliases": {"unk_m44ac": "apo_sg_shldac", "unk_m44aa": "apo_sg_shldaa"}, "src": "sg_k_punk_shieldoff"},
    {"name": "k_punk_disfldoff", "kind": "wrap", "module": "unk_m44ac", "alias": "apo_sg_disfld", "src": "sg_k_punk_disfldoff"},
    {"name": "k_psta_init_mala", "kind": "reimpl", "src": "sg_k_psta_init_mala"},
    {"name": "ap_unk_u1", "kind": "new", "src": "sg_ap_unk_u1"},
    {"name": "ap_unk_u2", "kind": "new", "src": "sg_ap_unk_u2"},
    {"name": "ap_unk_u3", "kind": "new", "src": "sg_ap_unk_u3"},
    # Area randomizer only: the Upper City elevator guard no longer needs the armor (see the .nss header).
    {"name": "k_ptar_alertsith", "kind": "wrap", "module": "tar_m02ab", "alias": "apo_sg_alertsith",
     "src": "sg_k_ptar_alertsith", "needs": "area_randomizer"},
]


def write_token_templates(installation):
    src = installation.resource(TOKEN_BASE_ITEM, ResourceType.UTI)
    if src is None:
        sys.exit(f"vanilla {TOKEN_BASE_ITEM}.uti not found -- is --game-dir a real KOTOR install?")
    os.makedirs(OVERRIDE, exist_ok=True)
    count = 0
    for key, label in TOKEN_FAMILIES.items():
        for n in range(1, TOKENS_PER_FAMILY + 1):
            resref = f"ap_tk_{key}{n}"
            uti = construct_uti(read_gff(src.data))
            uti.resref = ResRef(resref)
            uti.tag = resref
            uti.name = LocalizedString.from_english(f"{label} Progression {n}")
            uti.description = LocalizedString.from_english(
                f"An Archipelago progression item for {label}. Story events on {label} wait for enough of "
                "these. Can't be sold, dropped, or destroyed.")
            uti.plot = 1
            uti.stack_size = 1
            data = bytearray()
            write_gff(dismantle_uti(uti), data)
            with open(os.path.join(OVERRIDE, f"{resref}.uti"), "wb") as f:
                f.write(bytes(data))
            count += 1
    return count


def _read_module_script(module, resref):
    path = os.path.join(MOD_DIR, f"{module}_s.rim")
    for res in read_rim(path):
        if res.resref.get().lower() == resref.lower() and res.restype == ResourceType.NCS:
            return res.data
    return None


def _compile(src_name):
    nss = os.path.join(SRC_DIR, f"{src_name}.nss")
    ncs = os.path.join(SRC_DIR, f"{src_name}.ncs")
    mtime_before = os.path.getmtime(ncs) if os.path.exists(ncs) else None
    result = subprocess.run([NWNNSSCOMP, "-c", nss, "-o", ncs], capture_output=True, text=True, cwd=SRC_DIR, timeout=60)
    fresh = os.path.exists(ncs) and (mtime_before is None or os.path.getmtime(ncs) != mtime_before)
    if not fresh or "Compilation aborted" in result.stdout or "Error:" in result.stdout:
        print(f"  COMPILE FAILED: {src_name}\n{result.stdout}\n{result.stderr}")
        return None
    with open(ncs, "rb") as f:
        return f.read()


def _slot_data():
    try:
        with open(SLOT_DATA_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _gate_wanted(gate, slot):
    need = gate.get("needs")
    return not need or bool(slot.get(need))


def apply_gates(slot):
    deployed = 0
    wanted = 0
    for gate in GATES:
        name = gate["name"]
        if not _gate_wanted(gate, slot):
            continue
        wanted += 1
        if gate["kind"] == "dispatch":
            # One vanilla name, differently compiled in several modules: each module's original is kept under its own alias
            # and the wrapper picks by module.
            missing = False
            for module, alias in gate["aliases"].items():
                orig = _read_module_script(module, name)
                if orig is None:
                    print(f"  {name}: vanilla script not found in {module}_s.rim -- gate NOT applied")
                    missing = True
                    break
                with open(os.path.join(OVERRIDE, f"{alias}.ncs"), "wb") as f:
                    f.write(orig)
            if missing:
                continue
        if gate["kind"] == "wrap":
            orig = _read_module_script(gate["module"], name)
            if orig is None:
                print(f"  {name}: vanilla script not found in {gate['module']}_s.rim -- gate NOT applied")
                continue
            alias_path = os.path.join(OVERRIDE, f"{gate['alias']}.ncs")
            with open(alias_path, "wb") as f:
                f.write(orig)
            # Same script name compiled differently in other modules: keep each module's original under its own alias.
            for extra in gate.get("extra_wraps", []):
                extra_orig = _read_module_script(extra["module"], name)
                if extra_orig is None:
                    print(f"  {name}: vanilla script not found in {extra['module']}_s.rim -- gate NOT applied")
                    break
                with open(os.path.join(OVERRIDE, f"{extra['alias']}.ncs"), "wb") as f:
                    f.write(extra_orig)
            else:
                extra_orig = True
            if extra_orig is None:
                continue
        data = _compile(gate["src"])
        if data is None:
            continue
        with open(os.path.join(OVERRIDE, f"{name}.ncs"), "wb") as f:
            f.write(data)
        deployed += 1
        print(f"  {name}: {gate['kind']} deployed")
    return deployed, wanted


def _aliases(gate):
    if gate["kind"] == "dispatch":
        return list(gate["aliases"].values())
    if gate["kind"] != "wrap":
        return []
    return [gate["alias"]] + [e["alias"] for e in gate.get("extra_wraps", [])]


def _ours(path, src):
    """True when the Override file is the script this patcher compiled, so a file another feature deployed under
    the same name (the droid wrapper for k_ptar_alertsith) is never removed."""
    built = os.path.join(SRC_DIR, f"{src}.ncs")
    if not (os.path.isfile(path) and os.path.isfile(built)):
        return False
    with open(path, "rb") as a, open(built, "rb") as b:
        return a.read() == b.read()


def remove_gates():
    removed = 0
    for gate in GATES:
        main_path = os.path.join(OVERRIDE, f"{gate['name']}.ncs")
        if _ours(main_path, gate["src"]):
            os.remove(main_path)
            removed += 1
            for alias_name in _aliases(gate):
                alias = os.path.join(OVERRIDE, f"{alias_name}.ncs")
                if os.path.isfile(alias):
                    os.remove(alias)
                    removed += 1
    return removed


# Dialog edits: (module, function) pairs, each returning {"<name>.dlg": bytes} built from the game's own module copy of the
# dialog (never from Override). They are written to Override next to the scripts and removed with them.
DIALOG_BUILDERS = [
    ("story_gate_dialogs_unknown", "build"),      # Unknown World U1 to U3 and Dantooine D2 starter inserts
    ("story_gate_dialogs_korriban", "build"),     # Ko1: Yuthura's acceptance
    ("story_gate_dialogs_korriban", "build_uthar_intro"),  # Uthar's welcome scene tolerates an absent student
]


def _build_dialogs():
    import importlib
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    built = {}
    for module_name, func in DIALOG_BUILDERS:
        built.update(getattr(importlib.import_module(module_name), func)(GAME_DIR))
    return built


def apply_dialogs():
    built = _build_dialogs()
    for fname, data in built.items():
        with open(os.path.join(OVERRIDE, fname), "wb") as f:
            f.write(data)
    print(f"  {len(built)} dialog edit(s) deployed")
    return len(built)


def remove_dialogs():
    """Removes only dialogs that are byte-identical to what this patcher builds."""
    try:
        built = _build_dialogs()
    except Exception as e:
        print(f"  (could not rebuild the dialog edits to compare, leaving them: {e})")
        return 0
    removed = 0
    for fname, data in built.items():
        path = os.path.join(OVERRIDE, fname)
        if os.path.isfile(path):
            with open(path, "rb") as f:
                same = f.read() == data
            if same:
                os.remove(path)
                removed += 1
    return removed


def _connected_progression_system():
    if not os.path.isfile(SLOT_DATA_PATH):
        return False
    try:
        with open(SLOT_DATA_PATH, encoding="utf-8") as f:
            return bool(json.load(f).get("progression_system", False))
    except Exception:
        return False


def main():
    if "--restore" in sys.argv:
        # A full restore (uninstall) also takes out the progression item templates; switching the system off for one seed keeps them.
        tokens = 0
        for key in TOKEN_FAMILIES:
            for step in (1, 2, 3):
                path = os.path.join(OVERRIDE, f"ap_tk_{key}{step}.uti")
                if os.path.isfile(path):
                    os.remove(path)
                    tokens += 1
        print(f"Removed {remove_gates() + remove_dialogs() + tokens} story gate file(s).")
        return
    on = "--force" in sys.argv or _connected_progression_system()
    if not on:
        n = remove_gates() + remove_dialogs()
        print(f"Progression System is off -- story gates not applied. Removed {n} stale gate file(s).")
        return
    slot = _slot_data()
    if "--force" in sys.argv and "--area-randomizer" in sys.argv:
        slot["area_randomizer"] = 1
    # A gate this seed does not need may be left over from a previous seed.
    for gate in GATES:
        if not _gate_wanted(gate, slot) and _ours(os.path.join(OVERRIDE, f"{gate['name']}.ncs"), gate["src"]):
            os.remove(os.path.join(OVERRIDE, f"{gate['name']}.ncs"))
            for alias_name in _aliases(gate):
                alias = os.path.join(OVERRIDE, f"{alias_name}.ncs")
                if os.path.isfile(alias):
                    os.remove(alias)
    tokens = write_token_templates(Installation(GAME_DIR))
    deployed, wanted = apply_gates(slot)
    dialogs = apply_dialogs()
    print(f"Story gates: {deployed}/{wanted} deployed, {dialogs} dialog edits, {tokens} item templates written.")
    if deployed != wanted:
        sys.exit(1)


if __name__ == "__main__":
    main()
