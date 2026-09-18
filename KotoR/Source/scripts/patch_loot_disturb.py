r"""
Loot Mode (destroy/bonus/replace), implemented as pure STATIC template
data edits applied before the game ever loads -- same technique already
proven for the Galactic Coin item injection and the Additional Enemies
bounty-card creature clones (patch_additional_enemies.py's
_clone_bounty_carrier). No runtime script, no script-hook field of any
kind, and therefore none of the process-level caching gotchas that
plagued every earlier design of this feature.

REPLACES TWO EARLIER DESIGNS, in order:
1. Mod_OnAcquirItem (patch_item_suppression.py's original mechanism) --
   retired because it re-fires for already-held items, forcing held-
   quantity-delta guards and purchase-detection heuristics. EXPLICITLY
   RULED OUT for reuse here too -- do not reintroduce it for any reason.
2. OnInvDisturbed(REMOVED)/ScriptDisturbed(REMOVED) (this file's own
   earlier design) -- structurally sound for PLACEABLES
   (a real backpack001 container correctly fired and
   destroyed a suppressed item) but a real dead end for CREATURE corpse
   loot: confirmed via kse.log that ScriptDisturbed never fires at
   all when a player loots a dead creature's body (looting a grenade off
   end_repsol007/end_repsol009 produced ZERO log output, not even the
   background type=ADDED noise every other object generates constantly).
   ScriptDisturbed on a UTC appears to only observe that creature's
   inventory while it's ALIVE (equipment swaps, AI churn), not the
   loot-window transfer after death -- and since most of this game's real
   loot comes from killing enemies and looting the body, that gap was
   fatal to the whole approach for creatures. Also would have needed a
   full exit-to-desktop relaunch after every seed/mode change (the
   confirmed per-process script-hook-eligibility cache), which the new
   design below has no need of at all.

WHY STATIC EDITING WORKS FOR ALL THREE MODES:; CreateItemOnObject at a
creature's OnDeath already proven (bounty cards) to land in the SAME
object the player then loots -- i.e. this engine keeps the dying creature
as the one lootable object, it never swaps in a separate bodybag
placeable. A creature/placeable template's ItemList is just GFF data, no
different in kind from any other field this project already edits
directly (on_inventory/on_disturbed used to be one of those fields; now
none of that machinery is needed for loot at all). Editing it once at
patch time and depositing the result as a global Override file (exactly
like every earlier field edit in this project) means the modified loot is
just... there, the moment that template's module loads -- same as any
other vanilla placement, no event, no cache, no relaunch.

  - destroy: delete every non-whitelisted ItemList entry from every
    loot-bearing template.
  - replace: same scan, but swap each non-whitelisted entry for a
    seed-deterministic random pick from the loot pool instead of deleting
    it.
  - bonus: leave all original items untouched; add ONE extra
    seed-deterministic random loot-pool item to every template that has
    at least one item already. (This fires much more often than the old
    per-5-real-pickups milestone design -- simplicity is favored over
    matching the exact old cadence.)

Progression System's Sith Armor/Shield Codes (the 2 items whose real
acquisition is a corpse/container, not dialogue -- see
DEVELOPMENT_HISTORY.md's "researching the Progression System's
checkpoint wrappers" section) are handled the same way now: an
unconditional removal
from any template carrying them, independent of loot_mode, whenever
progression_system is on. Sith Papers/Enviro Suit/the 4 Star Maps remain
entirely on patch_item_suppression.py's separate
apply_progression_checkpoint_wrappers() mechanism (dialogue/module-
transition gated, not inventory-based) -- untouched by this file.

granted_exempt_ bookkeeping (needed by the old runtime designs to protect
an AP-granted item from being immediately re-suppressed) is GONE, not
needed: this file only ever touches WORLD-PLACED template data, never
anything delivered through the AP item pipeline, so there is no overlap
to guard against any more.

Idempotent by construction: every run re-derives each template's final
state from the PRISTINE source (chitin first, then every module *.rim
including each module's own _s.rim companion -- confirmed this session
that some real loot, e.g. end_m01aa's rsldcrps002 corpse, lives only in
the _s.rim, not the main .rim), never from a previously-deployed Override
copy of its own. A manifest (_loot_static_manifest.json) tracks exactly
which Override files THIS script has deployed, so `--restore` and a
mode/seed switch both know precisely what to remove, without guessing at
another feature's legitimate Override content (ap_voidbox, Bounty Card
creature clones, etc.) by name collision.

Usage:
  python patch_loot_disturb.py                          -- apply (uses real seed slot_data)
  python patch_loot_disturb.py --game-dir "D:\...\swkotor" -- apply against a non-default install
  python patch_loot_disturb.py --force --mode=<destroy|bonus|replace|skip> [--progression-system] -- manually-chosen mode
  python patch_loot_disturb.py --restore                -- undo everything this script has deployed

Same SLOT_DATA_PATH / gear_items.json loading conventions as
patch_item_suppression.py.
"""
import json
import os
import random
import sys

