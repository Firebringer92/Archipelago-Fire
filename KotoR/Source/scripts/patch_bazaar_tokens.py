"""
Places the Archipelago Bazaar's 100 tokens (ap_bz_token, see generate_bazaar_jawa.py) into module containers.

Only for seeds with the Archipelago Bazaar on (slot data "bazaar"). The rules, decided with the design (FutureDesign.md, F4):
  - 100 tokens, one per container, containers only (never an enemy's drop);
  - at most 10 in any one module;
  - none in the end game (Leviathan, Unknown World, Star Forge, Yavin), the Ebon Hawk or the Endar Spire, and none in the unused
    Black Vulkar level (tar_m10ab) or the Hidden Bek Base (tar_m11aa / tar_m11ab);
  - only ordinary containers: usable, with an inventory, not plot, not static, and no quest script on them (the random-treasure scripts
    k_plc_tres* are fine).
Which containers is decided by the seed name, so a re-run gives the same placement.

How: a container's contents live in its template (UTP), which every instance of that template shares. So each chosen container gets its
own copy of its template, apbz<NNN>.utp in Override, with the token added to its item list (same tag and everything else), and the
module's GIT instance is pointed at the copy. A module that already holds an apbz template is left alone. Like the other module patchers
this edits <modules>/<module>.rim in place after backing it up into the shared extender/backup/modules (--restore puts every backup back),
and it must run AFTER patch_loot_disturb.py (which rebuilds templates from that backup).

Usage:  python patch_bazaar_tokens.py [--game-dir=DIR] [--force --seed=NAME] [--dry-run] [--restore]
        (--modules-dir / --override-dir / --backup-dir override the folders under --game-dir; used to test on a scratch copy)
"""
import json
import os
import random
import shutil
import sys

from pykotor.common.misc import ResRef
from pykotor.extract.installation import Installation, SearchLocation
from pykotor.resource.formats.gff import GFFList, read_gff, write_gff
from pykotor.resource.formats.rim import read_rim, write_rim
from pykotor.resource.generics.git import construct_git, dismantle_git
from pykotor.resource.type import ResourceType

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SLOT_DATA_PATH = os.path.join(REPO_ROOT, "extender", "area_trampolines", "_slot_data.json")
DEFAULT_BACKUP_DIR = os.path.join(REPO_ROOT, "extender", "backup", "modules")
DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"

TOKEN_RESREF = "ap_bz_token"
TOKEN_TOTAL = 100
PER_MODULE_CAP = 10
CLONE_PREFIX = "apbz"

# Modules whose containers may hold a token (every play area outside the exclusions in the module docstring).
ELIGIBLE_MODULES = [
    # Taris
    "tar_m02aa", "tar_m02ad", "tar_m03ab", "tar_m03ad", "tar_m04aa", "tar_m05aa", "tar_m05ab", "tar_m08aa", "tar_m09aa",
    "tar_m10aa", "tar_m10ac",
    # Dantooine
    "danm13", "danm14ab", "danm14ac", "danm14ad", "danm15", "danm16",
    # Kashyyyk
    "kas_m22aa", "kas_m22ab", "kas_m23aa", "kas_m23ab", "kas_m23ac", "kas_m24aa",
    # Korriban
    "korr_m33aa", "korr_m33ab", "korr_m34aa", "korr_m35aa", "korr_m36aa", "korr_m37aa", "korr_m38aa", "korr_m38ab", "korr_m39aa",
    # Manaan
    "manm26ae", "manm27aa", "manm28aa", "manm28ab", "manm28ac",
    # Tatooine
    "tat_m17aa", "tat_m17ab", "tat_m18aa", "tat_m18ab", "tat_m18ac", "tat_m20aa",
]
# A container script that belongs to a quest keeps the container out; the generic random-treasure scripts do not.
_SCRIPT_FIELDS = ("OnOpen", "OnUsed", "OnInvDisturbed", "OnHeartbeat", "OnClosed", "OnLock", "OnUnlock")
_GENERIC_SCRIPT_PREFIX = "k_plc_tres"


def _arg(flag, default=None):
    for a in sys.argv[1:]:
        if a.startswith(flag + "="):
            return a.split("=", 1)[1]
    return default


def _slot_data():
    if not os.path.isfile(SLOT_DATA_PATH):
        return None
    try:
        with open(SLOT_DATA_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"  (couldn't read {SLOT_DATA_PATH}: {e})")
        return None


def _eligible_template(t):
    """True for an ordinary container template (a GFF root)."""
    if not t.get_uint8("HasInventory") or t.get_uint8("Plot") or t.get_uint8("Static") or not t.get_uint8("Useable"):
        return False
    for field in _SCRIPT_FIELDS:
        script = str(t.get_resref(field)).lower() if t.exists(field) else ""
        if script and not script.startswith(_GENERIC_SCRIPT_PREFIX):
            return False
    return True


def _with_token(template_gff_root):
    """The template with one token added to its item list."""
    items = template_gff_root.get_list("ItemList") if template_gff_root.exists("ItemList") else GFFList()
    entry = items.add(0)
    entry.set_resref("InventoryRes", ResRef(TOKEN_RESREF))
    entry.set_uint16("Repos_PosX", 0)
    entry.set_uint16("Repos_PosY", 0)
    template_gff_root.set_list("ItemList", items)


