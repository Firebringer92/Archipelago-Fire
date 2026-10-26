"""
Installs (or takes back out) everything the droid options need, in the game's Override folder:

  * Battle Droid, a tenth classes.2da row (class 9) with its own DRB columns in feat/skills/featgain. Its name is the game's
    own "Battle Droid" string (dialog.tlk entry 15680); its description is still the Combat Droid one. dialog.tlk is
    deliberately left alone (build_ap_tracker_quest.py expects its own strings at the very end of that file).
  * The melee weapons opened to droids: baseitems.2da `droidorhuman` set to 0 on the 14 melee/lightsaber rows. Lightsabers
    still need their proficiency feat, which only the Battle Droid class grants.
  * Human-rig droid models (built by build_hk47_human_rig.py / build_droid_human_rig.py, checked in under
    extender/raw_override_files): the HK-47 variant (appearance row 1, PC only), the war droid (row 58) and the assassin
    droid (row 82). Their animations come from a human supermodel, so melee weapons swing natively.
  * starting_class=droid only: the Taris Upper City elevator door script (k_ptar_alertsith) is wrapped so a droid PC that merely
    carries the Sith armor is let through (a droid cannot wear it); the wrapper sets the papers flag and unlocks the door. The vanilla script is preserved from its module archive as
    apo_k_ptar_alertsith_orig; see extender/scripts_src/k_ptar_alertsith_droid.nss.
  * starting_class=droid only: the vanilla Persuade checks (k_con_perseasy / persmed / pershigh and the three Manaan planet-vote steps)
    are replaced by copies that roll a droid PC on its Charisma modifier (extender/scripts_src/k_inc_droidpers.nss: the game's AutoDC
    bracket table with the Charisma modifier as the rank), because a droid cannot train Persuade and the vanilla roll reads no
    usable rank. A failed roll can close a story outcome that needs a success (redeeming Bastila on the Star Forge). Everyone else
    keeps the vanilla roll.
  * companion_class=droid only: p_<companion>.utc templates for the seven non-droid companions (droid race, subrace 0, the
    seed's droid look and droid class at class level 1 with that class's level-1 feat kit, the droid hide), Canderous's
    combined droid + Regeneration hide, and the Mark Two ranged-animation fix.
  * Droid gear (either option): better stats on the existing droid plating, shields, targeting computers and sensors (DROID_GEAR
    below). Copies of the item templates in Override; the spike mounts, utility devices and repair kits are left alone.

Needed when starting_class is droid (4) and/or companion_class is droid (4). With neither, everything this script ever wrote
is removed again, so it runs on every Connect.

  python generate_droid_assets.py [--game-dir=PATH]            read the options from _slot_data.json, install or remove
  python generate_droid_assets.py --restore [--game-dir=PATH]  remove everything
  python generate_droid_assets.py --status [--game-dir=PATH]
  testing overrides: --starting-class=N  --companion-mode=N  --plan-json='{"mission":[58,9],...}'

What was written is recorded in <game>/Override/ap_droid_manifest.json: files written (plus any same-named file that was
there before, moved aside), and the original cells of every appearance.2da / baseitems.2da cell that was changed.
"""
import json
import os
import shutil
import sys

from pykotor.common.misc import EquipmentSlot, InventoryItem, ResRef
from pykotor.extract.installation import Installation, SearchLocation
from pykotor.resource.formats.gff import write_gff
from pykotor.resource.formats.twoda import read_2da, write_2da
from pykotor.resource.generics.utc import UTCClass, dismantle_utc, read_utc
from pykotor.resource.generics.uti import UTIProperty, dismantle_uti, read_uti
from pykotor.resource.type import ResourceType

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
RAW_OVERRIDE_DIR = os.path.join(REPO_ROOT, "extender", "raw_override_files")
SLOT_DATA_PATH = os.path.join(REPO_ROOT, "extender", "area_trampolines", "_slot_data.json")
MANIFEST = "ap_droid_manifest.json"
BACKUP_SUFFIX = ".ap_droid_backup"
# Bump when any asset or rule below changes, so an unchanged-looking Connect still reinstalls.
VERSION = 6

# Files left behind by the developer-only build/test scripts: they own their own backups, so refuse to stack on top of them.
LEGACY_MARKERS = ("droid_test_manifest.json", "hk47_variant_appearance_backup.json", "ap_drdwar_appearance_backup.json",
                  "ap_drdassn_appearance_backup.json")

