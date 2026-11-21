"""The shop randomizer's game side: restocks the game's stores and silences the game's own stock scripts.

A store's static stock is the ItemList of its template (a UTM), which lives in the module's _s.rim; the client edits it there in place (client/k2_modules.py: backup first,
put back on revert). The game also adds level-scaled random items the first time the player talks to a shopkeeper (the a_stock* scripts); for a randomized shop those
would pile their own items on the seed's list, so every one of them is replaced by an empty script in Override.

The plan (which stores, which items, which scripts) comes from the world's slot data (shop_plan).
"""
import typing

# `void main() {}` compiled with nwnsc and stripped of NOPs (tools/ncs_nops.py): the engine runs it and does nothing. test_shop compares it to a fresh compile.
EMPTY_SCRIPT = bytes.fromhex("4e43532056312e3042000000171e000000000820002000")
ROW_WIDTH = 10                  # a store's item grid is ten wide


def apply_item_list(root, stock: typing.Sequence[str]) -> bool:
    """Replaces a UTM's ItemList by the stock, laid out row by row; every item is infinite (the K1 shops held 99 of each)."""
    from pykotor.common.misc import ResRef
    from pykotor.resource.formats.gff import GFFList
    items = GFFList()
    for n, resref in enumerate(stock):
        entry = items.add(0)
        entry.set_resref("InventoryRes", ResRef(resref))
        entry.set_uint16("Repos_PosX", n % ROW_WIDTH)
        entry.set_uint16("Repos_Posy", n // ROW_WIDTH)              # the game's own spelling of the field
        entry.set_uint8("Infinite", 1)
    root.set_list("ItemList", items)
    return True


# crafting_gated stores sell only these: the game's Components (compont_00001) and Chemicals (chem_00001) are free (Cost 0), so each gets a copy with a price; the tag and base item
# stay, which is what the workbench and the chemical lab count. Prices are the Archipelago Vendor's smallest bundle rate (data/vendor.json: 10 for 300 credits).
SUPPLY_ITEMS = {"ap_shpcomp": "compont_00001", "ap_shpchem": "chem_00001"}
SUPPLY_PRICE = 30


def supply_items(game_dir: str) -> typing.Tuple[typing.Dict[str, bytes], typing.List[str]]:
    """({Override file: bytes}, problems): the two priced supply items, made from the player's own item templates."""
    from pykotor.extract.installation import Installation, SearchLocation
    from pykotor.resource.formats.gff import bytes_gff, read_gff
    from pykotor.resource.type import ResourceType
    inst = Installation(game_dir)
    files: typing.Dict[str, bytes] = {}
    problems: typing.List[str] = []
    for new, source in SUPPLY_ITEMS.items():
        res = inst.resource(source, ResourceType.UTI, [SearchLocation.CHITIN])
        if res is None:
            problems.append("the item %s was not found in the game files, so the shops cannot sell it" % source)
            continue
        gff = read_gff(res.data)
        gff.root.set_uint32("Cost", SUPPLY_PRICE)
        files[new + ".uti"] = bytes_gff(gff)
    return files, problems


def shop_files(store, plan: dict, game_dir: typing.Optional[str] = None) -> typing.Tuple[typing.Dict[str, bytes], typing.List[str]]:
    """Edits the stores of the plan in their module files and returns ({Override file: bytes}, problems). With the plan's supplies_only the priced supply items are made too."""
    files: typing.Dict[str, bytes] = {}
    problems: typing.List[str] = []
    if not plan:
        return files, problems
    if plan.get("supplies_only"):
        if game_dir is None:
            problems.append("the shops' crafting supplies were not made: the game folder was not given")
        else:
            made, supply_problems = supply_items(game_dir)
            files.update(made)
            problems += supply_problems
    for entry in plan.get("stores", []):
        module, utm = entry["module"], entry["utm"]
        if not store.exists(module, "_s"):
            problems.append("the shop randomizer: module %s_s.rim was not found, so its store %s keeps its stock" % (module, entry["tag"]))
            continue
        stock = list(entry["stock"])
        if not store.edit_gff(module, utm, "utm", lambda root, stock=stock: apply_item_list(root, stock), "_s"):
            problems.append("the shop randomizer: store %s was not found in %s_s.rim, so it keeps its stock" % (utm, module))
    for name in plan.get("silence", []):
        files[name + ".ncs"] = EMPTY_SCRIPT
    return files, problems
