r"""
Applies the door/trigger mapping AP's own entrance_rando engine computed
during world generation (see worlds/kotor/EntranceRando.py) to the real
game files -- rewriting each transition's LinkedToModule/LinkedTo GIT
fields to point at its shuffled destination instead of the vanilla one.

Reads the mapping out of extender/area_trampolines/_slot_data.json --
written by KotorClient.py on every successful Connect, straight from the
real slot_data the AP server sent THIS player for THEIR OWN slot (see
KotorClient.py's SLOT_DATA_PATH/write_slot_data_for_patch_scripts()).
You must connect once with KotorClient.py before running this (see
README.md Step 6). This works identically whether you're hosting or
joining someone else's multiworld -- neither needs local access to a
generated AP_<seed>.zip at all -- reading the zip directly would only
ever work on whichever machine ran Generate.py, since a joining player
never has it, and would need to filter for THIS player's own slot rather
than grabbing whichever slot's data happened to be read first in a
multiworld with more than one KOTOR player.

Shares the same backup directory as patch_item_suppression.py
(extender/backup/modules/) -- both scripts repack the same underlying
module RIM files, so a single shared backup/restore covers whichever of
the two (or both) have touched a given module. Use
patch_item_suppression.py --restore to undo either or both (its restore
loop is generic over every file in that directory, so the `_s.rim`
backups this script also makes -- see below -- are covered automatically,
no changes needed there).

Also force-unlocks every randomizable door's own vanilla lock state
(Locked/KeyRequired on its real UTD blueprint, which lives in the
module's `_s.rim`, NOT the per-instance GIT struct this script's own
LinkedToModule/LinkedTo edit touches -- confirmed by direct comparison
against LaneDibello/Kotor-Randomizer's own UnlockDoorInFile, credited in
this repo's README, which does the same UTD-blueprint edit for its own
curated door list). A shuffled door keeps whatever vanilla access gate it
had in its OLD context (a quest flag, a disguise, permission from an NPC)
even though it may now be the only way into or out of an area -- of the
116 real doors in door_graph.json, 24 outside the excluded story-critical
zones have Locked=1 or KeyRequired=1 on their blueprint in vanilla data.
Scoped to exactly the doors this project already tracks (door_graph.json),
not a blanket unlock of every door in the game.

Usage:
  python patch_door_randomizer.py                          -- apply (backs up first)
  python patch_door_randomizer.py --force                  -- skip the area_randomizer check, apply anyway
  python patch_door_randomizer.py --game-dir "D:\...\swkotor" -- apply against a non-default install

Needs pykotor only -- no NWScript compiler involved at all, this only
rewrites existing LinkedToModule/LinkedTo GFF fields, never generates or
compiles a script.
"""
import json
import os
import shutil
import sys

from pykotor.common.misc import ResRef
from pykotor.resource.formats.rim import read_rim, write_rim
from pykotor.resource.formats.gff import read_gff, write_gff
from pykotor.resource.type import ResourceType

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"


def _arg_value(flag, default):
    for i, a in enumerate(sys.argv):
        if a == flag and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
        if a.startswith(flag + "="):
            return a.split("=", 1)[1]
    return default


GAME_DIR = _arg_value("--game-dir", DEFAULT_GAME_DIR)
MOD_DIR = os.path.join(GAME_DIR, "modules")
BACKUP_DIR = os.path.join(REPO_ROOT, "extender", "backup", "modules")
# Same path patch_item_suppression.py reads -- see its own copy of this
# constant/comment for the full reasoning.
SLOT_DATA_PATH = os.path.join(REPO_ROOT, "extender", "area_trampolines", "_slot_data.json")