COMPANION_TEMPLATES = {"bastila": "p_bastilla", "canderous": "p_cand", "carth": "p_carth", "jolee": "p_jolee",
                       "juhani": "p_juhani", "mission": "p_mission", "zaalbar": "p_zaalbar"}
COMBAT, EXPERT, BATTLE = 6, 7, 9
DROID_RACE = 5

# appearance.2da rows hosting the human-rig models: (row, row whose cells are copied, model resref, label)
HK_VARIANT_ROW, HK47_ROW, HK_VARIANT_MODEL = 1, 3, "ap_hk47v"
WAR_ROW, WAR_SOURCE_ROW, WAR_MODEL = 58, 66, "ap_drdwar"
ASSASSIN_ROW, ASSASSIN_SOURCE_ROW, ASSASSIN_MODEL = 82, 56, "ap_drdassn"

# baseitems.2da rows whose droidorhuman is 1 (human only) and must become 0: quarterstaff .. short lightsaber (0-10) and the
# three wookiee/gamorrean/ghaffi melee weapons (78-80). Melee is then gated only by the proficiency feats.
MELEE_BASEITEM_ROWS = list(range(0, 11)) + [78, 79, 80]

# Taris elevator door: wrapper (precompiled, checked in) + the vanilla original it hands off to
ALERTSITH = "k_ptar_alertsith"
ALERTSITH_MODULE = "tar_m02ab"
ALERTSITH_WRAPPER_NCS = os.path.join(REPO_ROOT, "extender", "scripts_src", "k_ptar_alertsith_droid.ncs")
# vanilla script name -> precompiled replacement in extender/scripts_src (<name>_droid.ncs); full reimplementations, no original kept
PERSUADE_OVERRIDES = ("k_con_perseasy", "k_con_persmed", "k_con_pershigh", "k_pman_planet57", "k_pman_planet58", "k_pman_planet59")

# ---- Battle Droid (classes.2da row 9) ---------------------------------------------------------------------------------
BATTLE_PREFIX = "drb"
BATTLE_NAME_STRREF = 15680  # "Battle Droid", already in the stock dialog.tlk
SKILL_DEMOLITIONS, SKILL_AWARENESS, SKILL_REPAIR, SKILL_SECURITY = 1, 3, 5, 6
BATTLE_CLASS_SKILLS = {SKILL_AWARENESS, SKILL_SECURITY, SKILL_DEMOLITIONS, SKILL_REPAIR}
FEAT_LIGHTSABER_PROF, FEAT_MELEE_PROF = 43, 44
# Feats a Battle Droid may pick on level-up (feat.2da drb_list = 1) in auto-level preference order (drb_recom): the melee and
# the blaster lines interleaved. Prerequisites are enforced by the game itself.
BATTLE_FEAT_ORDER = [
    28, 30, 11, 31, 8, 84, 29, 17, 92, 91, 20, 19, 37, 32, 18, 83, 77, 53, 81, 82, 26, 51, 46, 33, 35, 47, 49, 36, 50, 113,
]
# Level-1 feat kit per droid class: the class-table feats a template-spawned companion never receives by itself.
FEAT_KIT = {
    COMBAT: [39, 40, 42, 78, 110],
    EXPERT: [39, 96, 78, 110],
    BATTLE: [39, 40, 42, 43, 44, 78, 110],
}
HIT_DIE = {COMBAT: 12, EXPERT: 8, BATTLE: 10}
# Vanilla droid creature hide (immunity to mind spells, paralysis and poison): HK-47 wears this one. Canderous keeps his
# Regeneration +4 (it lived on his own hide, g_i_crhide007) through a custom hide that is the droid hide plus that property.
DROID_HIDE = "g_i_crhide013"
CAND_HIDE = "ap_drdhide_cand"
CAND_ORIGINAL_HIDE = "g_i_crhide007"
REGENERATION_PROPERTY = 35


def _arg(flag, default=None):
    for a in sys.argv[1:]:
        if a.startswith(flag + "="):
            return a.split("=", 1)[1]
    return default


