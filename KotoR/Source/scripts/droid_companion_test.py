"""
Test-only droid companion prepatch (live test of the "all companions are droids" design).

Writes, into the game's Override:
  * modified copies of the seven non-droid companions' templates (p_<name>.utc): Race 5 (droid), SubraceIndex 0,
    a droid look and a droid class dealt out at random (seeded), class level 1 with that class's level-1 feat kit;
  * a test "Battle Droid" class as classes.2da row 9 (hit die 10, full attack bonus, 3 skill points, class skills
    Awareness/Security/Demolitions/Repair, blaster/rifle/heavy + lightsaber + melee proficiency), with its own DRB
    columns added to feat.2da, skills.2da and featgain.2da. The class reuses the Combat Droid name string, so it
    DISPLAYS as "Combat Droid" -- dialog.tlk is deliberately not touched (build_ap_tracker_quest.py expects its own
    strings at the very end of that file).
HK-47 and T3-M4 are untouched.

Templates only affect companions spawned AFTER the files land, so test on a save where these companions have not
been recruited yet (then /ap_apply companion_<name>).

  python droid_companion_test.py apply   [--seed=N] [--game-dir=PATH]
  python droid_companion_test.py restore [--game-dir=PATH]
  python droid_companion_test.py show    [--game-dir=PATH]

Everything written is recorded in <game>/Override/droid_test_manifest.json; restore removes exactly those files and
puts back any same-named file that was there before.
"""
import json
import os
import random
import shutil
import sys

from pykotor.extract.installation import Installation, SearchLocation
from pykotor.resource.formats.gff import write_gff
from pykotor.resource.formats.twoda import read_2da, write_2da
from pykotor.common.misc import EquipmentSlot, InventoryItem, ResRef
from pykotor.resource.generics.utc import UTCClass, dismantle_utc, read_utc
from pykotor.resource.generics.uti import dismantle_uti, read_uti
from pykotor.resource.type import ResourceType

DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"

COMPANIONS = ["p_bastilla", "p_cand", "p_carth", "p_jolee", "p_juhani", "p_mission", "p_zaalbar"]
# appearance.2da rows: war 66, assassin 56, sentry 64, spyder 65, Mark Four 59, Mark Two 61, Mark One 60
# human-rig war droid (row 58) and assassin droid (row 82) replace the creature-style versions; the other five are unchanged
LOOKS = [58, 82, 64, 65, 59, 61, 60]
# for this test the two human-rig looks go to the two Battle Droid companions (class 9 can equip melee); the swap keeps the class deal
PINNED = {"p_mission": 58, "p_juhani": 82}
COMBAT, EXPERT, BATTLE = 6, 7, 9
CLASS_HAND = [COMBAT, COMBAT, COMBAT, EXPERT, EXPERT, BATTLE, BATTLE]  # dealt out at random across the seven
DROID_RACE = 5
MANIFEST = "droid_test_manifest.json"

# ---- Battle Droid (test class, classes.2da row 9) -------------------------------------------------------------
BATTLE_PREFIX = "drb"
SKILL_COMPUTER_USE, SKILL_DEMOLITIONS, SKILL_STEALTH, SKILL_AWARENESS = 0, 1, 2, 3
SKILL_PERSUADE, SKILL_REPAIR, SKILL_SECURITY, SKILL_TREAT_INJURY = 4, 5, 6, 7
BATTLE_CLASS_SKILLS = {SKILL_AWARENESS, SKILL_SECURITY, SKILL_DEMOLITIONS, SKILL_REPAIR}
FEAT_LIGHTSABER_PROF, FEAT_MELEE_PROF = 43, 44
# Feats a Battle Droid may pick on level-up (feat.2da drb_list = 1) with their auto-level preference order (drb_recom,
# 1 = first choice): the melee and the blaster lines interleaved. Prerequisites (earlier feat / character level) are
# enforced by the game itself.
BATTLE_FEAT_ORDER = [
    28,   # Power Attack
    30,   # Rapid Shot
    11,   # Flurry
    31,   # Sniper Shot
    8,    # Critical Strike
    84,   # Toughness
    29,   # Power Blast
    17,   # Improved Power Attack
    92,   # Improved Rapid Shot
    91,   # Improved Flurry
    20,   # Improved Sniper Shot
    19,   # Improved Critical Strike
    37,   # Weapon Focus: Melee
    32,   # Weapon Focus: Blaster
    18,   # Improved Power Blast
    83,   # Master Power Attack
    77,   # Master Sniper Shot
    53,   # Whirlwind Attack
    81,   # Master Critical Strike
    82,   # Master Power Blast
    26,   # Multi-Shot
    51,   # Weapon Specialization: Melee
    46,   # Weapon Specialization: Blaster
    33,   # Weapon Focus: Blaster Rifle
    35,   # Weapon Focus: Heavy Weapons
    47,   # Weapon Specialization: Blaster Rifle
    49,   # Weapon Specialization: Heavy Weapons
    36,   # Weapon Focus: Lightsaber
    50,   # Weapon Specialization: Lightsaber
    113,  # Dueling
]


