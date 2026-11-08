"""Places the Bazaar's hundred tokens (ap_bz_token) into containers of the game's modules, the way the KotOR 1 patcher does.

A container's contents live in its template, which every instance of that template shares. So each chosen container gets its own copy of its template, apbz<NNN>.utp in
Override, with the token added to its item list (same tag and everything else), and the module's GIT instance is pointed at the copy (client/k2_modules.py edits the module
file in place after a backup). The choice is made from the seed's name, so a re-run gives the same placement.

Rules (the K1 rules, adapted): 100 tokens, one per container, containers only; at most 10 in any one module; only ordinary containers (usable, with an inventory, not plot, not
static, and no script of their own beyond the game's generic treasure scripts); only the free-roam areas listed below (none in the prologue, the Ebon Hawk, the endgame or the
scenes the player cannot come back to).
"""
import random
import typing

TOKEN_RESREF = "ap_bz_token"
CLONE_PREFIX = "apbz"
GENERIC_SCRIPT_PREFIXES = ("k_plc_tres", "k_plc_treas")
SCRIPT_FIELDS = ("OnOpen", "OnUsed", "OnInvDisturbed", "OnHeartbeat", "OnClosed", "OnLock", "OnUnlock")

# Free-roam areas: Telos and the Citadel, Nar Shaddaa, Dxun, Onderon, Dantooine, Korriban. Left out on purpose: the prologue (101-106PER, 151-153HAR), the Ebon Hawk, 262TEL (the
# last Telos scene), 351NAR (the yacht), 702KOR (locks behind the player), 710/711KOR (visions), the Malachor finale.
ELIGIBLE_MODULES = [
    "201TEL", "202TEL", "203TEL", "204TEL", "207TEL", "208TEL", "209TEL", "231TEL", "232TEL", "233TEL", "261TEL",
    "301NAR", "302NAR", "303NAR", "304NAR", "305NAR", "306NAR",
    "401DXN", "402DXN", "403DXN", "404DXN", "410DXN", "411DXN",
    "501OND", "502OND", "503OND", "504OND", "506OND", "511OND", "512OND",
    "601DAN", "602DAN", "604DAN", "605DAN", "610DAN",
    "701KOR",
]


def eligible_template(root) -> bool:
    """An ordinary container template (a GFF root)."""
    if not root.get_uint8("HasInventory") or root.get_uint8("Plot") or root.get_uint8("Static") or not root.get_uint8("Useable"):
        return False
    for field in SCRIPT_FIELDS:
        script = str(root.get_resref(field)).lower() if root.exists(field) else ""
        if script and not script.startswith(GENERIC_SCRIPT_PREFIXES):
            return False
    return True


def with_token(data: bytes) -> bytes:
    """The container template with one token added to its item list."""
    from pykotor.common.misc import ResRef
    from pykotor.resource.formats.gff import GFFList, bytes_gff, read_gff
    gff = read_gff(data)
    root = gff.root
    items = root.get_list("ItemList") if root.exists("ItemList") else GFFList()
    entry = items.add(0)
    entry.set_resref("InventoryRes", ResRef(TOKEN_RESREF))
    entry.set_uint16("Repos_PosX", 0)
    entry.set_uint16("Repos_PosY", 0)
    root.set_list("ItemList", items)
    return bytes_gff(gff)


def find_candidates(game_dir: str, store, modules: typing.Iterable[str]) -> typing.Dict[str, typing.List[typing.Tuple[int, str, bytes]]]:
    """{module: [(index of the placeable in the GIT, template resref, template bytes)]} for the ordinary containers of each module. Instances already pointing at a clone
    are skipped (the client restores the modules before it places, so this only matters after a partial earlier run)."""
    from pykotor.extract.installation import Installation, SearchLocation
    from pykotor.resource.formats.gff import read_gff
    from pykotor.resource.type import ResourceType
    installation: typing.List[typing.Any] = []              # opened only when a template is not in the module itself
    core: typing.Dict[str, typing.Optional[bytes]] = {}

    def core_template(resref: str) -> typing.Optional[bytes]:
        if resref not in core:
            if not installation:
                installation.append(Installation(game_dir))
            inst = installation[0]
            res = inst.resource(resref, ResourceType.UTP, [SearchLocation.OVERRIDE, SearchLocation.CHITIN])
            core[resref] = res.data if res else None
        return core[resref]

    out: typing.Dict[str, typing.List[typing.Tuple[int, str, bytes]]] = {}
    for module in modules:
        if not store.exists(module):
            continue
        local: typing.Dict[str, bytes] = {}
        for suffix in ("", "_s"):
            if store.exists(module, suffix):
                for (resref, ext), data in store.resources(module, suffix).items():
                    if ext == "utp":
                        local[resref] = data
        git_data = next((d for (r, ext), d in store.resources(module).items() if ext == "git"), None)
        if git_data is None:
            continue
        placeables = read_gff(git_data).root.get_list("Placeable List")
        found = []
        for i, placeable in enumerate(placeables):
            resref = str(placeable.get_resref("TemplateResRef")).lower()
            if resref.startswith(CLONE_PREFIX):
                continue
            raw = local.get(resref) or core_template(resref)
            if raw is not None and eligible_template(read_gff(raw).root):
                found.append((i, resref, raw))
        out[module] = found
    return out


def plan_tokens(candidates: typing.Dict[str, list], seed_name: str, total: int = 100, cap: int = 10) -> typing.List[dict]:
    """Chooses the containers: [{module, index, resref, clone}] in a fixed order. Deterministic for a seed name."""
    rng = random.Random("%s|bazaar-tokens" % seed_name)
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


def apply_plan(store, chosen: typing.List[dict]) -> typing.Dict[str, bytes]:
    """Points the GIT instances at the clones (module files, backed up) and returns {clone file name: bytes} for Override."""
    from pykotor.common.misc import ResRef
    by_module: typing.Dict[str, typing.List[dict]] = {}
    for item in chosen:
        by_module.setdefault(item["module"], []).append(item)
    files: typing.Dict[str, bytes] = {}
    for module, items in by_module.items():
        def change(root, items=items):
            placeables = root.get_list("Placeable List")
            for item in items:
                placeables[item["index"]].set_resref("TemplateResRef", ResRef(item["clone"]))
            return True
        store.edit_gff(module, None, "git", change)
        for item in items:
            files[item["clone"] + ".utp"] = with_token(item["raw"])
    return files


def token_files(game_dir: str, store, seed_name: str) -> typing.Tuple[typing.Dict[str, bytes], typing.List[str]]:
    """Plans and applies the token placement for a seed: the module files are edited (backed up first) and the clone templates are returned for Override.
    The modules must be in the game's own state (the client restores them first)."""
    from k2_bazaar import config
    cfg = config()
    total, cap = int(cfg["tokens_total"]), int(cfg["tokens_per_module"])
    candidates = find_candidates(game_dir, store, ELIGIBLE_MODULES)
    chosen = plan_tokens(candidates, seed_name, total, cap)
    problems = []
    if len(chosen) < total:
        problems.append("only %d of the %d Bazaar tokens could be placed (not enough ordinary containers found)" % (len(chosen), total))
    return apply_plan(store, chosen), problems


def clone_files(chosen: typing.List[dict]) -> typing.Dict[str, bytes]:
    """The Override clones alone (when the module files already carry this seed's edits)."""
    return {item["clone"] + ".utp": with_token(item["raw"]) for item in chosen}