# ---- helpers ----------------------------------------------------------------------------------------------------------
def _read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _load_table(inst, override, name):
    """The Override copy of a 2DA if there is one (another patcher may have edited it), else the game's own."""
    path = os.path.join(override, name + ".2da")
    if os.path.isfile(path):
        return read_2da(open(path, "rb").read())
    res = inst.resource(name, ResourceType.TwoDA, [SearchLocation.CHITIN])
    if res is None:
        raise RuntimeError(f"{name}.2da not found")
    return read_2da(res.data)


def _write_table(table, override, name):
    write_2da(table, os.path.join(override, name + ".2da"), ResourceType.TwoDA)


class Recorder:
    """Collects what an install writes so a later run can undo exactly that."""

    def __init__(self, override):
        self.override = override
        self.files = {}      # file name -> backup name or None
        self.cells = {}      # table name -> {row: {header: original value}}

    def put(self, name, writer):
        path = os.path.join(self.override, name)
        backup = None
        if os.path.exists(path):
            backup = name + BACKUP_SUFFIX
            shutil.copy2(path, os.path.join(self.override, backup))
        writer(path)
        self.files[name] = backup

    def copy(self, src, name):
        self.put(name, lambda p: shutil.copy2(src, p))

    def edit_cell(self, table, table_name, row, header, value):
        saved = self.cells.setdefault(table_name, {}).setdefault(str(row), {})
        if header not in saved:
            saved[header] = table.get_row(row).get_string(header)
        table.set_cell(row, header, value)


def _clone_row(rec, table, table_name, row, source_row, label, model, modeltype=None):
    """Points appearance row `row` at `model`: every cell of `source_row`, then the label, race (= model resref) and type."""
    source = {h: table.get_row(source_row).get_string(h) for h in table.get_headers()}
    for h, v in source.items():
        rec.edit_cell(table, table_name, row, h, v)
    rec.edit_cell(table, table_name, row, "label", label)
    rec.edit_cell(table, table_name, row, "race", model)
    if modeltype:
        rec.edit_cell(table, table_name, row, "modeltype", modeltype)


# ---- Battle Droid tables ----------------------------------------------------------------------------------------------
def build_battle_tables(inst, override):
    classes = _load_table(inst, override, "classes")
    assert classes.get_height() == 9, "classes.2da row count changed -- check the Battle Droid row index"
    src = classes.get_row(COMBAT)
    cells = {h: src.get_string(h) for h in classes.get_headers()}
    cells.update({"label": "BattleDroid", "name": str(BATTLE_NAME_STRREF), "hitdie": "10", "skillpointbase": "3", "attackbonustable": "CLS_ATK_1",
                  "featstable": BATTLE_PREFIX.upper(), "skillstable": BATTLE_PREFIX.upper(),
                  "featgain": BATTLE_PREFIX.upper()})
    new_index = classes.add_row(str(classes.get_height()), cells)
    assert new_index == BATTLE, f"Battle Droid landed on row {new_index}, expected {BATTLE}"

    feat = _load_table(inst, override, "feat")
    for suffix in ("list", "granted", "recom"):
        feat.add_column(f"{BATTLE_PREFIX}_{suffix}")
        for i in range(feat.get_height()):
            feat.set_cell(i, f"{BATTLE_PREFIX}_{suffix}", feat.get_row(i).get_string(f"drc_{suffix}"))
    for f in (FEAT_LIGHTSABER_PROF, FEAT_MELEE_PROF):
        feat.set_cell(f, f"{BATTLE_PREFIX}_granted", "1")
    for rank, f in enumerate(BATTLE_FEAT_ORDER, start=1):
        feat.set_cell(f, f"{BATTLE_PREFIX}_list", "1")
        feat.set_cell(f, f"{BATTLE_PREFIX}_recom", str(rank))

    skills = _load_table(inst, override, "skills")
    for suffix in ("class", "reco"):
        skills.add_column(f"{BATTLE_PREFIX}_{suffix}")
        for i in range(skills.get_height()):
            value = skills.get_row(i).get_string(f"drc_{suffix}")
            if suffix == "class":
                value = "1" if i in BATTLE_CLASS_SKILLS else "0"
            skills.set_cell(i, f"{BATTLE_PREFIX}_{suffix}", value)

    featgain = _load_table(inst, override, "featgain")
    for suffix in ("reg", "bon"):
        featgain.add_column(f"{BATTLE_PREFIX}_{suffix}")
        for i in range(featgain.get_height()):
            featgain.set_cell(i, f"{BATTLE_PREFIX}_{suffix}", featgain.get_row(i).get_string(f"drx_{suffix}"))

    return {"classes": classes, "feat": feat, "skills": skills, "featgain": featgain}


