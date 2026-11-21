"""The loot randomizer's game side: the ordinary gear lying in containers and carried by creatures is replaced (or topped up) with random pieces from the shop pool.

Loot that sits in a template is plain data, so it is changed the way the Bazaar tokens and the stores are: in the module files (the _s.rim of each module holds its
container and creature templates), in place after a backup, put back on revert (client/k2_modules.py). What it touches, and what it never touches:
  * only items of the pool (the world sends it: ordinary, non-plot, non-quest gear with a price); quest items, plot items, credits, datapads and everything else stay;
  * containers: each pool item in the template becomes another pool item (replace), or the template gets one more (bonus, only when it already held some gear);
  * creatures: only what the creature drops counts. Carried gear is what its AI equips from the pack, so it is never swapped out: replace makes the original
    non-droppable (the creature still uses it) and adds the pick as the droppable item; bonus adds one droppable pick to a creature that carries something;
  * crafting mode: each pool item becomes crafting Components instead of another piece of gear (the item compont_00001, as many entries as the piece is worth, at most ten);
  * runtime loot (the random-treasure containers and creature spawn scripts) is left alone;
  * modules in the plan's skip list (the opening module, whose gear the first minutes need) are not touched.
Every pick is seeded by the world's seed number, the module, the template and the entry, so it does not depend on the order of work.
"""
import random
import typing

REPLACE, BONUS, CRAFTING = "replace", "bonus", "crafting"
COMPONENTS = "compont_00001"       # the crafting Components item (the bench counts one per unit)
MAX_COMPONENTS = 10             # entries of it that one piece of gear turns into at most
ROW_WIDTH = 10                  # the item grid of a container is laid out ten to a row


def _pick(plan: dict, module: str, resref: str, ext: str, index: int) -> str:
    rng = random.Random("%s|%s|%s|%s|%d" % (plan["seed"], module.upper(), resref, ext, index))
    return rng.choice(plan["pool"])


def _append(items, resref: str, droppable: bool) -> None:
    from pykotor.common.misc import ResRef
    position = len(items)
    entry = items.add(0)
    entry.set_resref("InventoryRes", ResRef(resref))
    entry.set_uint16("Repos_PosX", position % ROW_WIDTH)
    entry.set_uint16("Repos_Posy", position // ROW_WIDTH)          # the game's own spelling of the field
    if droppable:
        entry.set_uint8("Dropable", 1)


def components_for(game_dir: str) -> typing.Callable[[str], int]:
    """resref -> how many Components the piece of gear is worth in crafting mode: its value / 200, at least 1 (what the workbench returns for breaking it down), at most ten.
    Read from the player's own item templates; a piece that cannot be read counts as one."""
    from pykotor.extract.installation import Installation, SearchLocation
    from pykotor.resource.formats.gff import read_gff
    from pykotor.resource.type import ResourceType
    inst = Installation(game_dir)
    cache: typing.Dict[str, int] = {}

    def worth(resref: str) -> int:
        key = resref.lower()
        if key not in cache:
            count = 1
            try:
                res = inst.resource(key, ResourceType.UTI, [SearchLocation.OVERRIDE, SearchLocation.CHITIN])
                if res is not None:
                    root = read_gff(res.data).root
                    value = max(int(root.get_uint32("Cost")) if root.exists("Cost") else 0, int(root.get_uint32("AddCost")) if root.exists("AddCost") else 0)
                    count = min(MAX_COMPONENTS, max(1, value // 200))
            except Exception:
                count = 1
            cache[key] = count
        return cache[key]
    return worth


def change_template(plan: dict, module: str, resref: str, ext: str, root, worth: typing.Optional[typing.Callable[[str], int]] = None) -> bool:
    """Applies the plan to one container (utp) or creature (utc) template. Returns whether it changed. `worth` (crafting mode): resref -> Components."""
    from pykotor.common.misc import ResRef
    if not root.exists("ItemList"):
        return False
    pool = set(plan["pool"])
    items = root.get_list("ItemList")
    creature = ext == "utc"
    existing = list(items)
    if not existing:
        return False
    changed = False
    gear = 0
    for index, item in enumerate(existing):
        if str(item.get_resref("InventoryRes")).lower() not in pool:
            continue
        if creature and not (item.exists("Dropable") and item.get_uint8("Dropable")):
            continue                                              # carried but not dropped: the creature's own gear
        gear += 1
        if plan["mode"] == CRAFTING:
            count = worth(str(item.get_resref("InventoryRes")).lower()) if worth else 1
            if creature:
                item.set_uint8("Dropable", 0)                     # the creature still uses its gear, but drops Components instead
                for _ in range(count):
                    _append(items, COMPONENTS, True)
            else:
                item.set_resref("InventoryRes", ResRef(COMPONENTS))
                for _ in range(count - 1):
                    _append(items, COMPONENTS, False)
            changed = True
            continue
        if plan["mode"] != REPLACE:
            continue
        pick = _pick(plan, module, resref, ext, index)
        if creature:
            item.set_uint8("Dropable", 0)                         # the creature still uses it (it equips from its pack), but it no longer drops
            _append(items, pick, True)
        else:
            item.set_resref("InventoryRes", ResRef(pick))
        changed = True
    if plan["mode"] == BONUS and (gear or creature):
        _append(items, _pick(plan, module, resref, ext, len(existing)), True)
        changed = True
    if changed:
        root.set_list("ItemList", items)                       # the list returned by get_list is a copy: put the appended entries back
    return changed


def loot_files(store, plan: dict, game_dir: typing.Optional[str] = None) -> typing.Tuple[int, typing.List[str]]:
    """Edits every module file of the game that holds templates, except the skipped modules. Returns (templates changed, problems). game_dir is read in crafting mode,
    for what each piece of gear is worth in Components."""
    if not plan or not plan.get("pool"):
        return 0, []
    worth = components_for(game_dir) if plan.get("mode") == CRAFTING and game_dir else None
    skip = {m.upper() for m in plan.get("skip_modules", [])}
    total = 0
    problems: typing.List[str] = []
    for module in store.modules("_s"):
        if module.upper() in skip:
            continue
        try:
            total += store.edit_resources(module, ("utp", "utc"), lambda r, e, root, m=module: change_template(plan, m, r, e, root, worth), "_s")
        except Exception as e:
            problems.append("the loot randomizer: %s_s.rim could not be changed (%s), its loot stays" % (module, e))
    return total, problems
