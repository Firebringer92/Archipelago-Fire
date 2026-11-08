"""Items of the KOTOR 2 world (first draft).

Classification follows the K1 world: skills, abilities, experience and credits are filler; class and training items are useful; the story tokens
(one family per gate family) and, later, anything the logic needs are progression. The item pool never changes with crafting mode: crafting mode only
changes what the delivery does with a gear item.
"""
import json
import pkgutil
import typing

from BaseClasses import ItemClassification

BASE_ID = 2_600_000


class ItemData(typing.NamedTuple):
    id: int
    classification: ItemClassification
    arm: str              # what the client sends to the game (dispatcher action and argument)
    weight: int = 0       # filler selection weight (0 = never chosen as filler)


def extra_companion_data() -> dict:
    """data/extra_companions.json: the extra companions' templates, looks and classes (ids only), and the safe looks of the generated ones."""
    return json.loads(pkgutil.get_data(__name__, "data/extra_companions.json").decode("utf-8"))


def crafting_data() -> dict:
    """data/crafting.json: the gear the crafting mode adds to the workbench, [[resref, type], ...]."""
    return json.loads(pkgutil.get_data(__name__, "data/crafting.json").decode("utf-8"))


def door_data() -> dict:
    """data/doors.json: the doors that may be re-linked (in coupled pairs), the modules, the roots and each module's own story requirement."""
    return json.loads(pkgutil.get_data(__name__, "data/doors.json").decode("utf-8"))


def enemy_data() -> dict:
    """data/enemies.json: per module the safe spawn points and the challenge-rating band, and the pool of creature templates (rating, category, source)."""
    return json.loads(pkgutil.get_data(__name__, "data/enemies.json").decode("utf-8"))


def shop_data() -> dict:
    """data/shops.json (the planets and their placed stores) and data/shop_pool.json (the resrefs a randomized shop may stock, and the staples every one carries)."""
    shops = json.loads(pkgutil.get_data(__name__, "data/shops.json").decode("utf-8"))
    pool = json.loads(pkgutil.get_data(__name__, "data/shop_pool.json").decode("utf-8"))
    return {"planets": shops["planets"], "stores": shops["stores"], "stock_scripts": shops["stock_scripts"], "pool": pool["pool"], "staples": pool["staples"]}


def peragus_data() -> dict:
    """data/peragus.json: the condensed Peragus (variant A of docs/PERAGUS_CONDENSED.md): the decisions, the skipped modules, the checks that cannot happen and the
    script hooks with their operations."""
    return json.loads(pkgutil.get_data(__name__, "data/peragus.json").decode("utf-8"))


def _gates() -> typing.List[dict]:
    return json.loads(pkgutil.get_data(__name__, "data/gates.json").decode("utf-8"))["gates"]


# Gate token families. One item name per family, many copies. tokens_needed of the family's last enabled gate = copies in the pool.
TOKEN_FAMILIES: typing.Dict[str, str] = {
    "Telos": "Telos Progression",
    "Nar Shaddaa": "Nar Shaddaa Progression",
    "Dxun/Onderon": "Dxun/Onderon Progression",
    "Dantooine": "Dantooine Progression",
    "Korriban": "Korriban Progression",
    "Endgame": "Endgame Progression",
}
TOKEN_ITEM_NAMES = tuple(TOKEN_FAMILIES.values())


def token_counts(disabled: typing.Container[str]) -> typing.Dict[str, int]:
    """Copies of each family token in the pool: the highest tokens_needed among the family's enabled gates."""
    out: typing.Dict[str, int] = {}
    for g in _gates():
        if not g["enabled"] or g["id"] in disabled:
            continue
        name = TOKEN_FAMILIES[g["family"]]
        out[name] = max(out.get(name, 0), g["tokens_needed"])
    return out