# ---- companions -------------------------------------------------------------------------------------------------------
def build_companion(inst, resref, appearance, droid_class):
    """Droid companion template: race 5, subrace 0, the droid look, class level 1 with that class's level-1 feat kit (replacing
    the old class's feats), level-1 hit points, no Force points and the droid hide."""
    res = inst.resource(resref, ResourceType.UTC, [SearchLocation.CHITIN])
    if res is None:
        raise RuntimeError(f"{resref}.utc not found in the game's chitin")
    utc = read_utc(res.data)
    utc.race_id = DROID_RACE
    utc.subrace_id = 0
    utc.appearance_id = appearance
    utc.classes = [UTCClass(droid_class, 1)]
    utc.feats = list(FEAT_KIT[droid_class])
    con_mod = (utc.constitution - 10) // 2
    hp = max(1, HIT_DIE[droid_class] + con_mod)
    utc.hp = hp
    utc.current_hp = hp
    utc.max_hp = hp
    utc.fp = 0
    utc.max_fp = 0
    hide = CAND_HIDE if resref == "p_cand" else DROID_HIDE
    utc.equipment[EquipmentSlot.HIDE] = InventoryItem(ResRef(hide), False)
    return utc


# ---- droid gear -------------------------------------------------------------------------------------------------------
# Item property encodings (property, subtype, cost table, cost value), taken from the game's own items.
PROP_ABILITY, PROP_ARMOR, PROP_DAMAGE, PROP_RESIST, PROP_ATTACK = 0, 1, 11, 17, 38
STR, DEX, CON, INT = 0, 1, 2, 3
BLUD, PIERCE, SLASH, ACID, COLD, ELEC, FIRE, SONIC, ION, ENERGY = 0, 1, 2, 4, 5, 7, 8, 10, 11, 12
ARMOR_MAX = 5  # iprp_meleecost, the armour bonus cost table, stops at +5
FLOOR_COST = 500
# resref -> stats. armor: the armour bonus on top of the plating's own base AC (light 3, medium 4, heavy 9, shields 0);
# abilities {ability: bonus}; attack / damage: flat bonuses; resist {damage type: level 1-6 = 5/-, 10/- ... 30/-}; cost: shop price.
DROID_GEAR = {
    # plating: final AC light 5/7/8, medium 6/8/9, heavy 10/12/13, Composite Heavy 14 (human armour runs about 4-14). Resistances:
    # blasters and lightsabers deal energy damage and melee weapons physical damage (baseitems damageflags), so energy comes first.
    "g_i_drdltplat001": {"armor": 2, "resist": {ENERGY: 1}, "cost": 300},
    "g_i_drdltplat002": {"armor": 4, "resist": {ENERGY: 1}, "cost": 600},
    "g_i_drdltplat003": {"armor": 5, "resist": {ENERGY: 2}, "cost": 1000},
    "g_i_drdmdplat001": {"armor": 2, "resist": {ENERGY: 1}, "cost": 800},
    "g_i_drdmdplat002": {"armor": 4, "resist": {ENERGY: 2, BLUD: 1, PIERCE: 1, SLASH: 1}, "cost": 1500},
    "g_i_drdmdplat003": {"armor": 5, "resist": {ENERGY: 2, BLUD: 2, PIERCE: 2, SLASH: 2}, "cost": 2500},
    "g_i_drdhvplat001": {"armor": 1, "resist": {ENERGY: 2, BLUD: 1, PIERCE: 1, SLASH: 1}, "cost": 2000},
    "g_i_drdhvplat002": {"armor": 3, "resist": {ENERGY: 3, BLUD: 2, PIERCE: 2, SLASH: 2}, "cost": 3500},
    "g_i_drdhvplat003": {"armor": 4, "resist": {ENERGY: 3, BLUD: 3, PIERCE: 3, SLASH: 3}, "cost": 5000},
    "g1_i_drdhvplat01": {"armor": 5, "abilities": {STR: 3},
                         "resist": {ENERGY: 4, BLUD: 3, PIERCE: 3, SLASH: 3, ION: 2, SONIC: 2}, "cost": 12000},
    # shields (belt slot): armour plus resistances
    "g_i_drdshld001": {"armor": 1, "resist": {ENERGY: 1}, "cost": 600},
    "g_i_drdshld002": {"armor": 2, "resist": {ENERGY: 2, SONIC: 1}, "cost": 1000},
    "g_i_drdshld003": {"armor": 3, "resist": {ENERGY: 3, SONIC: 2, ION: 1}, "cost": 1600},
    "g_i_drdshld005": {"armor": 1, "resist": {FIRE: 1, COLD: 1}, "cost": 600},
    "g_i_drdshld006": {"armor": 2, "resist": {FIRE: 2, COLD: 2, ACID: 1}, "cost": 1000},
    "g_i_drdshld007": {"armor": 3, "resist": {FIRE: 3, COLD: 3, ACID: 2, ELEC: 1}, "cost": 1600},
    "g_i_drdshld008": {"armor": 3, "resist": {ENERGY: 2}, "cost": 5000},
    "g1_i_drdshld001": {"armor": 4, "resist": {ENERGY: 4, SONIC: 3, ELEC: 3}, "cost": 6000},
    # targeting computers (head slot, shared with the sensors and scopes)
    "g_i_drdtrgcom001": {"attack": 1, "cost": 800},
    "g_i_drdtrgcom002": {"attack": 2, "damage": 1, "cost": 2000},
    "g_i_drdtrgcom003": {"attack": 3, "damage": 2, "abilities": {DEX: 2}, "cost": 3500},
    "g_i_drdtrgcom005": {"abilities": {DEX: 1}},
    "g_i_drdtrgcom006": {"abilities": {DEX: 2}},
    # sensors and scopes: keep the skill bonus, the higher tiers add an ability
    "g_i_drdmtnsen002": {"abilities": {DEX: 1}},
    "g_i_drdmtnsen003": {"abilities": {DEX: 2}},
    "g_i_drdsncsen002": {"abilities": {CON: 1}, "cost": FLOOR_COST},
    "g_i_drdsncsen003": {"abilities": {CON: 2}, "cost": FLOOR_COST},
    "g_i_drdsrcscp002": {"abilities": {STR: 1}, "cost": FLOOR_COST},
    "g_i_drdsrcscp003": {"abilities": {STR: 2}, "cost": FLOOR_COST},
}


