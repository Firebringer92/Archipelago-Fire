"""Shared read-only access to the Steam/Aspyr TSL install's game data, for the
KOTOR 2 research scripts. Never writes to the game folder.

    import sys; sys.path.insert(0, r"C:\\Users\\User\\KOTOR2 AP\\tools")
    import tsl_data as T

Facts this module bakes in (all verified against the real install):
- 82 modules, each stored as THREE files in modules\\: <BASE>.rim (ARE/GIT/IFO/
  layout), <BASE>_s.rim (scripts, UTC/UTI/UTP/UTD/UTT/UTW/UTM/UTE templates) and
  <BASE>_dlg.erf (dialogues). Use module_resources(base) to get all three merged.
- Resource precedence at runtime is Override > module > chitin. Override holds
  Aspyr/Steam assets, including a replacement handmaiden.DLG, so for dialogue
  lookups use find(), which applies that precedence.
- Routine ids for compiled scripts come from the PROTOTYPE ORDER of the real TSL
  nwscript.nss (877 routines). nwnnsscomp's own labels use K1's table and are
  wrong for TSL; use routine_name()/ncs_actions() instead.
- Dialogue (DLG) condition scripts and their Param1..5 live on the LINK structs
  (StartingList / EntriesList / RepliesList items), not on the nodes.
"""
import logging
import os
import re
import sys
from functools import lru_cache

GAME = os.environ.get("K2_GAME_DIR") or r"C:\Program Files (x86)\Steam\steamapps\common\Knights of the Old Republic II"
# development copy of the game's nwscript.nss (routine names only; the class tables and the wrapper builders do not need it)
NSS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "nss", "nwscript_k2_vanilla.nss")

logging.disable(logging.CRITICAL)  # pykotor is very chatty at DEBUG

from pykotor.extract.installation import Installation, SearchLocation  # noqa: E402
from pykotor.resource.formats.gff import read_gff  # noqa: E402
from pykotor.resource.formats.ncs import read_ncs  # noqa: E402
from pykotor.resource.formats.twoda import read_2da  # noqa: E402
from pykotor.resource.type import ResourceType  # noqa: E402

RT = ResourceType


@lru_cache(maxsize=1)
def inst():
    return Installation(GAME)


# ---------------------------------------------------------------- modules
@lru_cache(maxsize=1)
def module_bases():
    """Sorted list of the 82 module bases, e.g. ['001EBO', ..., '950COR']."""
    d = os.path.join(GAME, "modules")
    out = set()
    for f in os.listdir(d):
        m = re.match(r"(.+?)(_s\.rim|_dlg\.erf|\.rim)$", f, re.I)
        if m:
            out.add(m.group(1))
    return sorted(out)


def module_resources(base):
    """All resources of one module: <base>.rim + <base>_s.rim + <base>_dlg.erf."""
    out = []
    for fn in (f"{base}.rim", f"{base}_s.rim", f"{base}_dlg.erf"):
        try:
            out.extend(inst().module_resources(fn))
        except Exception:
            pass
    return out


def module_gff(base, restype, name=None):
    """First resource of this type in the module (or the one named `name`), as a GFF root."""
    for r in module_resources(base):
        if r.restype() == restype and (name is None or r.resname().lower() == name.lower()):
            return read_gff(r.data()).root
    return None


def module_area_info(base):
    """(area_resref, ARE root, GIT root, IFO root) for a module; any may be None."""
    ifo = module_gff(base, RT.IFO)
    are = module_gff(base, RT.ARE)
    git = module_gff(base, RT.GIT)
    return ifo, are, git


# ---------------------------------------------------------------- lookups
def find(name, restype, module=None):
    """Resolve a resource with game precedence: Override, then (optionally) the
    given module's three files, then chitin. Returns bytes or None."""
    r = inst().resource(name, restype, [SearchLocation.OVERRIDE])
    if r is not None:
        return r.data
    if module:
        for x in module_resources(module):
            if x.restype() == restype and x.resname().lower() == name.lower():
                return x.data()
    r = inst().resource(name, restype, [SearchLocation.CHITIN])
    return r.data if r is not None else None


def twoda(name):
    data = find(name, RT.TwoDA)
    return read_2da(data) if data else None


def gff(name, restype, module=None):
    data = find(name, restype, module)
    return read_gff(data).root if data else None