def _arg(flag, default):
    for a in sys.argv[2:]:
        if a.startswith(flag + "="):
            return a.split("=", 1)[1]
    return default


def _write_2da_file(table, path):
    write_2da(table, path, ResourceType.TwoDA)


def _load_table(inst, name):
    res = inst.resource(name, ResourceType.TwoDA, [SearchLocation.OVERRIDE, SearchLocation.CHITIN])
    if res is None:
        raise RuntimeError(f"{name}.2da not found")
    return read_2da(res.data)


def build_battle_tables(inst):
    """Returns {"classes": TwoDA, "feat": TwoDA, "skills": TwoDA, "featgain": TwoDA} with the Battle Droid added."""
    classes = _load_table(inst, "classes")
    assert classes.get_height() == 9, "classes.2da row count changed -- check the Battle Droid row index"
    src = classes.get_row(COMBAT)
    cells = {h: src.get_string(h) for h in classes.get_headers()}
    cells.update({"label": "BattleDroid", "hitdie": "10", "skillpointbase": "3", "attackbonustable": "CLS_ATK_1",
                  "featstable": BATTLE_PREFIX.upper(), "skillstable": BATTLE_PREFIX.upper(),
                  "featgain": BATTLE_PREFIX.upper()})
    new_index = classes.add_row(str(classes.get_height()), cells)
    assert new_index == BATTLE, f"Battle Droid landed on row {new_index}, expected {BATTLE}"

    feat = _load_table(inst, "feat")
    for suffix in ("list", "granted", "recom"):
        feat.add_column(f"{BATTLE_PREFIX}_{suffix}")
        for i in range(feat.get_height()):
            feat.set_cell(i, f"{BATTLE_PREFIX}_{suffix}", feat.get_row(i).get_string(f"drc_{suffix}"))
    for f in (FEAT_LIGHTSABER_PROF, FEAT_MELEE_PROF):
        feat.set_cell(f, f"{BATTLE_PREFIX}_granted", "1")
    for rank, f in enumerate(BATTLE_FEAT_ORDER, start=1):
        feat.set_cell(f, f"{BATTLE_PREFIX}_list", "1")
        feat.set_cell(f, f"{BATTLE_PREFIX}_recom", str(rank))

    skills = _load_table(inst, "skills")
    for suffix in ("class", "reco"):
        skills.add_column(f"{BATTLE_PREFIX}_{suffix}")
        for i in range(skills.get_height()):
            value = skills.get_row(i).get_string(f"drc_{suffix}")
            if suffix == "class":
                value = "1" if i in BATTLE_CLASS_SKILLS else "0"
            skills.set_cell(i, f"{BATTLE_PREFIX}_{suffix}", value)

    featgain = _load_table(inst, "featgain")
    for suffix in ("reg", "bon"):
        featgain.add_column(f"{BATTLE_PREFIX}_{suffix}")
        for i in range(featgain.get_height()):
            featgain.set_cell(i, f"{BATTLE_PREFIX}_{suffix}", featgain.get_row(i).get_string(f"drx_{suffix}"))

    return {"classes": classes, "feat": feat, "skills": skills, "featgain": featgain}


# Level-1 feat kit per droid class (feat.2da `<prefix>_granted` == 1 at class level 1; the later droid upgrades and
# logic upgrades arrive from the class table at their own levels as the companion auto-levels).
FEAT_KIT = {
    COMBAT: [39, 40, 42, 78, 110],
    EXPERT: [39, 96, 78, 110],
    BATTLE: [39, 40, 42, 43, 44, 78, 110],
}
HIT_DIE = {COMBAT: 12, EXPERT: 8, BATTLE: 10}
# Vanilla droid creature hide (immunity to mind spells, paralysis and poison): HK-47 wears this one. Every droid gets it,
# replacing any hide the old companion had (Canderous's and Juhani's).
DROID_HIDE = "g_i_crhide013"
# Canderous keeps his Regeneration +4 (it lived on his own hide, g_i_crhide007): he gets a custom hide that is the droid hide plus
# that one property. Resref must stay <= 16 characters.
CAND_HIDE = "ap_drdhide_cand"
CAND_ORIGINAL_HIDE = "g_i_crhide007"