def _gear_property(name, subtype, table, value):
    prop = UTIProperty()
    prop.property_name, prop.subtype, prop.cost_table, prop.cost_value = name, subtype, table, value
    prop.param1, prop.param1_value, prop.chance_appear = 255, 0, 100
    return prop


def build_gear(inst, resref, spec):
    """The droid item's template with `spec` applied: its armour bonus replaced, the other bonuses added after its own properties
    (the droid-only use limit and any skill bonus or cast spell are kept)."""
    res = inst.resource(resref, ResourceType.UTI)  # default order: a few droid items are only in module files
    if res is None:
        raise RuntimeError(f"{resref}.uti not found")
    uti = read_uti(res.data)
    if "armor" in spec:
        assert spec["armor"] <= ARMOR_MAX
        uti.properties = [p for p in uti.properties if p.property_name != PROP_ARMOR]
        uti.properties.append(_gear_property(PROP_ARMOR, 0, 2, spec["armor"]))
    for ability, bonus in spec.get("abilities", {}).items():
        uti.properties.append(_gear_property(PROP_ABILITY, ability, 1, bonus))
    if "attack" in spec:
        uti.properties.append(_gear_property(PROP_ATTACK, 0, 2, spec["attack"]))
    if "damage" in spec:
        uti.properties.append(_gear_property(PROP_DAMAGE, ENERGY, 4, spec["damage"]))
    for damage_type, level in spec.get("resist", {}).items():
        uti.properties.append(_gear_property(PROP_RESIST, damage_type, 7, level))
    cost = max(uti.cost, spec.get("cost", 0), FLOOR_COST)
    uti.cost = uti.add_cost = cost
    return uti


def build_cand_hide(inst):
    """The droid hide with Canderous's own Regeneration property added (copied from his original hide)."""
    find = [SearchLocation.OVERRIDE, SearchLocation.CHITIN]
    droid = read_uti(inst.resource(DROID_HIDE, ResourceType.UTI, find).data)
    orig = read_uti(inst.resource(CAND_ORIGINAL_HIDE, ResourceType.UTI, find).data)
    regen = [p for p in orig.properties if p.property_name == REGENERATION_PROPERTY]
    assert len(regen) == 1, "expected exactly one Regeneration property on Canderous's original hide"
    droid.properties.append(regen[0])
    droid.tag = CAND_HIDE
    return droid