# ---------------------------------------------------------------- text
def tlk_text(strref):
    try:
        return inst().talktable().string(int(strref))
    except Exception:
        return ""


def loc_text(locstring):
    """Text of a GFF LocalizedString: talk-table lookup if it has a strref, else inline."""
    try:
        if locstring.stringref >= 0:
            return tlk_text(locstring.stringref)
        for _, _, text in locstring:
            return text
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------- scripts
@lru_cache(maxsize=1)
def routine_names():
    """List of the 877 vanilla routine names, indexed by routine id."""
    proto = re.compile(r"^\s*(?:int|void|object|string|float|effect|talent|location|action|vector|event|itemproperty|struct\s+\w+)\s+(\w+)\s*\(")
    names = []
    for line in open(NSS, encoding="latin-1"):
        s = line.split("//")[0]
        m = proto.match(s)
        if m and s.rstrip().endswith(";"):
            names.append(m.group(1))
    assert len(names) == 877, len(names)
    return names


def routine_name(rid):
    n = routine_names()
    return n[rid] if 0 <= rid < len(n) else f"routine_{rid}"


def routine_id(name):
    return routine_names().index(name)


def ncs_pattern(name):
    """Raw byte pattern of an ACTION instruction for a routine (cheap prefilter)."""
    return bytes([0x05, 0x00]) + routine_id(name).to_bytes(2, "big")


def ncs_actions(data):
    """Parse a compiled script. Returns a list of (routine_name, [recent_int_consts], last_string)
    for every ACTION, where the consts are the up-to-4 most recent CONSTI values and the string is
    the most recent CONSTS before the call. Enough to read calls like
    AddAvailableNPCByTemplate(NPC_ATTON, "p_atton") or GetGlobalNumber("K_STAR_MAP")."""
    ncs = read_ncs(data)
    ints, last_s, out = [], None, []
    for ins in ncs.instructions:
        t = ins.ins_type.name
        if t == "CONSTS":
            last_s = ins.args[0]
        elif t == "CONSTI":
            ints = (ints + [ins.args[0]])[-4:]
        elif t == "ACTION":
            out.append((routine_name(ins.args[0]), list(ints), last_s))
    return out


def ncs_strings(data):
    """All string constants in a compiled script, in order."""
    return [i.args[0] for i in read_ncs(data).instructions if i.ins_type.name == "CONSTS"]


# ---------------------------------------------------------------- scanning
def iter_all_resources():
    """Yield (where, FileResource) for chitin, Override, and every module file.
    where is 'chitin', 'override' or the module base name."""
    for r in inst().chitin_resources():
        yield "chitin", r
    for r in inst().override_resources():
        yield "override", r
    for b in module_bases():
        for r in module_resources(b):
            yield b, r


# ---------------------------------------------------------------- reference data
CLASS_NAMES = {0: "Soldier", 1: "Scout", 2: "Scoundrel", 3: "JediGuardian", 4: "JediConsular", 5: "JediSentinel",
               6: "CombatDroid", 7: "ExpertDroid", 8: "Minion", 9: "TechSpecialist", 10: "BountyHunter(cut)",
               11: "JediWeaponmaster", 12: "JediMaster", 13: "JediWatchman", 14: "SithMarauder", 15: "SithLord",
               16: "SithAssassin"}
NPC_SLOTS = {0: "Atton", 1: "Bao-Dur", 2: "Mandalore", 3: "G0-T0", 4: "Handmaiden", 5: "HK-47", 6: "Kreia",
             7: "Mira", 8: "T3-M4", 9: "Visas", 10: "Hanharr", 11: "Disciple"}
PLANETS = {"EBO": "Ebon Hawk", "PER": "Peragus", "HAR": "Harbinger", "TEL": "Telos", "NAR": "Nar Shaddaa",
           "DXN": "Dxun", "OND": "Onderon", "DAN": "Dantooine", "KOR": "Korriban", "NIH": "Nihilus ship (Ravager)",
           "MAL": "Malachor V", "COR": "Coruscant/holorecord"}


def planet_of(base):
    return PLANETS.get(base[-3:].upper(), base[-3:])


if __name__ == "__main__":
    print(len(module_bases()), "modules;", len(routine_names()), "routines")
    print("sample:", module_bases()[:6])
