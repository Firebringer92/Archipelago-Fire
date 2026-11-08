"""The seed's data for the game: what the client turns slot_data into before the game starts.

How a script can read the seed, and what it cannot (checked against the game's script API): there is no Get2DAString in KOTOR 2 scripts, so a 2DA is
only read by the engine itself. The extender routine K2SE_ConfigInt reads integers from the K2SE folder in %LOCALAPPDATA% (config.txt), so:
  * switches and small numbers (this module's ROWS) go into a managed block of config.txt as ap_<name>=<int> (client/k2_patch.py writes it);
    nss/k2ap_seed.nss, generated from ROWS by tools/build_seed_include.py, gives each one a function: K2AP_Goal(), K2AP_StoryGates(), ...
  * big tables the ENGINE reads natively (recipe 2DAs, store templates, item and creature templates) are written as files into Override by the
    feature that needs them, registered in FILE_BUILDERS;
  * the 8,191-byte limit of config.txt (the extender reads only that much) leaves room for about 250 more numbers after the ROWS below.
Add rows at the END only: a row's key is what the compiled scripts ask for.
"""
import typing

SEED_FORMAT = 1

# Gate order = bit number in the disabled-gates mask. Same ids as worlds/kotor2/Options.py DisabledGates.valid_keys.
GATE_ORDER = ("TEL1", "TEL2", "TEL3", "NAR1", "NAR2", "NAR3", "DXN1", "DXN2", "DXN3", "DAN1", "DAN2", "DAN3",
              "KOR1", "KOR2", "KOR3", "FIN1", "FIN2", "FIN3", "FIN4")

EXPERIENCE_OFF = 0


def _opt(name: str, default: int = 0) -> typing.Callable[[dict], int]:
    def get(slot: dict) -> int:
        return int(slot.get("options", {}).get(name, default))
    get.__name__ = "opt_" + name
    return get


def _goal_type(slot: dict) -> int:
    return int(slot.get("options", {}).get("goal", 0))


def _gate_mask(slot: dict) -> int:
    mask = 0
    for gate in slot.get("disabled_gates", []):
        if gate in GATE_ORDER:
            mask |= 1 << GATE_ORDER.index(gate)
    return mask


def _xp_clamp(slot: dict) -> int:
    """1 when the game holds vanilla XP to the amount the seed expects (the ap experience modes)."""
    return 1 if int(slot.get("options", {}).get("experience_mode", EXPERIENCE_OFF)) != EXPERIENCE_OFF else 0


# (key, value from slot_data). The key is the constant's name in k2ap_seed.nss (K2AP_ROW_<KEY>).
ROWS: typing.Tuple[typing.Tuple[str, typing.Callable[[dict], int]], ...] = (
    ("FORMAT", lambda s: SEED_FORMAT),
    ("SEED_GUARD", lambda s: int(s.get("seed_guard", 0))),
    ("GOAL", _goal_type),
    ("LEVEL_CAP", lambda s: int(s.get("level_cap", 0))),
    ("DISABLED_GATES", _gate_mask),
    ("STORY_GATES", _opt("story_gates", 1)),
    ("SHORTENED_PERAGUS", _opt("shortened_peragus")),
    ("COMPANIONS", _opt("companions", 1)),
    ("COMPANION_CLASS", _opt("companion_class")),
    ("MULTICLASS_COMPANION", _opt("multiclass_companion")),
    ("STARTING_CLASS", _opt("starting_class")),
    ("EXPERIENCE_MODE", _opt("experience_mode")),
    ("CREDIT_MODE", _opt("credit_mode")),
    ("BAZAAR", _opt("bazaar", 1)),
    ("QUEST_ITEM_CHECKS", _opt("quest_item_checks", 1)),
    ("AREA_VISIT_CHECKS", _opt("area_visit_checks", 1)),
    ("ALIGNMENT_CHECKS", _opt("alignment_checks", 1)),
    ("CRAFTING_MODE", _opt("crafting_mode")),
    ("LOOT_MODE", _opt("loot_mode")),
    ("CRAFTING_GATED", _opt("crafting_gated")),
    ("AREA_RANDOMIZER", _opt("area_randomizer")),
    ("ENEMY_RANDOMIZER", _opt("enemy_randomizer")),
    ("SHOP_RANDOMIZER", _opt("shop_randomizer")),
    ("SHOP_COUNT", _opt("shop_count", 30)),
    ("LOOT_RANDOMIZER", _opt("loot_randomizer")),
    ("ARCHIPELAGO_VENDOR", _opt("archipelago_vendor")),
    ("DEATH_LINK", _opt("death_link")),
    ("TRAP_LINK", _opt("trap_link")),
    ("LEVEL_TARGET", _opt("level_target", 20)),
    ("GOAL_LEVEL", _opt("goal_level", 25)),
    ("SKIP_TURRETS", lambda s: 1),
    ("XP_CLAMP", _xp_clamp),
    ("PATCHED", lambda s: 1),            # the client's patch is applied: scripts that change the game's behaviour act only when this is 1
)


