"""The crafting mode's game side: the project recipe table for the workbench, the item values that set what a recipe costs, and the per-type unlocks.

What the live bench tests found (docs/CRAFTING_FEASIBILITY.md): the workbench builds any item named in a recipe-table row; the cost in Components is the template's
AddCost field divided by 20 (rounded down) and the yield of breaking an item down is AddCost divided by 200 (rounded down, at least 1); a recipe is listed when its
required rank is at most the character's rank in the recipe's skill plus 8. So this module
  * writes k2se_recipes.2da: the game's own item-creation rows (copied from the player's install, never shipped) and a row for each piece of gear in the plan, laid out
    on the bench tab that matches its type; the console's workbench entry opens that table in place of the game's;
  * writes a copy of each gear template with the AddCost the mode asks for;
  * builds only the rows of the types that are unlocked (crafting_gated), and the flags that show or hide the console's three entries.
Modes (the world sends mode, seed, gated, types, gear): 1 simple: gear needs a rank from its value and costs its normal amount; 2 complex: ranks 6 higher (at most
32), the game's own rows too, and double the cost; 3 random_requirements: every rank random 1 to 32 and the cost a random multiple (a half to four times).
"""
import random
import typing

TABLE = "k2se_recipes"
SIMPLE, COMPLEX, RANDOM = 1, 2, 3
TYPE_GROUP = {"armor": 0, "ranged": 1, "melee": 2, "lightsaber": 3, "other": 4}       # the bench tab each type lands on
REPAIR = 5                                                                              # the skill the bench rows ask for
COST_FACTORS = (0.5, 1.0, 1.5, 2.0, 3.0, 4.0)
MAX_RANK = 32