from pykotor.common.misc import InventoryItem, ResRef
from pykotor.extract.installation import Installation
from pykotor.extract.capsule import Capsule
from pykotor.resource.formats.gff import read_gff, write_gff
from pykotor.resource.formats.rim import read_rim, write_rim
from pykotor.resource.generics.utp import construct_utp, dismantle_utp
from pykotor.resource.generics.utc import construct_utc, dismantle_utc
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
MOD_DIR = os.path.join(GAME_DIR, "Modules")
OVERRIDE = os.path.join(GAME_DIR, "Override")
SLOT_DATA_PATH = os.path.join(REPO_ROOT, "extender", "area_trampolines", "_slot_data.json")
MANIFEST_PATH = os.path.join(REPO_ROOT, "extender", "area_trampolines", "_loot_static_manifest.json")
# Separate from MANIFEST_PATH (Override files) -- tracks exactly which
# module .rim filenames apply_module_rim_contents() has itself modified,
# so --restore reverts precisely those from the SHARED backup dir without
# also undoing door_randomizer's/additional_enemies' own independent
# edits to the same physical file (they share LOCKER_BACKUP_DIR, but each
# script's restore should only touch what IT modified).
MODULE_MANIFEST_PATH = os.path.join(REPO_ROOT, "extender", "area_trampolines", "_loot_static_module_manifest.json")
# Shared backup dir with patch_additional_enemies.py/patch_door_randomizer.py
# -- no filename collision, since those back up modules' main .rim while
# this backs up end_m01aa's _s.rim companion specifically.
LOCKER_BACKUP_DIR = os.path.join(REPO_ROOT, "extender", "backup", "modules")

# Same two-location fallback as patch_item_suppression.py's own GEAR_JSON.
GEAR_JSON = os.path.join(REPO_ROOT, "scripts", "gear_items.json")
if not os.path.isfile(GEAR_JSON):
    GEAR_JSON = os.path.join(REPO_ROOT, "Archipelago", "worlds", "kotor", "gear_items.json")

# Never touch this template's item list anywhere in the game, even
# though it qualifies as "has inventory": this project's OWN Galactic
# Shop container -- its contents ARE the shop's live economy, not world
# loot. Safe to exclude by bare name globally since this exact resref is
# never reused by BioWare content (it's this project's own creation).
PLACEABLE_EXCLUDE = {"ap_voidbox"}