def row_index(key: str) -> int:
    for i, (k, _) in enumerate(ROWS):
        if k == key:
            return i
    raise KeyError(key)


def seed_values(slot: dict) -> typing.List[typing.Tuple[str, int]]:
    return [(key, int(get(slot))) for key, get in ROWS]


def render_2da(columns: typing.Sequence[str], rows: typing.Sequence[typing.Sequence[typing.Any]]) -> str:
    """A text 2DA (V2.0). Cells are written as given; an empty cell becomes ****."""
    out = ["2DA V2.0", "", "    " + " ".join(columns)]
    for i, row in enumerate(rows):
        cells = [("****" if str(c) == "" else str(c)) for c in row]
        out.append("%d    %s" % (i, " ".join(cells)))
    return "\r\n".join(out) + "\r\n"


def config_lines(slot: dict) -> typing.List[str]:
    """The seed's lines for config.txt: ap_<key lower case>=<int>."""
    return ["ap_%s=%d" % (key.lower(), value) for key, value in seed_values(slot)]


# Name of the file in Override -> builder(slot_data) -> text, or None when the feature is off. Feature packages register here.
FILE_BUILDERS: typing.Dict[str, typing.Callable[[dict], typing.Optional[str]]] = {}


def seed_files(slot: dict) -> typing.Dict[str, bytes]:
    """{file name: bytes} for every data file this seed needs in Override (the switches are not files: see config_lines)."""
    files = {}
    for name, builder in FILE_BUILDERS.items():
        text = builder(slot)
        if text is not None:
            files[name] = text.encode("ascii")
    return files


def nss_include() -> str:
    """Source of nss/k2ap_seed.nss (kept in step by tools/build_seed_include.py and a test). The game's script compiler has no const or #define,
    so every setting is read by its own small function: K2AP_Goal(), K2AP_StoryGates(), ..."""
    lines = ["// k2ap_seed.nss -- the seed's settings, read from the extender's config.txt (include file; needs the extended routines).",
             "// GENERATED by tools/build_seed_include.py from client/k2_seed.py. Do not edit.",
             "// The client writes the ap_* lines when it connects. A game started without the client's patch finds none and reads 0 everywhere,",
             "// which means: no gates, no randomisers, no skips, a vanilla-leaning run.",
             ""]
    for key, _ in ROWS:
        lines += ["int %s()" % func_name(key), "{", '    return K2SE_ConfigInt("ap_%s", 0);' % key.lower(), "}", ""]
    lines += ["// Bit number of a story gate in the disabled-gates mask, -1 for an unknown id.",
              "int K2AP_GateBit(string sGate)",
              "{"]
    for i, gate in enumerate(GATE_ORDER):
        lines.append('    if (sGate == "%s") return %d;' % (gate, i))
    lines += ["    return -1;", "}", "",
              '// TRUE when the seed switched the story gate off (sGate like "NAR1").',
              "int K2AP_GateOff(string sGate)",
              "{",
              "    int nBit = K2AP_GateBit(sGate);",
              "    if (nBit < 0) return FALSE;",
              "    return (K2AP_DisabledGates() >> nBit) & 1;",
              "}", ""]
    return "\n".join(lines)


def func_name(key: str) -> str:
    """'SEED_GUARD' -> 'K2AP_SeedGuard'."""
    return "K2AP_" + "".join(part.capitalize() for part in key.split("_"))