def build_companion(inst, resref, appearance, droid_class):
    """Droid companion template: Race 5, subrace 0, droid look, class level 1 with that class's level-1 feat kit
    (replacing the old class's feats), level-1 hit points and no Force points. KOTOR's own auto-level then raises
    the companion to the party's level through the real class tables."""
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


def build_cand_hide(inst):
    """The droid hide with Canderous's own Regeneration property added (copied from his original hide)."""
    droid = read_uti(inst.resource(DROID_HIDE, ResourceType.UTI, [SearchLocation.OVERRIDE, SearchLocation.CHITIN]).data)
    orig = read_uti(inst.resource(CAND_ORIGINAL_HIDE, ResourceType.UTI, [SearchLocation.OVERRIDE, SearchLocation.CHITIN]).data)
    regen = [p for p in orig.properties if p.property_name == 35]
    assert len(regen) == 1, "expected exactly one Regeneration property on Canderous's original hide"
    droid.properties.append(regen[0])
    droid.tag = CAND_HIDE
    return droid


def deal(seed):
    rng = random.Random(seed)
    looks = LOOKS[:]
    classes = CLASS_HAND[:]
    rng.shuffle(looks)
    rng.shuffle(classes)
    plan = {resref: [look, cls] for resref, look, cls in zip(COMPANIONS, looks, classes)}
    for who, want in PINNED.items():
        if plan[who][0] != want:
            other = next(k for k, v in plan.items() if v[0] == want)
            plan[other][0], plan[who][0] = plan[who][0], want
    return {k: (v[0], v[1]) for k, v in plan.items()}


def _put(path, writer, record, key):
    backup = None
    if os.path.exists(path):
        backup = path + ".droidtest_backup"
        shutil.copy2(path, backup)
    writer(path)
    record[key] = {"path": path, "backup": backup}


def apply(game_dir):
    override = os.path.join(game_dir, "Override")
    manifest_path = os.path.join(override, MANIFEST)
    if os.path.exists(manifest_path):
        sys.exit("already applied -- run restore first")
    seed = int(_arg("--seed", random.SystemRandom().randrange(1, 10**6)))
    inst = Installation(game_dir)
    plan = deal(seed)
    tables = build_battle_tables(inst)
    record = {}
    for name, table in tables.items():
        _put(os.path.join(override, name + ".2da"), lambda p, t=table: _write_2da_file(t, p), record, name + ".2da")
    cand_hide = build_cand_hide(inst)
    _put(os.path.join(override, CAND_HIDE + ".uti"),
         lambda p, u=cand_hide: write_gff(dismantle_uti(u), p, ResourceType.UTI), record, CAND_HIDE + ".uti")
    for resref, (look, cls) in plan.items():
        utc = build_companion(inst, resref, look, cls)
        _put(os.path.join(override, resref + ".utc"),
             lambda p, u=utc: write_gff(dismantle_utc(u), p, ResourceType.UTC), record, resref + ".utc")
    json.dump({"seed": seed, "plan": plan, "files": record}, open(manifest_path, "w"), indent=1)
    names = {COMBAT: "Combat Droid", EXPERT: "Expert Droid", BATTLE: "Battle Droid (class 9, shows as 'Combat Droid')"}
    print(f"seed {seed}")
    for resref, (look, cls) in plan.items():
        print(f"  {resref:11s} look {look:3d}  class {cls} = {names[cls]}")
    print("applied. Restart the game, make a NEW save (companions not yet recruited), then /ap_apply companion_<name>.")


def restore(game_dir):
    override = os.path.join(game_dir, "Override")
    manifest_path = os.path.join(override, MANIFEST)
    if not os.path.exists(manifest_path):
        sys.exit("nothing to restore (no manifest)")
    for key, info in json.load(open(manifest_path))["files"].items():
        path = info["path"]
        if info["backup"] and os.path.exists(info["backup"]):
            shutil.move(info["backup"], path)
            print(f"  restored previous {key}")
        elif os.path.exists(path):
            os.remove(path)
            print(f"  removed {key}")
    os.remove(manifest_path)
    print("restored.")


def show(game_dir):
    override = os.path.join(game_dir, "Override")
    manifest_path = os.path.join(override, MANIFEST)
    if not os.path.exists(manifest_path):
        print("not applied")
        return
    m = json.load(open(manifest_path))
    print("seed", m["seed"])
    for resref in COMPANIONS:
        path = os.path.join(override, resref + ".utc")
        if os.path.exists(path):
            u = read_utc(open(path, "rb").read())
            print(f"{resref:11s} race {u.race_id} subrace {u.subrace_id} look {u.appearance_id} "
                  f"classes {[(c.class_id, c.class_level) for c in u.classes]}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "show"
    game = _arg("--game-dir", DEFAULT_GAME_DIR)
    {"apply": apply, "restore": restore, "show": show}[mode](game)
