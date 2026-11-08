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

CLONE_PREFIX = "apen"


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


def clone_utc(data: bytes, clone: str) -> bytes:
    from pykotor.common.misc import ResRef
    from pykotor.resource.formats.gff import bytes_gff, read_gff
    gff = read_gff(data)
    gff.root.set_string("Tag", clone)
    gff.root.set_resref("TemplateResRef", ResRef(clone))
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


def enemy_files(game_dir: str, store, plan: dict) -> typing.Tuple[typing.Dict[str, bytes], int, typing.List[str]]:
    """Builds the creature copies and edits the GITs. Returns ({Override file: bytes}, creatures added, problems). A spawn whose template or module cannot be found
    is skipped and reported; the rest goes ahead."""
    files: typing.Dict[str, bytes] = {}
    problems: typing.List[str] = []
    spawns = (plan or {}).get("spawns") or []
    if not spawns:
        return files, 0, problems
    inst_holder: list = []
    cache: typing.Dict[typing.Tuple[str, str], typing.Optional[bytes]] = {}
    by_module: typing.Dict[str, typing.List[dict]] = {}
    missing_templates = set()
    missing_modules = set()
    number = 0
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
        by_module.setdefault(module, []).append(dict(spawn, clone=clone))
    added = 0
    for module, entries in sorted(by_module.items()):
        if store.edit_gff(module, None, "git", lambda root, entries=entries: add_creatures(root, entries)):
            added += len(entries)
        else:
            problems.append("the enemy randomizer: module %s has no area list to add to, so it gets no new creatures" % module)
            for e in entries:
                files.pop(e["clone"] + ".utc", None)
    if missing_modules:
        problems.append("the enemy randomizer: module file(s) not found: %s" % ", ".join(sorted(missing_modules)))
    if missing_templates:
        problems.append("the enemy randomizer: creature template(s) not found, those spots stay empty: %s" % ", ".join(sorted(missing_templates)))
    return files, added, problems
