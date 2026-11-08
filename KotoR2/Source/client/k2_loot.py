"""The loot randomizer's game side: the ordinary gear lying in containers and carried by creatures is replaced (or topped up) with random pieces from the shop pool.

Loot that sits in a template is plain data, so it is changed the way the Bazaar tokens and the stores are: in the module files (the _s.rim of each module holds its
container and creature templates), in place after a backup, put back on revert (client/k2_modules.py). What it touches, and what it never touches:
  * only items of the pool (the world sends it: ordinary, non-plot, non-quest gear with a price); quest items, plot items, credits, datapads and everything else stay;
  * containers: each pool item in the template becomes another pool item (replace), or the template gets one more (bonus, only when it already held some gear);
  * creatures: only what the creature drops counts. Carried gear is what its AI equips from the pack, so it is never swapped out: replace makes the original
    non-droppable (the creature still uses it) and adds the pick as the droppable item; bonus adds one droppable pick to a creature that carries something;
  * runtime loot (the random-treasure containers and creature spawn scripts) is left alone;
  * modules in the plan's skip list (the opening module, whose gear the first minutes need) are not touched.
Every pick is seeded by the world's seed number, the module, the template and the entry, so it does not depend on the order of work.
"""
import random
import typing

REPLACE, BONUS = "replace", "bonus"
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


def change_template(plan: dict, module: str, resref: str, ext: str, root) -> bool:
    """Applies the plan to one container (utp) or creature (utc) template. Returns whether it changed."""
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


def loot_files(store, plan: dict) -> typing.Tuple[int, typing.List[str]]:
    """Edits every module file of the game that holds templates, except the skipped modules. Returns (templates changed, problems)."""
    if not plan or not plan.get("pool"):
        return 0, []
    skip = {m.upper() for m in plan.get("skip_modules", [])}
    total = 0
    problems: typing.List[str] = []
    for module in store.modules("_s"):
        if module.upper() in skip:
            continue
        try:
            total += store.edit_resources(module, ("utp", "utc"), lambda r, e, root, m=module: change_template(plan, m, r, e, root), "_s")
        except Exception as e:
            problems.append("the loot randomizer: %s_s.rim could not be changed (%s), its loot stays" % (module, e))
    return total, problems
