"""Battle Droid: a third droid class, in the slot the game cut (classes.2da row 10, "BountyHunter(CUT!!!)"), and the item rules that let a droid use melee weapons.

Combat Droid (class 6) and Expert Droid (class 7) are the game's own and cannot use melee weapons: every sword, staff and lightsaber is marked human-only in baseitems.2da
(droidorhuman = 1) and race 5 hides human-only gear. The Battle Droid is a Combat Droid with the lightsaber and melee proficiency feats, a hit die of 10 and a melee and
blaster feat list; the melee rows of baseitems.2da are opened to droids (0 = anyone). Its look is a droid model re-mounted on a human skeleton (tools/build_droid_models.py), the
only way a droid model plays the human melee animations.

Everything is made from the player's own game tables when the seed is patched; nothing from the game is stored in the project. The class tables are edited in memory by
`apply_battle_class` (also used by tools/classrb_data.py, so the class rebuild's data includes class 10 whether or not the Override files exist yet) and written as
`classes.2da`, `feat.2da`, `skills.2da`, `featgain.2da` and `baseitems.2da` for the game's Override folder by `droid_table_files`.
"""
import typing

BATTLE = 10                  # classes.2da row
BATTLE_PREFIX = "drb"        # feat.2da / skills.2da / featgain.2da column prefix (Combat Droid is "drc", Expert Droid "drx")
BATTLE_LABEL = "BattleDroid"
BATTLE_NAME_STRREF = 15680   # "Battle Droid", already in the game's dialog.tlk
CUT_LABEL = "BountyHunter(CUT!!!)"
COMBAT = 6
EXPERT = 7
SKILL_DEMOLITIONS, SKILL_AWARENESS, SKILL_REPAIR, SKILL_SECURITY = 1, 3, 5, 6
BATTLE_CLASS_SKILLS = {SKILL_DEMOLITIONS, SKILL_AWARENESS, SKILL_REPAIR, SKILL_SECURITY}
FEAT_LIGHTSABER_PROF, FEAT_MELEE_PROF = 43, 44
# Feats a Battle Droid may pick on level-up (feat.2da drb_list = 1), in the order the automatic level-up prefers them (drb_recom): the melee and blaster lines interleaved.
# Rows the game has turned into dead entries (labels starting XXX) are skipped when the table is edited.
BATTLE_FEAT_ORDER = [28, 30, 11, 31, 8, 84, 29, 17, 92, 91, 20, 19, 37, 32, 18, 83, 77, 53, 81, 82, 26, 51, 46, 33, 47, 36, 50, 113]
BATTLE_HIT_DIE = 10
BATTLE_SKILL_POINT_BASE = 3
# baseitems.2da rows marked human-only (droidorhuman 1) that are melee weapons: quarterstaff to short lightsaber (0-10), the three alien melee weapons and the force pike.
# Melee is then gated only by the proficiency feats.
MELEE_BASEITEM_ROWS = list(range(0, 11)) + [78, 79, 80, 93]
TABLES = ("classes", "feat", "skills", "featgain", "baseitems")


def _text(table, row: int, header: str) -> str:
    try:
        return table.get_row(row).get_string(header)
    except Exception:  # noqa: BLE001
        return ""