# (module .rim filename, resref) pairs to exclude -- for names that DO
# need protecting, but ONLY in one specific module, since the same bare
# name is reused by BioWare elsewhere with genuinely different (and
# normally-suppressible) contents. A bare-name-only exclusion here would
# be WRONG, not just imprecise: excluding
# "footlker001" by name alone also silently exempted end_m01ab's own
# entirely different, ordinary footlker001 (adhesive grenade/quarterstaff/
# etc.) from suppression, since PLACEABLE_EXCLUDE used to be checked with
# no module context at all inside apply_module_rim_contents().
#   - (end_m01aa_s.rim, footlker001): the Endar Spire's MANDATORY
#     starting-gear footlocker. A real softlock: destroy
#     mode correctly-per-its-own-rules stripped it down to zero items
#     (its only weapon, a Short Sword, plus starting medkits/clothing),
#     leaving the player with no weapon and no way to proceed past the
#     opening corridor. ONLY this one locker needs
#     protecting -- not footlker003 (the next one along, end_m01aa's
#     OWN copy), which is ordinary loot and suppresses normally like any
#     other module-embedded container via apply_module_rim_contents().
PLACEABLE_EXCLUDE_SCOPED = {("end_m01aa_s.rim", "footlker001")}

_LOOT_MODE_NAMES = {0: "skip", 1: "destroy", 2: "bonus", 3: "replace"}


def load_gear_whitelist():
    with open(GEAR_JSON, encoding="utf-8") as f:
        gear = json.load(f)
    suppress_resrefs = {r.lower() for r, v in gear.items() if not v.get("quest_dependent")}
    loot_pool = sorted(r for r, v in gear.items() if v.get("shop_randomize"))
    progression_resrefs = {r.lower() for r, v in gear.items() if v.get("progression_suppression") == "1"}
    return suppress_resrefs, loot_pool, progression_resrefs


def resolve_mode_and_progression(force_mode=None, force_progression=None):
    if force_mode is not None:
        return force_mode, bool(force_progression)
    if not os.path.exists(SLOT_DATA_PATH):
        print(f"No slot data at {SLOT_DATA_PATH} and no --force --mode= given -- nothing to do.")
        sys.exit(1)
    with open(SLOT_DATA_PATH) as f:
        slot_data = json.load(f)
    loot_mode_val = slot_data.get("loot_mode", 0)
    mode = _LOOT_MODE_NAMES.get(loot_mode_val, "skip")
    progression_system = bool(slot_data.get("progression_system", False))
    seed_name = str(slot_data.get("seed_name", "no-seed"))
    print(f"Connected seed resolves to loot_mode={loot_mode_val} -> mode={mode!r}, progression_system={progression_system}")
    return mode, progression_system, seed_name


def discover_chitin_templates(inst, restype):
    """CHITIN ONLY -- these are the genuinely, singularly global templates
    (one canonical definition, shared identically by reference wherever a
    module doesn't embed its own local copy), so a single Override file
    is safe for them: no per-module divergence is possible.

    Used to ALSO scan every module RIM here (first-name-wins), but that
    was a REAL BUG: BioWare reused simple
    sequential resrefs (footlker001, backpack001, metalbox001, ...)
    independently PER MODULE, each with its own distinct contents -- 58
    such names were confirmed colliding across the game. A name-keyed
    global dict can only ever remember ONE module's version, and
    deploying that as a global Override file silently overwrote every
    OTHER module's same-named placement with the wrong module's decision
    -- e.g. the Endar Spire's mandatory starting-gear locker
    (footlker001) getting its suppression decision computed from
    Dantooine's completely different footlker001 instance. Module-
    embedded templates are now handled entirely separately, per-module,
    by apply_module_rim_contents() below -- never through this function
    or Override at all.

    res.data() reads directly from the BIF/chitin source -- NOT
    inst.resource(name, restype), which resolves through the override-
    aware precedence chain (Override > Modules > chitin) and would
    silently read back THIS SCRIPT'S OWN prior Override output on a
    second run, compounding instead of recomputing from pristine data
    every time (a separate real bug also caught live this session)."""
    templates = {}
    for res in inst.chitin_resources():
        if res.restype() == restype:
            name = res.resname()
            if name not in templates:
                templates[name] = res.data()
    return templates