def restore(modules_dir, override_dir, backup_dir):
    removed = 0
    for fname in os.listdir(override_dir) if os.path.isdir(override_dir) else []:
        low = fname.lower()
        if low.startswith(CLONE_PREFIX) and low.endswith(".utp"):
            os.remove(os.path.join(override_dir, fname))
            removed += 1
    print(f"  removed {removed} token container template(s) from Override")
    if not os.path.isdir(backup_dir):
        print("No backup directory found -- nothing to restore.")
        return
    restored = 0
    for fname in os.listdir(backup_dir):
        shutil.copy2(os.path.join(backup_dir, fname), os.path.join(modules_dir, fname))
        restored += 1
    print(f"Restored {restored} module RIM(s) from backup.")


def main():
    game_dir = _arg("--game-dir", DEFAULT_GAME_DIR)
    modules_dir = _arg("--modules-dir", os.path.join(game_dir, "modules"))
    override_dir = _arg("--override-dir", os.path.join(game_dir, "Override"))
    backup_dir = _arg("--backup-dir", DEFAULT_BACKUP_DIR)
    dry = "--dry-run" in sys.argv

    if "--restore" in sys.argv:
        restore(modules_dir, override_dir, backup_dir)
        return

    if "--force" in sys.argv:
        seed_name = _arg("--seed", "bazaar-test")
    else:
        data = _slot_data()
        if data is None:
            print(f"No usable data at {SLOT_DATA_PATH} -- connect once with KotorClient.py first (or pass --force --seed=NAME).")
            return
        if not data.get("bazaar", False):
            print("The Archipelago Bazaar is off for this seed -- no tokens to place.")
            return
        seed_name = data.get("seed_name") or "bazaar"
    rng = random.Random(f"{seed_name}|bazaar-tokens")

    installation = Installation(game_dir)
    core_cache = {}

    def core_template(resref):
        if resref not in core_cache:
            res = installation.resource(resref, ResourceType.UTP, [SearchLocation.CHITIN, SearchLocation.OVERRIDE])
            core_cache[resref] = res.data if res else None
        return core_cache[resref]

    # 1. every eligible container: (module, index of the instance in the GIT, template resref, template bytes)
    candidates = {}
    already_patched = set()
    for module in ELIGIBLE_MODULES:
        path = os.path.join(modules_dir, f"{module}.rim")
        if not os.path.exists(path):
            print(f"  {module}: RIM not found, skipping")
            continue
        local = {}
        for suffix in ("_s.rim", ".rim"):
            side = os.path.join(modules_dir, f"{module}{suffix}")
            if os.path.exists(side):
                for res in read_rim(side):
                    if res.restype == ResourceType.UTP:
                        local[str(res.resref).lower()] = res.data
        git_res = next((r for r in read_rim(path) if r.restype == ResourceType.GIT), None)
        if git_res is None:
            continue
        git = construct_git(read_gff(git_res.data))
        found = []
        for i, placeable in enumerate(git.placeables):
            resref = str(placeable.resref).lower()
            if resref.startswith(CLONE_PREFIX):
                already_patched.add(module)
                continue
            raw = local.get(resref) or core_template(resref)
            if raw is None:
                continue
            if _eligible_template(read_gff(raw).root):
                found.append((i, resref, raw))
        candidates[module] = found

    todo = [m for m in candidates if m not in already_patched]
    for m in sorted(already_patched):
        print(f"  {m}: already has token containers (an {CLONE_PREFIX}* template is placed) -- skipping. Run --restore to re-roll.")

    # 2. choose 100 containers, at most 10 per module (a module that is already patched keeps what it has)
    kept = 0
    pool = [(m, c) for m in todo for c in candidates[m]]
    rng.shuffle(pool)
    chosen = {}
    taken = {}
    for m, c in pool:
        if kept >= TOKEN_TOTAL:
            break
        if taken.get(m, 0) >= PER_MODULE_CAP:
            continue
        chosen.setdefault(m, []).append(c)
        taken[m] = taken.get(m, 0) + 1
        kept += 1
    if kept < TOKEN_TOTAL:
        print(f"WARNING: only {kept} of {TOKEN_TOTAL} tokens could be placed (not enough eligible containers).")

    # 3. write the copies and repoint the GIT instances
    next_clone = 1
    for module in sorted(chosen):
        path = os.path.join(modules_dir, f"{module}.rim")
        archive = read_rim(path)
        git_res = next(r for r in archive if r.restype == ResourceType.GIT)
        git = construct_git(read_gff(git_res.data))
        for index, resref, raw in chosen[module]:
            clone = f"{CLONE_PREFIX}{next_clone:03d}"
            next_clone += 1
            gff = read_gff(raw)
            _with_token(gff.root)
            gff.root.set_resref("TemplateResRef", ResRef(clone))
            blob = bytearray()
            write_gff(gff, blob)
            if not dry:
                os.makedirs(override_dir, exist_ok=True)
                with open(os.path.join(override_dir, f"{clone}.utp"), "wb") as f:
                    f.write(bytes(blob))
            git.placeables[index].resref = ResRef(clone)
        if not dry:
            os.makedirs(backup_dir, exist_ok=True)
            backup_path = os.path.join(backup_dir, f"{module}.rim")
            if not os.path.exists(backup_path):
                shutil.copy2(path, backup_path)
            new_git = bytearray()
            write_gff(dismantle_git(git), new_git)
            archive.set_data(git_res.resref, ResourceType.GIT, bytes(new_git))
            write_rim(archive, path)
        print(f"  {module}: {len(chosen[module])} token(s)")

    placed = sum(len(v) for v in chosen.values())
    print(f"\nDone. {'Would place' if dry else 'Placed'} {placed} Bazaar token(s) in {len(chosen)} module(s).")
    if not dry:
        print(f"Backup at {backup_dir} -- restore via `python patch_bazaar_tokens.py --restore`.")


if __name__ == "__main__":
    main()