def apply_battle_class(classes, feat, skills, featgain) -> bool:
    """Turns classes.2da row 10 into the Battle Droid, with its own columns in feat, skills and featgain (copies of the Combat Droid's, the feat granting and picking edited).
    Edits the four tables in place. Returns False, changing nothing, when this has been done already (the row is already labelled BattleDroid)."""
    label = _text(classes, BATTLE, "label")
    if label == BATTLE_LABEL:
        return False
    if label != CUT_LABEL:
        raise ValueError("classes.2da row %d is %r: the Battle Droid goes into the row the game cut (%s)" % (BATTLE, label, CUT_LABEL))
    combat = {h: _text(classes, COMBAT, h) for h in classes.get_headers()}
    combat.update({"label": BATTLE_LABEL, "name": str(BATTLE_NAME_STRREF), "hitdie": str(BATTLE_HIT_DIE), "skillpointbase": str(BATTLE_SKILL_POINT_BASE),
                   "featstable": BATTLE_PREFIX.upper(), "skillstable": BATTLE_PREFIX.upper(), "featgain": BATTLE_PREFIX.upper()})
    for header, value in combat.items():
        classes.set_cell(BATTLE, header, value)

    for suffix in ("list", "granted", "recom"):
        feat.add_column("%s_%s" % (BATTLE_PREFIX, suffix))
        for i in range(feat.get_height()):
            feat.set_cell(i, "%s_%s" % (BATTLE_PREFIX, suffix), _text(feat, i, "drc_" + suffix))
    for f in (FEAT_LIGHTSABER_PROF, FEAT_MELEE_PROF):
        feat.set_cell(f, BATTLE_PREFIX + "_list", "3")
        feat.set_cell(f, BATTLE_PREFIX + "_granted", "1")
    rank = 0
    for f in BATTLE_FEAT_ORDER:
        if _text(feat, f, "label").upper().startswith("XXX"):
            continue
        rank += 1
        feat.set_cell(f, BATTLE_PREFIX + "_list", "1")
        feat.set_cell(f, BATTLE_PREFIX + "_recom", str(rank))

    for suffix in ("class", "reco"):
        skills.add_column("%s_%s" % (BATTLE_PREFIX, suffix))
        for i in range(skills.get_height()):
            value = _text(skills, i, "drc_" + suffix)
            if suffix == "class":
                value = "1" if i in BATTLE_CLASS_SKILLS else "0"
            skills.set_cell(i, "%s_%s" % (BATTLE_PREFIX, suffix), value)

    for suffix in ("reg", "bon"):
        featgain.add_column("%s_%s" % (BATTLE_PREFIX, suffix))
        for i in range(featgain.get_height()):
            featgain.set_cell(i, "%s_%s" % (BATTLE_PREFIX, suffix), _text(featgain, i, "drx_" + suffix))
    return True


def open_melee_to_droids(baseitems) -> int:
    """droidorhuman 0 on the melee rows that are 1. Returns how many rows changed."""
    changed = 0
    for row in MELEE_BASEITEM_ROWS:
        if _text(baseitems, row, "droidorhuman") == "1":
            baseitems.set_cell(row, "droidorhuman", "0")
            changed += 1
    return changed


def droid_table_files(game_dir: str) -> typing.Tuple[typing.Dict[str, bytes], typing.List[str]]:
    """({file name: bytes}, problems): the five edited tables for the game's Override folder. A table is read from Override when it is there (another patch may have edited
    it; the edit is a no-op on a table that has it already), else from the game's own files."""
    from pykotor.extract.installation import Installation, SearchLocation
    from pykotor.resource.formats.twoda import bytes_2da, read_2da
    from pykotor.resource.type import ResourceType
    inst = Installation(game_dir)
    tables = {}
    problems: typing.List[str] = []
    for name in TABLES:
        res = inst.resource(name, ResourceType.TwoDA, [SearchLocation.OVERRIDE, SearchLocation.CHITIN])
        if res is None:
            problems.append("%s.2da was not found in the game files" % name)
            continue
        tables[name] = read_2da(res.data)
    if problems:
        return {}, problems
    try:
        apply_battle_class(tables["classes"], tables["feat"], tables["skills"], tables["featgain"])
        open_melee_to_droids(tables["baseitems"])
    except ValueError as e:
        return {}, [str(e)]
    return {name + ".2da": bytes_2da(table) for name, table in tables.items()}, problems


# appearance.2da rows that host the human-rig models (tools/build_droid_models.py) -> the model's resref. A Battle Droid whose look is one of these needs the model files.
# 82 the assassin droid, 58 the Mining Droid Mk II (a hand in place of the cannon), 29 the war droid, 380 the protocol droid (rows 91 and up are the player's body rows in portraits.2da) (the game's own rows 66 and 63 stay the Combat and Expert
# Droids' creature looks). The HK-50 body (row 538) is a game row and needs no model.
HUMAN_RIG_ROWS = {82: "ap_drdassn", 58: "ap_drdmine", 29: "ap_drdwar", 380: "ap_drdprot"}
DISGUISE_LOOKS = frozenset({380})   # looks that are always a disguise effect, never the creature's own appearance (the protocol droid has no fighting animations as a body; user, 2026-11-18)
# The Combat and Expert Droids' own looks (the war droid 66 and the protocol droid 63) are creature models: no weapon stances and no human walk, so a droid that wears one
# stands with its arms bent and holds nothing. The seed names them; the client gives the droid the human-rig body of the same droid instead (rig_looks).
CREATURE_TO_RIG = {66: 29, 63: 380}
FALLBACK_LOOK = 66       # Droid_War_01, a game row: used when a human-rig model could not be built, so nobody is given an appearance row that holds no model