def _process_inventory(items, mode, suppress_resrefs, loot_pool, progression_resrefs, rng):
    """Shared decision logic for both placeables and creatures -- returns
    (new_items, changed). Progression's unconditional strip runs first,
    independent of mode; destroy/replace/bonus then apply per `mode`."""
    changed = False
    kept = []
    for item in items:
        tag = str(item.resref).lower()
        if progression_resrefs and tag in progression_resrefs:
            changed = True
            continue  # always dropped, regardless of loot_mode
        if mode == "destroy" and tag in suppress_resrefs:
            changed = True
            continue
        if mode == "replace" and tag in suppress_resrefs:
            new_resref = rng.choice(loot_pool)
            kept.append(InventoryItem(ResRef(new_resref), item.droppable, item.infinite))
            changed = True
            continue
        kept.append(item)

    if mode == "bonus" and kept:
        kept.append(InventoryItem(ResRef(rng.choice(loot_pool)), True, False))
        changed = True

    return kept, changed


def _process_equipment(equipment, mode, suppress_resrefs, progression_resrefs):
    """Creature-only counterpart to _process_inventory, for equipped gear
    (Equip_ItemList/utc.equipment) instead of carried inventory (ItemList/
    utc.inventory) -- a completely separate GFF field this file must
    also process, or a real gap remains (a Sith
    trooper's equipped vibrosword/blaster survives destroy mode untouched
    since it was never carried inventory to begin with). Found via a
    project-wide scan: 192 of 205 chitin creature templates share ONE
    generic OnDeath script (k_def_death01, itself just a thin dispatcher
    into k_ai_master) -- ruling out per-creature OnDeath loot scripting as
    the culprit and pointing straight at this separate static field
    instead, which is a real, fixable gap, not a runtime/script blind spot
    like the OnHeartbeat-driven civilian-treasure containers.

    Deliberately does NOT remove or swap the equipped item itself, unlike
    inventory handling -- that would visibly change the creature's
    appearance and combat animations (e.g. fighting bare-handed instead of
    with their real weapon). Instead flips `droppable` to False, the exact
    flag that governs whether the item appears in the post-death loot
    window at all -- the creature still looks and fights exactly like
    vanilla, it just can't be looted afterward. destroy and replace get
    IDENTICAL treatment here (both just suppress dropability) -- replace's
    normal per-slot random substitution isn't safe for equipment, since
    `loot_pool` mixes weapons/armor/medpacs/etc. with no slot-type
    filtering, and a Medpac resref in a Weapon slot is invalid. bonus mode
    never touches equipment at all, matching its own existing behavior of
    only ever adding loot, never altering what's already there."""
    changed = False
    for item in equipment.values():
        if not item.droppable:
            continue  # already non-lootable, nothing to do
        tag = str(item.resref).lower()
        if progression_resrefs and tag in progression_resrefs:
            item.droppable = False
            changed = True
            continue
        if mode in ("destroy", "replace") and tag in suppress_resrefs:
            item.droppable = False
            changed = True
    return changed


def apply_placeables(inst, mode, suppress_resrefs, loot_pool, progression_resrefs, rng):
    """CHITIN-sourced placeables only now -- see discover_chitin_templates()'s
    docstring for why module-embedded ones are handled separately."""
    templates = discover_chitin_templates(inst, ResourceType.UTP)
    deployed = []
    for name in sorted(templates):
        if name in PLACEABLE_EXCLUDE:
            continue
        try:
            utp = construct_utp(read_gff(templates[name]))
        except Exception:
            continue
        if not utp.inventory:
            continue
        new_items, changed = _process_inventory(
            utp.inventory, mode, suppress_resrefs, loot_pool, progression_resrefs, rng)
        if not changed:
            continue
        utp.inventory = new_items
        write_gff(dismantle_utp(utp), os.path.join(OVERRIDE, f"{name}.utp"))
        deployed.append({"name": name, "type": "utp"})
    print(f"placeables (chitin-shared): {len(deployed)} template(s) rewritten")
    return deployed