def goal_token_counts(disabled: typing.Container[str], skip_gates: typing.Container[str] = ()) -> typing.Dict[str, int]:
    """Tokens a goal needs: like token_counts, ignoring the listed gates (for example FIN4 when the goal is reached before the Kreia fight)."""
    out: typing.Dict[str, int] = {}
    for g in _gates():
        if not g["enabled"] or g["id"] in disabled or g["id"] in skip_gates:
            continue
        name = TOKEN_FAMILIES[g["family"]]
        out[name] = max(out.get(name, 0), g["tokens_needed"])
    return out


# Characters that can be offered as extra companions on the new party slots (12-31). Each must pass a vetting test in the game before it is delivered.
EXTRA_COMPANION_NAMES = ["Bastila Shan", "Carth Onasi", "Jolee Bindo", "Juhani", "Mission Vao", "Zaalbar", "Canderous Ordo",
                         "Darth Sion", "Darth Nihilus", "Kavar", "Vrook Lamar", "Zez-Kai Ell"]
TRAP_TYPE_KEYS = ["lose_credits", "dark_side_push", "light_side_push", "lose_influence", "reduce_skill", "cut_max_health", "remove_companion",
                  "remove_half_inventory", "halve_strength", "halve_dexterity", "halve_intelligence", "halve_wisdom", "halve_charisma"]

F, U, P, T = ItemClassification.filler, ItemClassification.useful, ItemClassification.progression, ItemClassification.trap

_SKILLS = ["Computer Use", "Demolitions", "Stealth", "Awareness", "Persuade", "Repair", "Security", "Treat Injury"]
_ABILITIES = ["Strength", "Dexterity", "Constitution", "Intelligence", "Wisdom", "Charisma"]
_COMPANIONS = ["Atton Rand", "Bao-Dur", "Mandalore", "G0-T0", "Handmaiden", "HK-47", "Kreia", "Mira", "T3-M4", "Visas Marr", "Hanharr", "Disciple"]

COMPANION_NAMES = _COMPANIONS
ITEMS: typing.Dict[str, ItemData] = {}


def _add(name: str, cls: ItemClassification, arm: str, weight: int = 0) -> None:
    ITEMS[name] = ItemData(BASE_ID + len(ITEMS), cls, arm, weight)


for _s in _SKILLS:
    _add("Skill: " + _s, F, "skill:" + _s.lower().replace(" ", "_"), 3)
for _a in _ABILITIES:
    _add("Ability: %s Increase" % _a, F, "ability:" + _a.lower(), 2)
_add("Experience Points", F, "xp", 12)
_add("Republic Credits", F, "credits", 12)
for _c in _COMPANIONS:
    _add("Companion: " + _c, U, "companion:" + _c.lower().replace(" ", "_").replace("-", ""))
# Traps: delivery arms are the ones the research found feasible (docs/SYSTEMS.md); the list grows with the delivery work.
_add("Trap: Lose Credits", T, "trap:credits")
_add("Trap: Dark Side Push", T, "trap:dark")
_add("Trap: Light Side Push", T, "trap:light")
_add("Trap: Lose Influence", T, "trap:influence")
_TOKEN_KEYS = {"Telos": "telos", "Nar Shaddaa": "nar", "Dxun/Onderon": "dxn", "Dantooine": "dan", "Korriban": "kor", "Endgame": "endgame"}
for _family, _name in TOKEN_FAMILIES.items():
    _add(_name, P, "token:" + _TOKEN_KEYS[_family])   # delivered as a stage of the family journal quest ap_prog_<key> (client/k2_journal.py)
_add("Victory", P, "victory")
# Added after the first draft: appended so the ids above never move.
for _c in EXTRA_COMPANION_NAMES:
    _add("Companion: " + _c, U, "extracompanion:" + _c.lower().replace(" ", "_").replace("-", ""))
_add("AP Companion", U, "apcompanion")
# More traps (appended: ids above never move). Each is decided in the game at delivery from the character's live state and does nothing when there is
# nothing to take (see nss/k2se_disp.nss).
# multiclass_companion prestige: one item per companion who can be a Jedi (the five the story lets you train, Kreia and Visas); the companion is fixed by the item
JEDI_CAPABLE_SLOTS = (0, 1, 4, 6, 7, 9, 11)
for _slot in JEDI_CAPABLE_SLOTS:
    _add("Companion Prestige: " + _COMPANIONS[_slot], U, "companionprestige:%d" % _slot)
