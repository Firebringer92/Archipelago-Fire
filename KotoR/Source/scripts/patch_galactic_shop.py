r"""
Galactic Shop (Options.py's GalacticShop) -- the local game
install half. KotorClient.py runs this on every Connect (reads
galactic_shop from _slot_data.json); a tester can also run it by hand.

When galactic_shop is ON it:
  1. Writes Override/ap_voidbox.utp -- a brand-new placeable template
     cloned from the vanilla generic metal crate (metalbox001), renamed,
     emptied, with OnInvDisturbed pointed at ap_galtradebox. A NEW resref
     rather than an edit to metalbox001 itself, because that template is
     reused by ~15 modules game-wide -- editing it in place would affect
     every one of them, not just the intended shop box.
  2. Writes Override/ap_galcoin.uti -- the Galactic Coin, cloned from
     g_i_asthitem001 (Aesthetic_Item, BaseItem 65: a plain base type with
     no hardcoded engine behavior, picked deliberately -- BaseItem 55 is
     medical equipment and carries real engine-side use/consume behavior
     that would misrepresent a currency token).
  3. Copies the precompiled extender/scripts_src/ap_galtradebox.ncs into
     Override (recompiling it from .nss when nwnnsscomp.exe is available,
     so a source edit can't silently ship stale bytecode).
  4. Retargets exactly ONE of the 5 cargo-hold crate placeables in
     modules/ebo_m12aa.rim (the Ebon Hawk's main deck) from
     plstccrt001/metalbox001 to ap_voidbox, named "Galactic Shop" (the
     UTP's LocName -- was "one obvious shop box" vs. the original spike's
     all-5, which the live-confirmed spike used to troubleshoot a
     visibility issue; one clearly-named container reads better than 5
     identical unlabeled crates once you're not debugging visibility any
     more). The other 4 stay/return to their real vanilla template.
     Deterministic pick (lowest position) so re-running this always
     chooses the same physical crate and self-corrects an older run that
     boxed all 5. Backed up first to extender/backup/modules/ebo_m12aa.rim,
     same convention as patch_additional_enemies.py.

When galactic_shop is OFF (or --restore): puts the vanilla RIM back from
that backup if one exists, and removes the 3 Override files. The Ebon
Hawk is a module the player is inside constantly, so note the same
engine gotcha the spike hit: a save made INSIDE ebo_m12aa embeds its own
snapshot of the placeable list -- a real module transition (leave and
come back, or `warp ebo_m12aa`) is needed before an edit shows up.

Usage:
  python patch_galactic_shop.py                      -- apply per _slot_data.json
  python patch_galactic_shop.py --force --on|--off   -- ignore _slot_data.json
  python patch_galactic_shop.py --restore            -- same as --force --off
  python patch_galactic_shop.py --game-dir "D:\...\swkotor"
"""
import json
import os
import shutil
import subprocess
import sys

from pykotor.common.language import LocalizedString
from pykotor.common.misc import ResRef
from pykotor.extract.installation import Installation
from pykotor.resource.formats.gff import read_gff, write_gff
from pykotor.resource.formats.rim import read_rim, write_rim
from pykotor.resource.generics.git import construct_git, dismantle_git
from pykotor.resource.type import ResourceType

from nwnnsscomp_path import resolve_nwnnsscomp  # noqa: E402 -- see that module's docstring

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(REPO_ROOT, "extender", "scripts_src")
SLOT_DATA_PATH = os.path.join(REPO_ROOT, "extender", "area_trampolines", "_slot_data.json")
BACKUP_DIR = os.path.join(REPO_ROOT, "extender", "backup", "modules")
DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
NWNNSSCOMP = resolve_nwnnsscomp()

MODULE = "ebo_m12aa"
BOX_RESREF = "ap_voidbox"
COIN_RESREF = "ap_galcoin"
HANDLER_RESREF = "ap_galtradebox"
# The 5 cargo-hold crates, identified by their vanilla template AND
# position (the module has other plstccrt/metalbox instances elsewhere?
# No -- confirmed via the vanilla GIT dump: exactly these 5 exist, all in
# the one room -- but matching on position too is cheap insurance against
# a future module edit adding more). Only ONE of these 5 becomes the
# shop box -- one obvious "the" Galactic Shop container reads better
# than 5 identical unlabeled crates; the other 4 stay/return to their
# real vanilla resref.
VANILLA_TARGETS = {"plstccrt001", "metalbox001"}


def _pos_key(p):
    """Position is the only stable identity for a GIT placeable instance
    across repeated runs of this script -- resref is the ONE field this
    script ever changes, so a candidate's position never moves, letting a
    later run always find/re-choose the same physical crate (and revert
    any of the other 4 that a PRIOR run of the old all-5 behavior left
    boxed) even though resref alone can no longer distinguish "was this
    one vanilla or already ap_voidbox."""
    return (round(p.position.x, 3), round(p.position.y, 3), round(p.position.z, 3))