# ---- install / uninstall ----------------------------------------------------------------------------------------------
def uninstall(override):
    manifest_path = os.path.join(override, MANIFEST)
    manifest = _read_json(manifest_path, None)
    removed = 0
    if manifest is None:
        return 0
    for name, backup in manifest.get("files", {}).items():
        path = os.path.join(override, name)
        backup_path = os.path.join(override, backup) if backup else None
        if backup_path and os.path.exists(backup_path):
            shutil.move(backup_path, path)
        elif os.path.exists(path):
            os.remove(path)
        removed += 1
    for table_name, rows in manifest.get("cells", {}).items():
        path = os.path.join(override, table_name + ".2da")
        if not rows or not os.path.isfile(path):
            continue
        table = read_2da(open(path, "rb").read())
        for row, cells in rows.items():
            for header, value in cells.items():
                table.set_cell(int(row), header, value)
        write_2da(table, path, ResourceType.TwoDA)
        removed += 1
    os.remove(manifest_path)
    return removed


def install(game_dir, override, rec, pc_droid, plan, gates_own_guard=False):
    inst = Installation(game_dir)

    # Battle Droid class (the droid PC's class; a companion may be dealt it too)
    for name, table in build_battle_tables(inst, override).items():
        rec.put(name + ".2da", lambda p, t=table: write_2da(t, p, ResourceType.TwoDA))

    # melee weapons open to droids
    baseitems = _load_table(inst, override, "baseitems")
    for row in MELEE_BASEITEM_ROWS:
        rec.edit_cell(baseitems, "baseitems", row, "droidorhuman", "0")
    _write_table(baseitems, override, "baseitems")

    # Taris elevator: a droid PC carrying the Sith armor passes (the vanilla script only accepts it worn).
    # Skipped when the story gates already wrap the same script for an area randomizer seed (patch_story_gates.py):
    # that wrapper lets everyone through, droid included, and two writers of one script is not allowed.
    if pc_droid and not gates_own_guard:
        orig = inst.resource(ALERTSITH, ResourceType.NCS, [SearchLocation.MODULES], module_root=ALERTSITH_MODULE)
        if orig is None:
            raise RuntimeError(f"{ALERTSITH}.ncs not found in module {ALERTSITH_MODULE}")
        rec.put(f"apo_{ALERTSITH}_orig.ncs", lambda p: open(p, "wb").write(orig.data))
        rec.copy(ALERTSITH_WRAPPER_NCS, f"{ALERTSITH}.ncs")
    if pc_droid:
        for name in PERSUADE_OVERRIDES:
            rec.copy(os.path.join(REPO_ROOT, "extender", "scripts_src", f"{name}_droid.ncs"), f"{name}.ncs")

    # models + the appearance rows that host them
    appearance = _load_table(inst, override, "appearance")
    if pc_droid:
        for ext in ("mdl", "mdx"):
            rec.copy(os.path.join(RAW_OVERRIDE_DIR, f"{HK_VARIANT_MODEL}.{ext}"), f"{HK_VARIANT_MODEL}.{ext}")
        rec.copy(os.path.join(RAW_OVERRIDE_DIR, "ap_hk47v_01.tga"), "ap_hk47v_01.tga")
        _clone_row(rec, appearance, "appearance", HK_VARIANT_ROW, HK47_ROW, "AP_HK47_Variant", HK_VARIANT_MODEL)
    if plan:
        for model, row, source in ((WAR_MODEL, WAR_ROW, WAR_SOURCE_ROW), (ASSASSIN_MODEL, ASSASSIN_ROW, ASSASSIN_SOURCE_ROW)):
            for ext in ("mdl", "mdx"):
                rec.copy(os.path.join(RAW_OVERRIDE_DIR, f"{model}.{ext}"), f"{model}.{ext}")
            _clone_row(rec, appearance, "appearance", row, source, f"AP_{model}", model, modeltype="F")
        # Mark Two has no ranged attack of its own; the fixed model aliases its melee clips as ranged ones
        for ext in ("mdl", "mdx"):
            rec.copy(os.path.join(RAW_OVERRIDE_DIR, f"c_drdmktwo.{ext}"), f"c_drdmktwo.{ext}")
    _write_table(appearance, override, "appearance")

    # companion templates
    if plan:
        rec.put(CAND_HIDE + ".uti", lambda p: write_gff(dismantle_uti(build_cand_hide(inst)), p, ResourceType.UTI))
        for key, (look, droid_class) in plan.items():
            resref = COMPANION_TEMPLATES[key]
            utc = build_companion(inst, resref, int(look), int(droid_class))
            rec.put(resref + ".utc", lambda p, u=utc: write_gff(dismantle_utc(u), p, ResourceType.UTC))

    # droid gear (either option): better plating, shields, targeting computers and sensors
    for resref, spec in DROID_GEAR.items():
        uti = build_gear(inst, resref, spec)
        rec.put(resref + ".uti", lambda p, u=uti: write_gff(dismantle_uti(u), p, ResourceType.UTI))