def apply_creatures(inst, mode, suppress_resrefs, loot_pool, progression_resrefs, rng):
    """CHITIN-sourced creatures only now -- see discover_chitin_templates()'s
    docstring for why module-embedded ones are handled separately.

    Processes BOTH utc.inventory (carried items) and utc.equipment
    (equipped weapon/armor, see _process_equipment's own docstring for why
    this was a real gap) -- deliberately does NOT early-continue on an
    empty inventory alone: plenty of real
    enemies (most Sith troopers among them) carry nothing but an equipped
    weapon and zero inventory items, and used to be skipped entirely
    before this fix, never getting their equipment checked at all."""
    templates = discover_chitin_templates(inst, ResourceType.UTC)
    deployed = []
    for name in sorted(templates):
        try:
            utc = construct_utc(read_gff(templates[name]))
        except Exception:
            continue
        if not utc.inventory and not utc.equipment:
            continue
        changed = False
        if utc.inventory:
            new_items, inv_changed = _process_inventory(
                utc.inventory, mode, suppress_resrefs, loot_pool, progression_resrefs, rng)
            if inv_changed:
                utc.inventory = new_items
                changed = True
        if utc.equipment:
            if _process_equipment(utc.equipment, mode, suppress_resrefs, progression_resrefs):
                changed = True
        if not changed:
            continue
        write_gff(dismantle_utc(utc), os.path.join(OVERRIDE, f"{name}.utc"))
        deployed.append({"name": name, "type": "utc"})
    print(f"creatures (chitin-shared): {len(deployed)} template(s) rewritten")
    return deployed


def apply_module_rim_contents(game_dir, mode, suppress_resrefs, loot_pool, progression_resrefs, rng):
    """Handles every MODULE-EMBEDDED loot-bearing UTP/UTC directly, in
    place, in its own module's .rim file -- never via Override. This is
    what makes cross-module resref collisions a non-issue at all: each
    module's own placement is read from and written back to that exact
    module's own file, so it's impossible for one module's decision to
    leak into another's, regardless of whether they happen to share a
    bare resref name (58 confirmed real cases, e.g. footlker001/
    backpack001/metalbox001 reused independently per module by BioWare).
    Same technique already proven by patch_additional_enemies.py/
    patch_door_randomizer.py for RIM-level edits.

    Backs up each .rim file to the SHARED backup dir (same one
    patch_additional_enemies.py uses) before its first edit -- safe to
    share: every writer here uses the same "only copy if not already
    backed up" rule, so whichever script touches a file first preserves
    the true original for everyone. Tracks exactly which filenames THIS
    script has ever modified in its own manifest (separate from the
    shared backup dir) so --restore only reverts loot_disturb's own
    changes, not another feature's.

    Reads from the BACKUP copy when one already exists, not the live
    file -- otherwise a second run (reconnect, mode switch) would read
    back its OWN previous run's already-modified item list as if it were
    pristine, compounding (replace mode replacing an already-replaced
    item again, bonus mode stacking a second bonus item on top of the
    first, etc.) -- the exact same class of bug already caught once this
    session in the chitin-discovery path."""
    modified_files = []
    for fname in sorted(os.listdir(MOD_DIR)):
        if not fname.lower().endswith(".rim"):
            continue
        live_path = os.path.join(MOD_DIR, fname)
        backup_path = os.path.join(LOCKER_BACKUP_DIR, fname)
        source_path = backup_path if os.path.exists(backup_path) else live_path
        try:
            r = read_rim(source_path)
        except Exception:
            continue

        file_changed = False
        for res in r:
            if res.restype == ResourceType.UTP:
                res_name = res.resref.get()
                if res_name in PLACEABLE_EXCLUDE or (fname, res_name) in PLACEABLE_EXCLUDE_SCOPED:
                    continue
                ctor, dismantle, is_creature = construct_utp, dismantle_utp, False
            elif res.restype == ResourceType.UTC:
                ctor, dismantle, is_creature = construct_utc, dismantle_utc, True
            else:
                continue

            try:
                obj = ctor(read_gff(res.data))
            except Exception:
                continue
            # Equipped gear (utc.equipment, e.g. a Sith trooper's carried
            # vibrosword/blaster) is a separate GFF field from ItemList --
            # see _process_equipment's docstring for why this was a real
            # gap and why it's handled as a
            # dropable-flag flip, not removed/swapped like inventory.
            # UTP placeables have no equipment slots at all, so this only
            # ever applies on the UTC branch.
            has_equipment = is_creature and bool(getattr(obj, "equipment", None))
            if not obj.inventory and not has_equipment:
                continue
            changed = False
            if obj.inventory:
                new_items, inv_changed = _process_inventory(
                    obj.inventory, mode, suppress_resrefs, loot_pool, progression_resrefs, rng)
                if inv_changed:
                    obj.inventory = new_items
                    changed = True
            if has_equipment:
                if _process_equipment(obj.equipment, mode, suppress_resrefs, progression_resrefs):
                    changed = True
            if not changed:
                continue
            new_data = bytearray()
            write_gff(dismantle(obj), new_data)
            r.set_data(res.resref, res.restype, bytes(new_data))
            file_changed = True

        if file_changed:
            if not os.path.exists(backup_path):
                import shutil
                os.makedirs(LOCKER_BACKUP_DIR, exist_ok=True)
                shutil.copy2(live_path, backup_path)
            write_rim(r, live_path)
            modified_files.append(fname)

    print(f"module-embedded placeables/creatures: {len(modified_files)} module file(s) rewritten in place")
    return modified_files