_add("Prestige Class", U, "prestige")      # starting_class prestige_gated: the player becomes a light or dark prestige class of the seed's pair when it arrives
_add("Trap: Reduce a Skill", T, "trap:skill")
_add("Trap: Cut Max Health in Half", T, "trap:max_health")
_add("Trap: Remove a Companion", T, "trap:companion")
_add("Trap: Remove Half Inventory", T, "trap:inventory")
for _ability in ("Strength", "Dexterity", "Intelligence", "Wisdom", "Charisma"):
    _add("Trap: Halve " + _ability, T, "trap:halve_" + _ability.lower())

# crafting_gated: one item per crafting type (appended: ids above never move). The first five are the workbench's gear tabs, "parts" is the vanilla item-creation
# rows (upgrade parts, spikes, kits) together with the upgrade screen, "lab" is the chemical lab (medpacs, stims, grenades, mines, implants).
CRAFT_TYPES = {"armor": "Armor and Robes", "ranged": "Ranged Weapons", "melee": "Melee Weapons", "lightsaber": "Lightsabers", "other": "Belts, Gloves and Other Gear",
               "parts": "Upgrade Parts", "lab": "Chemical Lab"}
GEAR_CRAFT_TYPES = ("armor", "ranged", "melee", "lightsaber", "other")
for _key, _title in CRAFT_TYPES.items():
    _add("Crafting: " + _title, U, "craft:" + _key)
CRAFT_ITEM_BY_TYPE = {k: "Crafting: " + t for k, t in CRAFT_TYPES.items()}
# Gear in the pool (filler): one item per gear recipe of crafting.json, named by its template name (the game's item names are the game's text and are not published).
# Crafting mode off: the item is given. Crafting mode on: it unlocks that recipe and gives Components.
GEAR_ITEMS = [(r, k) for r, k in crafting_data()["gear"]]
for _resref, _kind in GEAR_ITEMS:
    _add("Gear: " + _resref, F, "gear:" + _resref)
GEAR_ITEM_NAMES = ["Gear: " + r for r, _ in GEAR_ITEMS]

# archipelago_vendor: one pass per menu of the Vendor on the Hawk (appended: ids above never move). "supply" is only in the pool when the seed has a crafting mode.
VENDOR_PASSES = {"skill": "Skill Training", "abil": "Ability Training", "align": "Alignment Change", "supply": "Crafting Supplies"}
for _key, _title in VENDOR_PASSES.items():
    _add("Vendor Pass: " + _title, U, "vendorpass:" + _key)
VENDOR_PASS_ITEM_BY_KEY = {k: "Vendor Pass: " + t for k, t in VENDOR_PASSES.items()}

BASE_COMPANION_ITEMS = ["Companion: " + c for c in _COMPANIONS]
EXTRA_COMPANION_ITEMS = {c: "Companion: " + c for c in EXTRA_COMPANION_NAMES}
TRAP_BY_KEY = {"lose_credits": "Trap: Lose Credits", "dark_side_push": "Trap: Dark Side Push", "light_side_push": "Trap: Light Side Push",
               "lose_influence": "Trap: Lose Influence", "reduce_skill": "Trap: Reduce a Skill", "cut_max_health": "Trap: Cut Max Health in Half",
               "remove_companion": "Trap: Remove a Companion", "remove_half_inventory": "Trap: Remove Half Inventory",
               "halve_strength": "Trap: Halve Strength", "halve_dexterity": "Trap: Halve Dexterity", "halve_intelligence": "Trap: Halve Intelligence",
               "halve_wisdom": "Trap: Halve Wisdom", "halve_charisma": "Trap: Halve Charisma"}
TRAP_NAMES = [n for n, d in ITEMS.items() if d.classification == T]
FILLER_WEIGHTS = {n: d.weight for n, d in ITEMS.items() if d.weight}
ITEM_NAME_TO_ID = {n: d.id for n, d in ITEMS.items()}