def _arg_value(flag, default):
    for i, a in enumerate(sys.argv):
        if a == flag and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
        if a.startswith(flag + "="):
            return a.split("=", 1)[1]
    return default


def _connected_galactic_shop():
    if not os.path.isfile(SLOT_DATA_PATH):
        return None
    try:
        with open(SLOT_DATA_PATH, encoding="utf-8") as f:
            return bool(json.load(f).get("galactic_shop", False))
    except Exception as e:
        print(f"  (couldn't read {SLOT_DATA_PATH}: {e})")
        return None


def _set_locstring(gff_root, label, text):
    gff_root.set_locstring(label, LocalizedString.from_english(text))


def write_box_template(installation: Installation, override_dir: str) -> None:
    src = installation.resource("metalbox001", ResourceType.UTP)
    if src is None:
        sys.exit("vanilla metalbox001.utp not found -- is --game-dir a real KOTOR install?")
    gff = read_gff(src.data)
    root = gff.root
    root.set_string("Tag", BOX_RESREF)
    root.set_resref("TemplateResRef", ResRef(BOX_RESREF))
    root.set_resref("OnInvDisturbed", ResRef(HANDLER_RESREF))
    _set_locstring(root, "LocName", "Galactic Shop")
    # Start empty: the vanilla crate ships with 2 stocked items, and a
    # Galactic Shop box that "contained" free loot would be confusing.
    root.get_list("ItemList").clear()
    root.set_uint8("HasInventory", 1)
    root.set_uint8("Useable", 1)
    root.set_uint8("Static", 0)
    root.set_uint8("Plot", 1)  # can't be destroyed by area-of-effect damage in the cargo hold
    data = bytearray()
    write_gff(gff, data)
    with open(os.path.join(override_dir, f"{BOX_RESREF}.utp"), "wb") as f:
        f.write(bytes(data))
    print(f"  wrote Override/{BOX_RESREF}.utp")


def write_coin_template(installation: Installation, override_dir: str) -> None:
    src = installation.resource("g_i_asthitem001", ResourceType.UTI)
    if src is None:
        sys.exit("vanilla g_i_asthitem001.uti not found -- is --game-dir a real KOTOR install?")
    gff = read_gff(src.data)
    root = gff.root
    root.set_string("Tag", COIN_RESREF)
    root.set_resref("TemplateResRef", ResRef(COIN_RESREF))
    _set_locstring(root, "LocalizedName", "Galactic Coin")
    _set_locstring(root, "DescIdentified",
                   "A trade token from the Galactic Shop. Put an item into a shop box to receive one; "
                   "put a coin in to receive something another traveler left behind.")
    _set_locstring(root, "Description", "")
    root.set_uint8("Identified", 1)
    root.set_uint8("Plot", 0)
    root.set_uint32("Cost", 0)
    root.set_uint16("StackSize", 1)
    data = bytearray()
    write_gff(gff, data)
    with open(os.path.join(override_dir, f"{COIN_RESREF}.uti"), "wb") as f:
        f.write(bytes(data))
    print(f"  wrote Override/{COIN_RESREF}.uti")


def deploy_handler(override_dir: str) -> None:
    nss_path = os.path.join(SRC_DIR, f"{HANDLER_RESREF}.nss")
    ncs_path = os.path.join(SRC_DIR, f"{HANDLER_RESREF}.ncs")
    if os.path.exists(NWNNSSCOMP) and os.path.exists(nss_path):
        result = subprocess.run([NWNNSSCOMP, "-c", nss_path, "-o", ncs_path],
                                capture_output=True, text=True, cwd=SRC_DIR)
        if not os.path.exists(ncs_path):
            sys.exit(f"COMPILE FAILED for {HANDLER_RESREF}:\n{result.stdout}\n{result.stderr}")
        print(f"  compiled {HANDLER_RESREF}.nss")
    elif not os.path.exists(ncs_path):
        sys.exit(f"{ncs_path} missing and no nwnnsscomp.exe to build it")
    shutil.copy2(ncs_path, os.path.join(override_dir, f"{HANDLER_RESREF}.ncs"))
    print(f"  deployed Override/{HANDLER_RESREF}.ncs")


