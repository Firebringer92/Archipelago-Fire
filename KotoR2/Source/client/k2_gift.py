"""The AP Companion Gift's world side: fifty gifts hidden in containers of the free-roam areas, the way the Bazaar's tokens are (client/k2_bazaar_tokens.py).

Not an option of the seed: the placement is made from the seed's name alone, so a re-run puts the same gifts in the same containers. A container that already holds a
Bazaar token (its instance points at an apbz clone) is not used again. Each chosen container gets its own copy of its template, apgf<NNN>.utp in Override, with one
ap_gift added to its item list, and the module's GIT instance is pointed at the copy (the module files are edited in place after a backup, client/k2_modules.py).
The item and the menu are built by client/k2_assets.py; the ten gifts the player starts with are a dispatcher job (the client's start grant).
"""
import random
import typing

from k2_bazaar_tokens import ELIGIBLE_MODULES, apply_plan, find_candidates

GIFT_RESREF = "ap_gift"
CLONE_PREFIX = "apgf"
TOTAL = 50                    # gifts hidden in the world
PER_MODULE = 4                # at most this many in any one module
START_STOCK = 0               # gifts the Exile starts with: none in the shipped build (a tester can give gifts with /k2_give gift <n>); the gifts hidden in containers stay


def with_gift(data: bytes) -> bytes:
    """The container template with one gift added to its item list."""
    from pykotor.common.misc import ResRef
    from pykotor.resource.formats.gff import GFFList, bytes_gff, read_gff
    gff = read_gff(data)
    root = gff.root
    items = root.get_list("ItemList") if root.exists("ItemList") else GFFList()
    entry = items.add(0)
    entry.set_resref("InventoryRes", ResRef(GIFT_RESREF))
    entry.set_uint16("Repos_PosX", 0)
    entry.set_uint16("Repos_PosY", 0)
    root.set_list("ItemList", items)
    return bytes_gff(gff)


def plan_gifts(candidates: typing.Dict[str, list], seed_name: str, total: int = TOTAL, cap: int = PER_MODULE) -> typing.List[dict]:
    """The containers that get a gift: [{module, index, resref, raw, clone}] in a fixed order. Deterministic for a seed name."""
    rng = random.Random("%s|companion-gifts" % seed_name)
    pool = [(m, c) for m in sorted(candidates) for c in candidates[m]]
    rng.shuffle(pool)
    chosen: typing.List[dict] = []
    per: typing.Dict[str, int] = {}
    for module, (index, resref, raw) in pool:
        if len(chosen) >= total:
            break
        if per.get(module, 0) >= cap:
            continue
        per[module] = per.get(module, 0) + 1
        chosen.append({"module": module, "index": index, "resref": resref, "raw": raw})
    for n, item in enumerate(sorted(chosen, key=lambda c: (c["module"], c["index"])), 1):
        item["clone"] = "%s%03d" % (CLONE_PREFIX, n)
    return chosen


def gift_files(game_dir: str, store, seed_name: str) -> typing.Tuple[typing.Dict[str, bytes], typing.List[str]]:
    """Plans and applies the gift placement: the module files are edited (backed up first) and the clone templates are returned for Override. Run after the Bazaar's
    tokens, on modules in the game's own state plus those edits."""
    candidates = find_candidates(game_dir, store, ELIGIBLE_MODULES)
    chosen = plan_gifts(candidates, seed_name)
    problems = []
    if len(chosen) < TOTAL:
        problems.append("only %d of the %d AP Companion Gifts could be placed (not enough ordinary containers found)" % (len(chosen), TOTAL))
    return apply_plan(store, chosen, with_gift), problems
