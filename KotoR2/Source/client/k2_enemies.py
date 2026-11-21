"""The enemy randomizer's game side: new hostile creatures are added to the combat areas, on top of what is already there.

The world draws, for each precomputed spawn point, a creature template (enemy_plan in the slot data). The client then
  * writes a copy of that template for each spawn into Override under a name of its own (apen001, apen002, ...) with the same name as its tag. A copy is needed because 32
    of the 91 pool templates exist only inside the module archives (and differ from module to module), and a tag of its own keeps every script that looks a creature up
    by tag from finding the new ones;
  * adds a creature entry for it to the module's GIT (the module .rim, edited in place after a backup, client/k2_modules.py).
Nothing already in a module is changed or removed. Each template's source is "global" (the game's common files) or the module whose copy is used.
"""
import math
import typing

from k2_bounty import build_item as build_datapad, with_datapad

CLONE_PREFIX = "apen"
# Modules that never get new creatures, whatever the seed's plan says (a seed made before a module was excluded still lists its spawns): 305NAR's pit is the arena of the
# Hanharr / Mira encounter, which the story stages itself.
NO_ENEMY_MODULES = frozenset({"305NAR"})
# The share of a module's planned creatures that is really added (the rest is left out), for the areas where the full count was a grind in play: the two Dxun tombs. A
# creature that carries a Bounty Datapad is always kept, so no bounty check can become unreachable.
ENEMY_SHARE = {"410DXN": 0.5, "411DXN": 0.5}
HOSTILE_FACTION = 1            # Hostile_1, the faction of the pool's ordinary enemies


def _source_utc(inst_holder: list, game_dir: str, store, template: str, source: str) -> typing.Optional[bytes]:
    from pykotor.extract.installation import Installation, SearchLocation
    from pykotor.resource.type import ResourceType
    if source != "global":
        for suffix in ("_s", ""):
            if store.exists(source, suffix):
                data = store.resources(source, suffix).get((template.lower(), "utc"))
                if data is not None:
                    return data
        return None
    if not inst_holder:
        inst_holder.append(Installation(game_dir))
    res = inst_holder[0].resource(template, ResourceType.UTC, [SearchLocation.OVERRIDE, SearchLocation.CHITIN])
    return res.data if res else None


def _datapad_files(inst_holder: list, game_dir: str) -> typing.Dict[str, bytes]:
    """{"ap_bounty_card.uti": bytes}, made from the game's own plain plot item (the one the Bazaar's tokens use)."""
    from k2_bazaar import config as bazaar_config
    from pykotor.extract.installation import Installation
    if not inst_holder:
        inst_holder.append(Installation(game_dir))
    return build_datapad(inst_holder[0], bazaar_config()["item_base"])


def clone_utc(data: bytes, clone: str) -> bytes:
    from pykotor.common.misc import ResRef
    from pykotor.resource.formats.gff import bytes_gff, read_gff
    gff = read_gff(data)
    gff.root.set_string("Tag", clone)
    gff.root.set_resref("TemplateResRef", ResRef(clone))
    # A template of the same name can be a scripted, non-hostile version in the module it comes from (the Sith Assassins of 221TEL and 222TEL are faction 5, the
    # Mandalorian and Vulkar templates of several modules are faction 3 or 5): an added creature must always be an enemy.
    gff.root.set_uint16("FactionID", HOSTILE_FACTION)
    return bytes_gff(gff)


def add_creatures(root, entries: typing.Sequence[dict]) -> bool:
    """Appends creature entries (clone, x, y, z, angle) to a GIT's Creature List."""
    from pykotor.common.misc import ResRef
    from pykotor.resource.formats.gff import GFFList
    lst = root.get_list("Creature List") if root.exists("Creature List") else GFFList()
    for e in entries:
        s = lst.add(4)
        s.set_single("XPosition", float(e["x"]))
        s.set_single("YPosition", float(e["y"]))
        s.set_single("ZPosition", float(e["z"]))
        s.set_single("XOrientation", math.cos(float(e["angle"])))
        s.set_single("YOrientation", math.sin(float(e["angle"])))
        s.set_resref("TemplateResRef", ResRef(e["clone"]))
    root.set_list("Creature List", lst)                           # the list returned by get_list is a copy: put it back
    return True