# The canonical starting kit for footlker001 under any active loot_mode
# (destroy/bonus/replace) -- confirmed against the TRUE vanilla
# backup that the real vanilla contents there are actually
# ['g_i_medeqpmnt01', 'g_i_medeqpmnt01', 'g_a_clothes01', 'g_w_shortswrd01']
# (2x Medpac, Clothing, Short Sword) -- no pistol at all, and an extra
# medpac beyond the intended 3-item {clothing, pistol, blade} loadout.
# Trimmed to exactly clothing + blade (dropping the
# extra medpac) and ADD a blaster pistol (g_w_blstrpstl001 -- the same
# resref real vanilla puts in the SEPARATE backpack001 container in this
# same room, which gets suppressed like any other ordinary loot under
# destroy mode and isn't specially protected) plus 10x Computer Spikes
# (Computer Use is the other skill, alongside Security, whose checks
# consume a physical item to attempt at all -- same "cheap insurance"
# reasoning as the retired Loot Safety Net's own Computer Spikes entry).
STARTING_LOCKER_KIT = (
    ["g_a_clothes01", "g_w_blstrpstl001", "g_w_shortswrd01"]
    + ["g_i_progspike01"] * 10
)


def ensure_starting_locker_gear(game_dir, mode):
    """Sets the Endar Spire's real starting locker (footlker001,
    end_m01aa_s.rim) to EXACTLY STARTING_LOCKER_KIT whenever loot_mode is
    active (destroy/bonus/replace) -- a full replace, not additive on top
    of vanilla, since real vanilla contents there include an extra item
    (see STARTING_LOCKER_KIT's own comment) that gets trimmed.
    Restores true vanilla contents instead when mode == "skip" (loot_mode
    off) -- this fix is explicitly NOT meant to apply then. Replaces the
    retired "Loot Safety Net" AP-item precollection (see Items.py/
    __init__.py's removal notes) with a permanent, seed-independent
    world-content fix instead.

    MUST edit end_m01aa_s.rim directly, NOT deploy an Override file --
    "footlker001" is one of the 58 real name collisions confirmed
    (BioWare reused this exact resref, with DIFFERENT contents, across 22
    other modules). An Override file would silently overwrite every one of
    those, not just the Endar Spire's copy.

    Idempotent: compares current contents against the target before
    writing, so a reconnect with an unchanged mode is a no-op."""
    path = os.path.join(game_dir, "modules", "end_m01aa_s.rim")
    if not os.path.exists(path):
        print("  end_m01aa_s.rim not found -- skipping starting-locker gear fix")
        return

    os.makedirs(LOCKER_BACKUP_DIR, exist_ok=True)
    backup_path = os.path.join(LOCKER_BACKUP_DIR, "end_m01aa_s.rim")
    if not os.path.exists(backup_path):
        import shutil
        shutil.copy2(path, backup_path)

    r = read_rim(path)
    utp_res = next((res for res in r if res.restype == ResourceType.UTP and res.resref.get() == "footlker001"), None)
    if utp_res is None:
        print("  footlker001 not found in end_m01aa_s.rim -- skipping starting-locker gear fix")
        return

    utp = construct_utp(read_gff(utp_res.data))
    current = [str(i.resref).lower() for i in utp.inventory]

    if mode == "skip":
        # Restore TRUE vanilla from the backup (never touched by this
        # function's own edits) -- "off" means no interference at all.
        backup_utp_res = next((res for res in read_rim(backup_path)
                                if res.restype == ResourceType.UTP and res.resref.get() == "footlker001"), None)
        vanilla_utp = construct_utp(read_gff(backup_utp_res.data))
        target = [str(i.resref).lower() for i in vanilla_utp.inventory]
        target_items = vanilla_utp.inventory
    else:
        target = [r.lower() for r in STARTING_LOCKER_KIT]
        target_items = [InventoryItem(ResRef(res), True, False) for res in STARTING_LOCKER_KIT]

    if current == target:
        return  # already matches, nothing to do

    utp.inventory = target_items
    new_data = bytearray()
    write_gff(dismantle_utp(utp), new_data)
    r.set_data(utp_res.resref, ResourceType.UTP, bytes(new_data))
    write_rim(r, path)
    label = "true vanilla" if mode == "skip" else "clothing+pistol+blade+10x Computer Spikes"
    print(f"  footlker001 (end_m01aa_s.rim) set to {label}")