def base_rank(basis: int) -> int:
    """The rank a gear recipe asks for in simple mode: one more than the value in 250s, at most 30 (the game's own ranks do not follow value)."""
    return max(1, min(30, 1 + basis // 250))


def new_add_cost(basis: int, factor: float) -> int:
    """AddCost for a template: the basis times the factor, a multiple of 20 and at least 20, so a recipe never costs nothing."""
    return max(20, int(round(basis * factor / 20.0)) * 20)


def flags(plan: dict, unlocked: typing.Collection[str]) -> typing.Dict[str, int]:
    """The console's switches: bench (the workbench entry), up (the upgrade screen), lab. Without gating all three are on."""
    if not plan:
        return {}
    have = (lambda t: True) if not plan.get("gated") else (lambda t: t in unlocked)
    bench = any(have(t) for t in plan.get("types", []) if t != "lab")
    if plan["mode"] == 0 and plan.get("gated"):
        bench = have("parts")                                   # no gear rows without a crafting mode: the game's own table only
    return {"ap_craft_bench": int(bench), "ap_craft_up": int(have("parts")), "ap_craft_lab": int(have("lab"))}


def flag_lines(plan: dict, unlocked: typing.Collection[str]) -> typing.List[str]:
    return ["%s=%d" % (k, v) for k, v in sorted(flags(plan, unlocked).items())]


def _vanilla_table(inst):
    from pykotor.extract.installation import SearchLocation
    from pykotor.resource.formats.twoda import read_2da
    from pykotor.resource.type import ResourceType
    res = inst.resource("itemcreate", ResourceType.TwoDA, [SearchLocation.OVERRIDE, SearchLocation.CHITIN])
    if res is None:
        raise FileNotFoundError("the game's item-creation table (itemcreate.2da) was not found")
    return read_2da(res.data)


def _pristine_item(inst, resref: str) -> typing.Optional[bytes]:
    """The game's own template (the common files only: an Override copy may be one this client wrote earlier)."""
    from pykotor.extract.installation import SearchLocation
    from pykotor.resource.type import ResourceType
    res = inst.resource(resref, ResourceType.UTI, [SearchLocation.CHITIN])
    return res.data if res else None


def gear_terms(root, resref: str, mode: int, seed: int) -> typing.Tuple[int, int, int]:
    """(rank, the AddCost the template should carry, its current AddCost) for one gear template under the mode: the one rule the table, the templates and the
    material yield all follow."""
    add_cost = int(root.get_uint32("AddCost")) if root.exists("AddCost") else 0
    cost = int(root.get_uint32("Cost")) if root.exists("Cost") else 0
    basis = max(add_cost, cost)
    rng = random.Random("%d|item|%s" % (seed, resref))
    if mode == SIMPLE:
        rank, factor = base_rank(basis), 1.0
    elif mode == COMPLEX:
        rank, factor = min(MAX_RANK, base_rank(basis) + 6), 2.0
    else:
        rank, factor = rng.randint(1, MAX_RANK), rng.choice(COST_FACTORS)
    wanted = new_add_cost(basis, factor)
    if mode == SIMPLE and add_cost >= 20:
        wanted = add_cost                                       # simple mode keeps a template as it is unless it would build for nothing
    return rank, wanted, add_cost


def yield_of(add_cost: int) -> int:
    """What breaking an item down returns, and what a gear item gives in Components: AddCost / 200, at least 1."""
    return max(1, add_cost // 200)


def material_yields(game_dir: str, plan: dict) -> typing.Dict[str, int]:
    """{gear resref: Components} the gear items of the plan give in crafting mode (from the AddCost its template carries under the mode)."""
    from pykotor.extract.installation import Installation
    from pykotor.resource.formats.gff import read_gff
    out: typing.Dict[str, int] = {}
    if not plan or not plan.get("mode"):
        return out
    inst = Installation(game_dir)
    for resref, _ in plan.get("gear", []):
        data = _pristine_item(inst, resref)
        if data is not None:
            _, wanted, _ = gear_terms(read_gff(data).root, resref, int(plan["mode"]), int(plan["seed"]))
            out[resref] = yield_of(wanted)
    return out


def crafting_files(game_dir: str, plan: dict, unlocked: typing.Collection[str],
                   received: typing.Optional[typing.Collection[str]] = None) -> typing.Tuple[typing.Dict[str, bytes], typing.List[str]]:
    """({Override file: bytes}, problems): the recipe table, and the gear templates whose AddCost changes. With plan["gear_gated"] a gear row is in the table only once
    its gear item is in `received` (a set of template names); the templates are written regardless, so costs do not depend on what has arrived."""
    from pykotor.extract.installation import Installation
    from pykotor.resource.formats.gff import bytes_gff, read_gff
    from pykotor.resource.formats.twoda import TwoDA, bytes_2da
    files: typing.Dict[str, bytes] = {}
    problems: typing.List[str] = []
    if not plan or not plan.get("mode"):
        return files, problems
    mode, seed, gated = int(plan["mode"]), int(plan["seed"]), bool(plan.get("gated"))
    gear_gated = bool(plan.get("gear_gated"))
    have = set(received or ())
    inst = Installation(game_dir)
    vanilla = _vanilla_table(inst)
    headers = vanilla.get_headers()
    table = TwoDA(headers)

    def unlocked_type(t: str) -> bool:
        return (not gated) or t in unlocked

    n = 0
    if unlocked_type("parts"):
        for row in vanilla:
            cells = {h: row.get_string(h) for h in headers}
            rank = int(cells["skill"] or 0)
            if mode == COMPLEX:
                rank = min(MAX_RANK, rank + 6)
            elif mode == RANDOM:
                rank = random.Random("%d|row|%s" % (seed, row.label())).randint(1, MAX_RANK)
            cells["skill"] = str(rank)
            table.add_row(str(n), cells)
            n += 1
    for resref, kind in plan.get("gear", []):
        data = _pristine_item(inst, resref)
        if data is None:
            problems.append("crafting: the template %s was not found in the game's files, it has no recipe" % resref)
            continue
        gff = read_gff(data)
        rank, wanted, add_cost = gear_terms(gff.root, resref, mode, seed)
        if wanted != add_cost:
            gff.root.set_uint32("AddCost", wanted)
            files[resref + ".uti"] = bytes_gff(gff)
        if unlocked_type(kind) and (not gear_gated or resref in have):
            cells = {h: "" for h in headers}
            cells.update({"label": resref, "skill": str(rank), "group": str(TYPE_GROUP[kind]), "level": "0", "align": "0", "base_skill": str(REPAIR), "dunno": "0"})
            table.add_row(str(n), cells)
            n += 1
    files[TABLE + ".2da"] = bytes_2da(table)
    return files, problems