def thin_spawns(spawns: typing.Sequence[dict]) -> typing.List[dict]:
    """Leaves out part of the spawns of the modules listed in ENEMY_SHARE: evenly spread over the module's points, in a fixed order, and never a bounty carrier."""
    out: typing.List[dict] = []
    for module in sorted({s["module"] for s in spawns}):
        mine = sorted((s for s in spawns if s["module"] == module), key=lambda s: (s["x"], s["y"], s["template"]))
        share = ENEMY_SHARE.get(module.upper(), 1.0)
        if share >= 1.0:
            out += mine
            continue
        plain = [s for s in mine if not s.get("bounty")]
        keep = {id(s) for i, s in enumerate(plain) if math.floor((i + 1) * share) > math.floor(i * share)}
        out += [s for s in mine if s.get("bounty") or id(s) in keep]
    return out


def enemy_files(game_dir: str, store, plan: dict) -> typing.Tuple[typing.Dict[str, bytes], int, typing.List[str]]:
    """Builds the creature copies and edits the GITs. Returns ({Override file: bytes}, creatures added, problems). A spawn whose template or module cannot be found
    is skipped and reported; the rest goes ahead."""
    files: typing.Dict[str, bytes] = {}
    problems: typing.List[str] = []
    spawns = thin_spawns([s for s in ((plan or {}).get("spawns") or []) if s["module"].upper() not in NO_ENEMY_MODULES])
    if not spawns:
        return files, 0, problems
    inst_holder: list = []
    cache: typing.Dict[typing.Tuple[str, str], typing.Optional[bytes]] = {}
    by_module: typing.Dict[str, typing.List[dict]] = {}
    missing_templates = set()
    missing_modules = set()
    number = 0
    carriers = 0
    datapad: typing.Dict[str, bytes] = {}
    if any(s.get("bounty") for s in spawns):
        try:
            datapad = _datapad_files(inst_holder, game_dir)
        except Exception as e:                       # without the item file a creature must not list it: the datapads are left out and the rest goes ahead
            problems.append("the bounty datapad could not be built, so no creature carries one: %s" % e)
    for spawn in sorted(spawns, key=lambda s: (s["module"], s["template"], s["x"], s["y"])):
        module = spawn["module"]
        if not store.exists(module):
            missing_modules.add(module)
            continue
        key = (spawn["template"], spawn["source"])
        if key not in cache:
            try:
                cache[key] = _source_utc(inst_holder, game_dir, store, spawn["template"], spawn["source"])
            except Exception as e:
                cache[key] = None
                problems.append("the enemy randomizer: reading %s failed (%s)" % (spawn["template"], e))
        data = cache[key]
        if data is None:
            missing_templates.add(spawn["template"])
            continue
        number += 1
        clone = "%s%03d" % (CLONE_PREFIX, number)
        files[clone + ".utc"] = clone_utc(data, clone)
        if spawn.get("bounty") and datapad:
            files[clone + ".utc"] = with_datapad(files[clone + ".utc"])
            carriers += 1
        by_module.setdefault(module, []).append(dict(spawn, clone=clone))
    added = 0
    for module, entries in sorted(by_module.items()):
        if store.edit_gff(module, None, "git", lambda root, entries=entries: add_creatures(root, entries)):
            added += len(entries)
        else:
            problems.append("the enemy randomizer: module %s has no area list to add to, so it gets no new creatures" % module)
            for e in entries:
                files.pop(e["clone"] + ".utc", None)
    if carriers:
        files.update(datapad)
    if missing_modules:
        problems.append("the enemy randomizer: module file(s) not found: %s" % ", ".join(sorted(missing_modules)))
    if missing_templates:
        problems.append("the enemy randomizer: creature template(s) not found, those spots stay empty: %s" % ", ".join(sorted(missing_templates)))
    return files, added, problems