def restore():
    """Deletes exactly the Override files this script has deployed (per
    MANIFEST_PATH) and reverts exactly the module .rim files it has
    directly edited (per MODULE_MANIFEST_PATH) from the shared backup --
    never guesses at another feature's legitimate content by name or
    file, and never touches a module file this script itself never
    modified even if that file is also backed up (shared with door_
    randomizer/additional_enemies)."""
    removed = 0
    if os.path.exists(MANIFEST_PATH):
        with open(MANIFEST_PATH) as f:
            manifest = json.load(f)
        for entry in manifest:
            path = os.path.join(OVERRIDE, f"{entry['name']}.{entry['type']}")
            if os.path.exists(path):
                os.remove(path)
                removed += 1
        os.remove(MANIFEST_PATH)
    else:
        print("No loot_disturb Override manifest found -- nothing to restore there.")

    restored = 0
    if os.path.exists(MODULE_MANIFEST_PATH):
        with open(MODULE_MANIFEST_PATH) as f:
            module_manifest = json.load(f)
        import shutil
        for fname in module_manifest:
            backup_path = os.path.join(LOCKER_BACKUP_DIR, fname)
            live_path = os.path.join(MOD_DIR, fname)
            if os.path.exists(backup_path):
                shutil.copy2(backup_path, live_path)
                restored += 1
        os.remove(MODULE_MANIFEST_PATH)
    else:
        print("No loot_disturb module-RIM manifest found -- nothing to restore there.")

    print(f"Removed {removed} loot_disturb file(s) from Override, restored {restored} module RIM(s) from backup. Vanilla fallback restored.")