def _signature(pc_droid, plan, gates_own_guard=False):
    sizes = {"alertsith": os.path.getsize(ALERTSITH_WRAPPER_NCS)}
    for name in PERSUADE_OVERRIDES:
        sizes[name] = os.path.getsize(os.path.join(REPO_ROOT, "extender", "scripts_src", f"{name}_droid.ncs"))
    for name in sorted(os.listdir(RAW_OVERRIDE_DIR)):
        if name.startswith(("ap_hk47v", "ap_drd", "c_drdmktwo")):
            sizes[name] = os.path.getsize(os.path.join(RAW_OVERRIDE_DIR, name))
    return json.dumps({"v": VERSION, "pc": pc_droid, "plan": plan, "assets": sizes, "gates_guard": gates_own_guard, "gear": DROID_GEAR}, sort_keys=True)


def main():
    game_dir = _arg("--game-dir", DEFAULT_GAME_DIR)
    override = os.path.join(game_dir, "Override")
    manifest_path = os.path.join(override, MANIFEST)

    if "--status" in sys.argv:
        m = _read_json(manifest_path, None)
        print("not installed" if m is None else f"installed: {len(m.get('files', {}))} files, tables {sorted(m.get('cells', {}))}")
        return
    if "--restore" in sys.argv:
        print(f"removed {uninstall(override)} droid asset group(s)")
        return

    slot = _read_json(SLOT_DATA_PATH, {})
    starting_class = int(_arg("--starting-class", slot.get("starting_class", 0)))
    companion_mode = int(_arg("--companion-mode", slot.get("companion_class_mode", 0)))
    plan_json = _arg("--plan-json", None)
    raw_plan = json.loads(plan_json) if plan_json else (slot.get("companion_droid_plan") or {})
    pc_droid = starting_class == 4
    plan = {k: v for k, v in raw_plan.items() if k in COMPANION_TEMPLATES} if companion_mode == 4 else {}

    existing = _read_json(manifest_path, None)
    if not pc_droid and not plan:
        print(f"no droid option on this seed; removed {uninstall(override)} droid asset group(s)")
        return

    for marker in LEGACY_MARKERS:
        if os.path.exists(os.path.join(override, marker)):
            sys.exit(f"{marker} is a leftover from the developer test scripts -- run their --restore first")

    gates_own_guard = bool(slot.get("progression_system")) and bool(slot.get("area_randomizer"))
    signature = _signature(pc_droid, plan, gates_own_guard)
    if existing and existing.get("signature") == signature and all(
            os.path.exists(os.path.join(override, n)) for n in existing.get("files", {})):
        print("droid assets unchanged")
        return

    uninstall(override)
    rec = Recorder(override)
    try:
        install(game_dir, override, rec, pc_droid, plan, gates_own_guard)
    finally:
        # even a half-finished install is recorded, so the next run (or --restore) can take it back out
        json.dump({"signature": signature, "files": rec.files, "cells": rec.cells}, open(manifest_path, "w"), indent=1)
    what = ("PC droid" if pc_droid else "") + (" + " if pc_droid and plan else "") + (f"{len(plan)} droid companions" if plan else "")
    print(f"installed droid assets ({what}): {len(rec.files)} files, tables {sorted(rec.cells)}")


if __name__ == "__main__":
    main()