def _connected_door_mapping():
    """Returns the door_mapping dict from _slot_data.json, or None if that
    file doesn't exist yet (never connected), area_randomizer wasn't
    actually on for this seed, or the file doesn't parse."""
    if not os.path.isfile(SLOT_DATA_PATH):
        return None
    try:
        with open(SLOT_DATA_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("door_mapping") or None
    except Exception as e:
        print(f"  (couldn't read {SLOT_DATA_PATH}: {e})")
        return None


def main():
    mapping = _connected_door_mapping()
    if mapping is None:
        if "--force" not in sys.argv:
            print(f"No usable door_mapping at {SLOT_DATA_PATH} -- connect once with KotorClient.py "
                  "first (see README.md Step 6), which writes your seed's real door_mapping there on "
                  "every successful Connect (only present at all if area_randomizer is actually on for "
                  "your seed). Pass --force to bypass this check if you believe that's wrong.")
        else:
            print("--force given but no usable door_mapping could be read at all -- nothing to apply.")
        return
    print("Connected seed has a real door_mapping -- applying.")

    # Group by module so each module's RIM is only opened/backed-up/written once.
    by_module: dict = {}
    for key, dest in mapping.items():
        module, list_name, index_str = key.split(":", 2)
        by_module.setdefault(module, []).append((list_name, int(index_str), dest))

    os.makedirs(BACKUP_DIR, exist_ok=True)
    changed = 0
    unchanged_modules = 0
    doors_unlocked = 0

    for module, entries in sorted(by_module.items()):
        path = os.path.join(MOD_DIR, f"{module}.rim")
        if not os.path.exists(path):
            print(f"  {module}: RIM not found, skipping")
            continue
        try:
            r = read_rim(path)
        except Exception as e:
            print(f"  {module}: could not read RIM ({e}), skipping")
            continue

        git_res = None
        for res in r:
            if res.restype == ResourceType.GIT:
                git_res = res
                break
        if git_res is None:
            print(f"  {module}: no GIT resource, skipping")
            continue

        gff = read_gff(git_res.data)
        any_real_change = False
        door_templates = set()
        for list_name, index, dest in entries:
            lst = gff.root.get_list(list_name)
            inst = lst.at(index)
            if list_name == "Door List" and inst.exists("TemplateResRef"):
                door_templates.add(inst.get_resref("TemplateResRef").get())
            current_module = inst.get_resref("LinkedToModule").get() if inst.exists("LinkedToModule") else ""
            current_waypoint = inst.get_string("LinkedTo") if inst.exists("LinkedTo") else ""
            if current_module.lower() == dest["dest_module"].lower() and current_waypoint == dest["dest_waypoint"]:
                continue  # already vanilla-matching (the graceful-fallback entries) -- no write needed
            inst.set_resref("LinkedToModule", ResRef(dest["dest_module"]))
            inst.set_string("LinkedTo", dest["dest_waypoint"])
            any_real_change = True

        if any_real_change:
            backup_path = os.path.join(BACKUP_DIR, f"{module}.rim")
            if not os.path.exists(backup_path):
                shutil.copy2(path, backup_path)

            new_git_data = bytearray()
            write_gff(gff, new_git_data)
            r.set_data(git_res.resref, ResourceType.GIT, bytes(new_git_data))
            write_rim(r, path)
            changed += 1
            print(f"  {module}: patched {len(entries)} transition(s)")
        else:
            unchanged_modules += 1

        doors_unlocked += _unlock_door_templates(module, door_templates)

    doors_unlocked += _unlock_known_local_doors()

    print(f"\nDone. modules patched: {changed}, modules with no real change: {unchanged_modules}, "
          f"doors unlocked: {doors_unlocked}")


def _unlock_door_templates(module: str, templates: set) -> int:
    """Force-unlocks (Locked=0, KeyRequired=0, OpenLockDC=0) every UTD
    blueprint named in `templates` that this module's own `_s.rim` carries
    and that is actually locked/key-gated in vanilla data -- see this
    file's own module docstring for why the lock lives here, not in the
    GIT instance the LinkedToModule/LinkedTo edit above touches. Runs
    unconditionally for every door this project tracks in this module,
    not just ones whose own destination changed this seed -- a door kept
    at its vanilla destination can still be the only way BACK from some
    other, newly-shuffled connection, so its lock state matters regardless
    of whether it personally got reassigned. No-ops (returns 0) if none of
    the given templates are actually locked -- never writes a file it
    didn't need to touch. Returns how many doors were changed."""
    if not templates:
        return 0
    s_path = os.path.join(MOD_DIR, f"{module}_s.rim")
    if not os.path.exists(s_path):
        return 0
    try:
        rs = read_rim(s_path)
    except Exception as e:
        print(f"  {module}_s.rim: could not read ({e}), skipping door-unlock pass")
        return 0

    unlocked = 0
    any_change = False
    wanted = {t.lower() for t in templates}
    for res in rs:
        if res.restype != ResourceType.UTD or res.resref.get().lower() not in wanted:
            continue
        if _clear_utd_lock_fields(rs, res, module):
            unlocked += 1
            any_change = True

    if not any_change:
        return 0

    backup_path = os.path.join(BACKUP_DIR, f"{module}_s.rim")
    if not os.path.exists(backup_path):
        shutil.copy2(s_path, backup_path)
    write_rim(rs, s_path)
    print(f"  {module}_s.rim: unlocked {unlocked} door(s)")
    return unlocked


# (module, TemplateResRef) pairs whose door uses its "Conversation" field
# as a HARD, zero-reply, unconditional denial instead of (or in addition
# to) Locked/KeyRequired -- clicking the door always plays one line (e.g.
# "This door has been permanently sealed.", "Private Sith docking bay.
# Security clearance required.", "Non-family members are not permitted
# entrance.") and ends the conversation, never opening the door, no matter
# what Locked/KeyRequired/Plot say. Confirmed by directly reading each
# door's own DLG (EntryList[0] text + reply count == 0) rather than
# assumed from the field being merely present -- one door with a
# Conversation field (tar02_doordlg, "choose your party members before
# leaving") is a normal non-blocking prompt and is deliberately NOT in
# this list. Clearing the door's own Conversation field (not the shared
# DLG resource, which may not be exclusive to this door) reverts it to
# plain Locked/KeyRequired-governed interaction.
DOORS_NEEDING_CONVERSATION_CLEARED = {
    ("danm14aa", "man14aa_door04"),
    ("danm14ad", "dan14ad_door01"),
    ("danm14ad", "dan14ad_door02"),
    ("korr_m33ab", "k33b_dor_academy"),
    ("korr_m39aa", "kor39_kor36"),
    ("manm26ad", "man26ad_door02"),
    ("manm26ae", "man26ac_door03"),
    ("manm26ae", "man26ac_door05"),
    ("tar_m03aa", "tar03_blkdoor"),
}


def _clear_utd_lock_fields(rs, res, module: str) -> bool:
    """Zeroes Locked/KeyRequired/OpenLockDC/Plot on one UTD blueprint
    already located inside an open RIM object (`rs`), writing the change
    back into `rs` in memory (caller still owns backup/write-to-disk).
    Also clears `Conversation` when this exact (module, template) is in
    DOORS_NEEDING_CONVERSATION_CLEARED -- see that set's own comment for
    why a data-only lock fix doesn't work for those doors. Returns False
    (no-op, nothing written) if neither applies -- never touches a door
    that wasn't actually gated. Plot is cleared alongside Locked/
    KeyRequired (not just a lock check) to match LaneDibello/Kotor-
    Randomizer's own UnlockDoorInFile, which clears all three together for
    its curated door list -- confirmed some of our own tracked doors are
    gated via Plot=1 alone (no Locked/KeyRequired at all), e.g. two
    Korriban Valley entries."""
    template = res.resref.get()
    needs_conv_clear = (module.lower(), template.lower()) in DOORS_NEEDING_CONVERSATION_CLEARED
    utd = read_gff(res.data)
    locked = utd.root.get_uint8("Locked") if utd.root.exists("Locked") else 0
    keyreq = utd.root.get_uint8("KeyRequired") if utd.root.exists("KeyRequired") else 0
    plot = utd.root.get_uint8("Plot") if utd.root.exists("Plot") else 0
    conv = utd.root.get_resref("Conversation").get() if utd.root.exists("Conversation") else ""
    if not locked and not keyreq and not plot and not (needs_conv_clear and conv):
        return False
    utd.root.set_uint8("Locked", 0)
    utd.root.set_uint8("KeyRequired", 0)
    utd.root.set_uint8("Plot", 0)
    if utd.root.exists("OpenLockDC"):
        utd.root.set_uint8("OpenLockDC", 0)
    if needs_conv_clear and conv:
        utd.root.set_resref("Conversation", ResRef.from_blank())
    new_data = bytearray()
    write_gff(utd, new_data)
    rs.set_data(res.resref, ResourceType.UTD, bytes(new_data))
    return True


# Doors that gate progression WITHIN a single module (LinkedToModule=="",
# a plain interior door -- not one of door_graph.json's 156 cross-module
# transitions at all, so the pass above never sees them) but that vanilla
# story order still expects to be locked until a specific quest beat.
# Area randomization can route a player into these areas before that beat,
# with no other way past. Sourced directly from LaneDibello/Kotor-
# Randomizer's own curated unlock list (credited in this repo's README),
# trimmed to the modules our own shuffle pool can actually route through
# (their Leviathan/Star Forge/Unknown World entries are dropped -- those
# planets are excluded from our pool entirely, see EntranceRando.py's
# EXCLUDED_BOTH_WAYS_PREFIXES, so nothing ever routes a player there early).
KNOWN_LOCAL_LOCKED_DOORS = [
    ("manm26ae", "man26ac_door03"),  # Manaan Ahto East -- door into the Republic Embassy
    ("manm26ae", "man26ac_door05"),  # Manaan Ahto East -- door to the submersible
    ("manm26ad", "man26ad_door02"),  # Manaan docking bay -- door into the Sith hangar
    ("tar_m03aa", "tar03_underdoor"),  # Taris Lower City -- door down to the Undercity
]


def _unlock_known_local_doors() -> int:
    by_module: dict = {}
    for module, label in KNOWN_LOCAL_LOCKED_DOORS:
        by_module.setdefault(module, []).append(label)

    unlocked = 0
    for module, labels in sorted(by_module.items()):
        s_path = os.path.join(MOD_DIR, f"{module}_s.rim")
        if not os.path.exists(s_path):
            continue
        try:
            rs = read_rim(s_path)
        except Exception as e:
            print(f"  {module}_s.rim: could not read ({e}), skipping known-local-door pass")
            continue

        wanted = {l.lower() for l in labels}
        module_unlocked = 0
        for res in rs:
            if res.restype != ResourceType.UTD or res.resref.get().lower() not in wanted:
                continue
            if _clear_utd_lock_fields(rs, res, module):
                module_unlocked += 1

        if not module_unlocked:
            continue
        backup_path = os.path.join(BACKUP_DIR, f"{module}_s.rim")
        if not os.path.exists(backup_path):
            shutil.copy2(s_path, backup_path)
        write_rim(rs, s_path)
        print(f"  {module}_s.rim: unlocked {module_unlocked} known local door(s)")
        unlocked += module_unlocked

    return unlocked


if __name__ == "__main__":
    main()