def main():
    if "--restore" in sys.argv:
        restore()
        return

    force_mode = _arg_value("--mode", None) if "--force" in sys.argv else None
    force_progression = "--progression-system" in sys.argv if "--force" in sys.argv else None
    mode, progression_system, seed_name = (
        (force_mode, bool(force_progression), "manual-force")
        if force_mode is not None
        else resolve_mode_and_progression()
    )

    suppress_resrefs, loot_pool, all_progression_resrefs = load_gear_whitelist()
    progression_resrefs = all_progression_resrefs if progression_system else set()
    if progression_system:
        print(f"Progression System is on -- {len(progression_resrefs)} quest item(s) always-stripped "
              f"at their real container/corpse source.")

    if mode == "skip" and not progression_resrefs:
        print("mode is 'skip' (loot_mode=normal) and Progression System is off -- nothing to wire up, vanilla loot left alone.")
        # Still clean up any manifest from a PREVIOUS mode/seed that no
        # longer applies -- a mode switch to skip+off must not leave
        # stale destroy/replace/bonus edits behind.
        if os.path.exists(MANIFEST_PATH) or os.path.exists(MODULE_MANIFEST_PATH):
            restore()
        # mode="skip" here means the starting-locker fix restores TRUE
        # vanilla instead of the destroy/bonus/replace kit -- "off" means
        # no interference at all. Must run AFTER restore() above, always,
        # since restore() only reverts loot_disturb's OWN prior module
        # edits and doesn't know about this specific locker's target state.
        ensure_starting_locker_gear(GAME_DIR, mode)
        return

    print(f"Non-whitelisted (suppressible) resrefs: {len(suppress_resrefs)}, random-loot pool: {len(loot_pool)}")
    rng = random.Random(seed_name)

    inst = Installation(GAME_DIR)
    deployed = []
    deployed += apply_placeables(inst, mode, suppress_resrefs, loot_pool, progression_resrefs, rng)
    deployed += apply_creatures(inst, mode, suppress_resrefs, loot_pool, progression_resrefs, rng)

    # Diff against the PREVIOUS manifest so a mode/seed switch cleans up
    # any Override file that no longer needs editing (e.g. a template
    # only needed a change under the old mode), not just adds new ones.
    old_manifest = []
    if os.path.exists(MANIFEST_PATH):
        with open(MANIFEST_PATH) as f:
            old_manifest = json.load(f)
    new_keys = {(e["name"], e["type"]) for e in deployed}
    stale = 0
    for entry in old_manifest:
        if (entry["name"], entry["type"]) not in new_keys:
            path = os.path.join(OVERRIDE, f"{entry['name']}.{entry['type']}")
            if os.path.exists(path):
                os.remove(path)
                stale += 1
    if stale:
        print(f"  removed {stale} stale Override file(s) from a previous mode/seed run")

    with open(MANIFEST_PATH, "w") as f:
        json.dump(deployed, f)

    modified_files = apply_module_rim_contents(
        GAME_DIR, mode, suppress_resrefs, loot_pool, progression_resrefs, rng)

    # Same stale-cleanup idea as the Override manifest above, but for
    # module .rim files -- a file that needed editing under the OLD
    # mode/seed but doesn't under the current one must be restored from
    # backup, not left in its old modified state.
    old_module_manifest = []
    if os.path.exists(MODULE_MANIFEST_PATH):
        with open(MODULE_MANIFEST_PATH) as f:
            old_module_manifest = json.load(f)
    new_module_keys = set(modified_files)
    stale_modules = 0
    for fname in old_module_manifest:
        if fname not in new_module_keys:
            backup_path = os.path.join(LOCKER_BACKUP_DIR, fname)
            live_path = os.path.join(MOD_DIR, fname)
            if os.path.exists(backup_path):
                import shutil
                shutil.copy2(backup_path, live_path)
                stale_modules += 1
    if stale_modules:
        print(f"  reverted {stale_modules} stale module RIM(s) from a previous mode/seed run")

    with open(MODULE_MANIFEST_PATH, "w") as f:
        json.dump(modified_files, f)

    # Must run LAST, after apply_module_rim_contents may have just
    # rewritten end_m01aa_s.rim, so this builds on top of (not instead
    # of) those other changes to the same file. mode here is always
    # destroy/bonus/replace (the "skip" case returns earlier above), so
    # this always sets the full starting kit, never vanilla.
    ensure_starting_locker_gear(GAME_DIR, mode)

    print(f"\nDone. {len(deployed)} Override template(s), {len(modified_files)} module RIM(s) rewritten in place. "
          "No relaunch needed -- this is static template data, applied the moment each module next loads.")


if __name__ == "__main__":
    main()