def rig_looks(slot_data: dict) -> int:
    """Replaces, in place, the creature looks (CREATURE_TO_RIG) of the droid player and the droid companions with the human-rig looks. Returns how many were changed. Safe to repeat."""
    changed = 0
    plans = [slot_data.get("start_class") or {}] + list((slot_data.get("companion_classes") or {}).values())
    for plan in plans:
        look = int(plan.get("look") or 0)
        if look in CREATURE_TO_RIG:
            plan["look"] = CREATURE_TO_RIG[look]
            changed += 1
    return changed


def uses_battle_droid(slot_data: dict) -> bool:
    """True when the seed makes the player or a companion a Battle Droid, or gives a droid one of the human-rig looks (whose models and appearance rows must then be built)."""
    if (slot_data.get("start_class") or {}).get("class") == BATTLE:
        return True
    if any(v.get("class") == BATTLE for v in (slot_data.get("companion_classes") or {}).values()):
        return True
    return bool(looks_in_use(slot_data))


def looks_in_use(slot_data: dict) -> typing.Set[int]:
    """The human-rig rows the player and the companions of this seed are given."""
    looks = {(slot_data.get("start_class") or {}).get("look")}
    looks |= {v.get("look") for v in (slot_data.get("companion_classes") or {}).values()}
    return {int(l) for l in looks if l and int(l) in HUMAN_RIG_ROWS}


def fallback_looks(slot_data: dict, rows: typing.Optional[typing.Iterable[int]] = None) -> int:
    """Gives every droid whose look is one of `rows` (default: every human-rig row) the fallback look, in place. Returns how many were changed."""
    rows = set(HUMAN_RIG_ROWS) if rows is None else set(rows)
    changed = 0
    start = slot_data.get("start_class") or {}
    if start.get("look") in rows:
        start["look"] = FALLBACK_LOOK
        changed += 1
    for plan in (slot_data.get("companion_classes") or {}).values():
        if plan.get("look") in rows:
            plan["look"] = FALLBACK_LOOK
            changed += 1
    return changed


def usable_look(look: int, override_dir: str) -> int:
    """The look to use now: a human-rig row only when its model files are in the game's Override folder, else the fallback."""
    import os
    model = HUMAN_RIG_ROWS.get(int(look or 0))
    if model is None:
        return int(look or 0)
    if all(os.path.isfile(os.path.join(override_dir, model + ext)) for ext in (".mdl", ".mdx")):
        return int(look)
    return FALLBACK_LOOK


def droid_files(game_dir: str, slot_data: dict, tools_dir: str, log=None) -> typing.Tuple[typing.Dict[str, bytes], typing.List[str]]:
    """({file name: bytes}, problems) for a seed with a Battle Droid: the class and item tables, the human-rig models and the appearance.2da that hosts them. Empty for a seed
    without one. A model that cannot be built (no MDLOps or numpy, say) is reported, and the droids that were to have its look get the fallback look (`fallback_looks`); the
    other models and the tables are still written. When no model can be built nothing hosts a human-rig look and the caller falls back for all of them."""
    if not uses_battle_droid(slot_data):
        return {}, []
    import sys
    files, problems = droid_table_files(game_dir)
    if not files:
        return {}, problems
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    try:
        import build_droid_models as models
        built, model_problems = models.build(game_dir, None, "all", log)
        problems += model_problems
        if built:
            table, _described = models.appearance_rows(game_dir)
            files.update(built)
            files["appearance.2da"] = table
            missing = {row for row in looks_in_use(slot_data) if not all(HUMAN_RIG_ROWS[row] + e in built for e in (".mdl", ".mdx"))}
            if missing:
                fallback_looks(slot_data, missing)
                problems.append("the human-rig model(s) %s were not built: the droids that were to look like them use the war droid look instead" %
                                ", ".join(sorted(HUMAN_RIG_ROWS[r] for r in missing)))
        else:
            problems.append("the Battle Droid's human-rig models were not built: those droids use the war droid look instead")
    except Exception as e:  # noqa: BLE001 -- the rest of the patch goes ahead
        problems.append("the Battle Droid's human-rig models could not be built: %s" % e)
    return files, problems