def patch_module(game_dir: str) -> None:
    mod_dir = os.path.join(game_dir, "modules")
    path = os.path.join(mod_dir, f"{MODULE}.rim")
    if not os.path.exists(path):
        sys.exit(f"{path} not found")

    os.makedirs(BACKUP_DIR, exist_ok=True)
    backup_path = os.path.join(BACKUP_DIR, f"{MODULE}.rim")
    spike_backup = path + ".apbackup"
    if not os.path.exists(backup_path) and os.path.exists(spike_backup):
        # A dev machine that carries an earlier hand-edit's own vanilla
        # backup (path + ".apbackup") should adopt that as THE backup
        # rather than snapshotting an already-modified RIM as "vanilla".
        shutil.copy2(spike_backup, backup_path)
        print(f"  adopted the earlier {MODULE}.rim.apbackup as the vanilla backup")

    # Vanilla resref for each of the 5 candidate positions comes from the
    # backup (falls back to "not backed up yet" below) -- resref alone
    # can't tell a still-vanilla crate apart from one an OLDER run of this
    # script (back when it boxed all 5) already retargeted.
    vanilla_resref_by_pos = {}
    if os.path.exists(backup_path):
        b = read_rim(backup_path)
        b_git_res = next((res for res in b if res.restype == ResourceType.GIT), None)
        if b_git_res is not None:
            b_git = construct_git(read_gff(b_git_res.data))
            for p in b_git.placeables:
                if str(p.resref).lower() in VANILLA_TARGETS:
                    vanilla_resref_by_pos[_pos_key(p)] = str(p.resref)

    r = read_rim(path)
    git_res = next((res for res in r if res.restype == ResourceType.GIT), None)
    if git_res is None:
        sys.exit(f"{MODULE}: no GIT resource")
    git = construct_git(read_gff(git_res.data))

    candidates = [p for p in git.placeables
                  if _pos_key(p) in vanilla_resref_by_pos or str(p.resref).lower() in VANILLA_TARGETS]
    if not candidates:
        print(f"  {MODULE}: no cargo-hold crates found at all -- nothing to do")
        return

    if not os.path.exists(backup_path):
        shutil.copy2(path, backup_path)
        print(f"  backed up vanilla {MODULE}.rim -> {backup_path}")
        for p in candidates:
            vanilla_resref_by_pos[_pos_key(p)] = str(p.resref)

    # Deterministic pick (lowest position tuple) so re-running this always
    # retargets the same physical crate.
    candidates.sort(key=_pos_key)
    chosen = candidates[0]

    changed = False
    for p in candidates:
        want = BOX_RESREF if p is chosen else vanilla_resref_by_pos.get(_pos_key(p), str(p.resref))
        if str(p.resref).lower() != want.lower():
            p.resref = ResRef(want)
            changed = True

    if not changed:
        print(f"  {MODULE}: already correct (1 shop box, {len(candidates) - 1} vanilla crate(s) untouched)")
        return

    new_git = bytearray()
    write_gff(dismantle_git(git), new_git)
    r.set_data(git_res.resref, ResourceType.GIT, bytes(new_git))
    write_rim(r, path)
    print(f"  {MODULE}: retargeted 1 of {len(candidates)} cargo-hold crates to {BOX_RESREF} "
          f"(the other {len(candidates) - 1} stay/return to their vanilla template)")


def restore(game_dir: str) -> None:
    mod_dir = os.path.join(game_dir, "modules")
    backup_path = os.path.join(BACKUP_DIR, f"{MODULE}.rim")
    if os.path.exists(backup_path):
        shutil.copy2(backup_path, os.path.join(mod_dir, f"{MODULE}.rim"))
        print(f"  restored vanilla {MODULE}.rim from backup")
    else:
        # No backup means this script never patched it -- but the module
        # may still carry an earlier hand edit. Check.
        path = os.path.join(mod_dir, f"{MODULE}.rim")
        if os.path.exists(path):
            git = construct_git(read_gff(next(res for res in read_rim(path) if res.restype == ResourceType.GIT).data))
            if any(str(p.resref).lower() == BOX_RESREF for p in git.placeables):
                spike_backup = path + ".apbackup"
                if os.path.exists(spike_backup):
                    shutil.copy2(spike_backup, path)
                    print(f"  restored vanilla {MODULE}.rim from the spike's .apbackup")
                else:
                    print(f"  WARNING: {MODULE}.rim still references {BOX_RESREF} and no backup exists to restore from")
    override_dir = os.path.join(game_dir, "Override")
    for fname in (f"{BOX_RESREF}.utp", f"{COIN_RESREF}.uti", f"{HANDLER_RESREF}.ncs"):
        p = os.path.join(override_dir, fname)
        if os.path.exists(p):
            os.remove(p)
            print(f"  removed Override/{fname}")
    print("Galactic Shop: vanilla restored.")


def main():
    game_dir = _arg_value("--game-dir", DEFAULT_GAME_DIR)
    if "--restore" in sys.argv:
        restore(game_dir)
        return
    if "--force" in sys.argv:
        enabled = "--on" in sys.argv
    else:
        enabled = _connected_galactic_shop()
        if enabled is None:
            print(f"No usable data at {SLOT_DATA_PATH} -- connect once with KotorClient.py first, "
                  "or pass --force --on/--off.")
            return
    if not enabled:
        restore(game_dir)
        return

    override_dir = os.path.join(game_dir, "Override")
    os.makedirs(override_dir, exist_ok=True)
    installation = Installation(game_dir)
    print("Galactic Shop: applying ...")
    write_box_template(installation, override_dir)
    write_coin_template(installation, override_dir)
    deploy_handler(override_dir)
    patch_module(game_dir)
    print(f"Galactic Shop: ON -- one {MODULE} cargo-hold crate is now the \"Galactic Shop\" box "
          f"(needs a real module transition, not a same-module reload, to show up).")


if __name__ == "__main__":
    main()
