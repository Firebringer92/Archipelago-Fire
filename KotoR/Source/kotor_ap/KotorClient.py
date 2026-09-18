"""
KotorClient.py -- the real bridge between an Archipelago server and the
injected KOTOR extender (127.0.0.1:25586).

Items received from the AP server are forwarded to the extender's
arm-batch pipeline (current-area + neighbor arming, auto-clear on
confirmed delivery). Location checks are auto-detected from the extender's
raw CHECK|JOURNAL/COMPANION/AREA and ALIGNMENT events via
kotor_location_tracker.py -- 100 real quest completions (every planet, via
KOTOR's own journal system), 9 companion-recruitment checks, 78
area-visited checks, and 13 light/dark alignment checks (10 threshold
crossings + 3 history-based bonus checks), 200 locations total. /ap_check
is kept as a manual override/diagnostic, not the primary path anymore.

Admin commands (/ap_apply, /ap_status) call the exact same extender
protocol the AP-item path uses, so they're safe to use for direct testing
without touching the AP server at all -- a "safety valve" separate from
the real item-received flow.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import random
import re
import subprocess
import sys
import time
import typing

import ModuleUpdate
ModuleUpdate.update()

import Utils

if __name__ == "__main__":
    Utils.init_logging("KotorClient", exception_logger="Client")

from CommonClient import (
    ClientCommandProcessor,
    CommonContext,
    get_base_parser,
    gui_enabled,
    logger,
    server_loop,
)

from kotor_extender_bridge import ExtenderBridge, delivery_state
from kotor_reconciliation import ReconciliationTracker, CLASS_ARM_TO_KEY
from kotor_location_tracker import LocationTracker
from worlds.kotor.Items import item_table, TRAP_ITEMS
from worlds.kotor.Locations import location_table
from worlds.kotor import NON_JEDI_COMPANION_KEYS

# NPC_* index (nwscript.nss) -> the arm that re-grants that companion.
# Order matches Locations.py's generator COMPANIONS list.
COMPANION_IDX_TO_ARM = [
    "companion_bastila", "companion_canderous", "companion_carth",
    "companion_hk47", "companion_jolee", "companion_juhani",
    "companion_mission", "companion_t3m4", "companion_zaalbar",
]

_ID_TO_LOCATION_DATA = {data.id: data for data in location_table.values()}

# TrapLink (see Options.py's TrapLink): an incoming linked trigger is
# resolved into one of our own trap types, rolled locally -- the sender's
# trap_name is only used for the log line. Same 12 arms a real Traps item
# uses (Items.py's TRAP_ITEMS), so a linked trap goes through exactly the
# same _pending_traps/_resolve_trap path.
TRAP_LINK_CANDIDATES: typing.List[typing.Tuple[str, str]] = [
    (name, data.arm_name) for name, data in TRAP_ITEMS.items()
]

# Galactic Shop (see Options.py's GalacticShop). ONE shared Data Storage
# key
# for the whole multiworld (deliberately NOT slot-scoped -- the pool is
# the point), holding {record_id: {player, game, resref, count, time}}.
# A dict keyed by record id rather than a list so both halves are single
# atomic server-side ops with a clean race story: deposit = "update"
# (merge one new key in), withdraw = "pop" (remove one key). A "pop" of a
# key someone else already popped is a no-op the SetReply exposes
# (original_value no longer has the key) -- that's the whole race
# detector, no separate locking needed.
GALACTIC_SHOP_KEY = "kotor_galactic_shop_pool"
# Empty-pool fallback (design: "grant a fixed default item instead of
# failing the withdrawal outright") -- a plain Medpac x2, the lowest-value
# consumable that's still genuinely useful. Not quest-relevant, not in
# any suppression whitelist.
GALACTIC_SHOP_DEFAULT_ITEM = ("g_i_medeqpmnt01", 2)
# How many times a single coin will re-pull the pool and retry after
# losing a withdraw race before giving up and granting the default item.
# Losing even once needs two players withdrawing within the same
# round-trip window; five in a row is not a realistic pool state, just a
# hard stop against spinning forever on a pathological server.
GALACTIC_SHOP_MAX_ATTEMPTS = 5
# Deposits/claims the game logged while the AP server wasn't connected
# (the extender runs regardless of server state) -- persisted so a
# client restart can't lose an item a player already physically gave
# up. Flushed on every Connected. Same directory convention as
# DELIVERY_LOG_PATH below (CWD-relative, next to the client).
GALACTIC_SHOP_PENDING_PATH = "kotor_galactic_shop_pending.json"
# Emitted by extender/scripts_src/ap_galtradebox.nss's OnInvDisturbed
# handler (KSE_Diag 142) -- relayed here like every other AP| line.
_VOIDTRADE_DEPOSIT_RE = re.compile(r"AP\|VOIDTRADE\|DEPOSIT\|([^|\s]+)\|(\d+)")
_VOIDTRADE_CLAIM_RE = re.compile(r"AP\|VOIDTRADE\|CLAIM\b")

# AdditionalFeats: the combined cross-class pool a granted item picks 3
# from -- weapon profs (Blaster Rifle/Heavy Weapons/Lightsaber, excluding
# Pistol/Melee since every class already has those) + armor profs (Light/
# Medium/Heavy) + Implant Level 1 + each class's signature ability feat.
# Source data is feat.2da; see research/feats/class_feats.json for the raw
# per-class table. Deliberately NOT filtered by class here -- the client
# doesn't need to know a character's exact final class to pick from this,
# since the generated NWScript wraps every grant in a live GetHasFeat
# guard as the real "don't double-grant" safety net (see
# KotorContext._is_pc_class_finalized's docstring for why the class-delta
# fix already guarantees a finalized character's baseline is correct).
ADDITIONAL_FEATS_POOL = [
    40, 42, 43,        # Weapon Prof: Blaster Rifle / Heavy Weapons / Lightsaber
    4, 5, 6,           # Armor Prof: Heavy / Light / Medium
    14,                # Implant Level 1
    28, 29,            # Power Attack / Power Blast (Soldier signature)
    11, 30,            # Flurry / Rapid Shot (Scout signature)
    8, 31, 60, 104,    # Critical Strike / Sniper Shot / Sneak Attack I / Scoundrel's Luck
    101, 88, 98,       # Force Jump / Force Focus / Force Immunity: Fear (Jedi signature)
]

# Traps (see Options.py's Traps): classes.2da's own hitdie column, row
# order matching real CLASS_TYPE_* constant values 0-8 (Soldier/Scout/
# Scoundrel/JediGuardian/JediConsular/JediSentinel/CombatDroid/
# ExpertDroid/Minion). Needed for the Cut Max Health in Half trap's Max-HP
# formula below -- KOTOR has no direct Max HP field at all (see
# DEVELOPMENT_HISTORY.md §5, "Engine limitations discovered"), so this is
# computed client-side from already-tracked state (current_classes/
# current_abilities) instead.
CLASS_HITDIE = {0: 10, 1: 8, 2: 6, 3: 10, 4: 6, 5: 8, 6: 12, 7: 8, 8: 10}


def _compute_max_hp(current_classes: dict, con: int) -> int:
    """MaxHP = sum(class_level * hitdie) + floor((CON-10)/2) * total_level.
    Only the PC's own base class + Jedi class (if any) matter here (traps
    are PC-only)."""
    base_class = current_classes.get("baseclass", -1)
    base_level = current_classes.get("baselevel", 0)
    guardian = current_classes.get("guardian", 0)
    consular = current_classes.get("consular", 0)
    sentinel = current_classes.get("sentinel", 0)
    hitdie_sum = base_level * CLASS_HITDIE.get(base_class, 8)
    if guardian:
        hitdie_sum += guardian * CLASS_HITDIE[3]
    elif consular:
        hitdie_sum += consular * CLASS_HITDIE[4]
    elif sentinel:
        hitdie_sum += sentinel * CLASS_HITDIE[5]
    total_level = base_level + guardian + consular + sentinel
    con_bonus = (con - 10) // 2  # Python's // floors correctly even for negative CON-10
    return hitdie_sum + con_bonus * total_level


def _con_decrease_for_half_max_hp(current_classes: dict, current_abilities: dict) -> int:
    """Best-effort search for the Cut Max Health in Half trap -- the
    hitdie_sum term in _compute_max_hp is fixed (CON can't touch it), so
    for some high-level/high-hitdie characters exactly half Max HP may be
    unreachable through Constitution alone (see Options.py's Traps
    docstring, confirmed with the user this is an accepted limitation of
    the engine's own data model, not a bug to chase further). Tries every
    real CON value from current down to 1 (D20's actual floor) and
    returns whichever decrease amount lands CLOSEST to half, preferring
    the LARGER decrease (more punishing, not less) on an exact tie.
    Returns 0 if state isn't known yet (no CLASSREPORT/ABILITYREPORT
    heard from yet) or CON is already at the floor -- caller treats that
    as a safe no-op."""
    con = current_abilities.get("con", 0)
    if con <= 1 or current_classes.get("baselevel", 0) <= 0:
        return 0
    target = _compute_max_hp(current_classes, con) // 2
    best_decrease = 0
    best_diff = None
    for new_con in range(con - 1, 0, -1):
        decrease = con - new_con
        diff = abs(_compute_max_hp(current_classes, new_con) - target)
        if best_diff is None or diff < best_diff or (diff == best_diff and decrease > best_decrease):
            best_diff = diff
            best_decrease = decrease
    return best_decrease


_GOAL_MALAK_RE = re.compile(r"AP\|CHECK\|GOAL\|MALAK_DEAD")
# reach_leviathan Goal option -- reuses the same raw journal event the
# "Leviathan: Captured by the Leviathan" location already fires on
# (lev_captured, journal_target=99 in Locations.py), no new NWScript/native
# signal needed.
_GOAL_LEVIATHAN_RE = re.compile(r"AP\|CHECK\|JOURNAL\|lev_captured\|value=(-?\d+)")
_LEVEL_RE = re.compile(r"AP\|LEVELREPORT\|(\d+)")
# arm_orchestrator.py's own diagnostic -- not written by the KSE DLL, but
# the log-tail thread relays ANY line in kse.log containing
# an AP| marker regardless of writer, so this reaches here the same way
# every real KSE_Diag marker does. See that file's
# _push_queue_bloat_warning_to_client() for why this exists: the original
# print-only warning never reached the client at all (only this script's
# own stdout, which the C extender discards on a successful exit).
_QUEUE_BLOAT_RE = re.compile(r"AP\|WARNING\|QUEUE_BLOAT\|(\d+)")
MAX_LEVEL = 20  # KOTOR's real level cap, per exptable.2da

# Loaded once at import time -- same source of truth Items.py reads to build
# the give_item:<resref> item_table entries. Used here only to decide HOW
# MANY of a gear item to grant: equipment (has a real equipment_slot) always
# grants 1, consumables grant consumable_stack_count (from slot_data),
# capped by the item's own real stack_limit either way.
GEAR_ITEMS_PATH = os.path.join(os.path.dirname(__file__), "worlds", "kotor", "gear_items.json")

# Separate from the shared `logger` (CommonClient's "Client" logger, which
# backs the GUI's main "Archipelago" tab) -- keeps that tab down to just 4
# things (extender connecting, AP server connecting, checks found, items
# sent). Everything else this client logs (the raw heartbeat/event
# firehose, delivery bookkeeping noise, startup warnings, banner text)
# goes here instead, on its own "Heartbeat" GUI tab (see
# KotorManager.logging_pairs below).
game_events_logger = logging.getLogger("Heartbeat")


def _load_gear_items() -> dict:
    try:
        with open(GEAR_ITEMS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, OSError, json.JSONDecodeError) as e:
        game_events_logger.warning(f"[gear] failed to load {GEAR_ITEMS_PATH} ({e}) -- gear item counts will default to 1.")
        return {}


GEAR_ITEMS = _load_gear_items()

# Arms that do AddMultiClass / ShowLevelUpGUI / AddPartyMember / CreateObject
# -- batching several of these together (even all first-time
# applications, no repeats involved) crashes the game. These get
# serialized client-side, one in flight at a time, instead of
# firing immediately like everything else -- see _process_heavy_queue().
# Deliberately NOT everything: skills/abilities/force_death don't touch
# multiclassing, the level-up GUI, or party membership, and have shown no
# crash risk even in much larger batches. see Items.py.)
HEAVY_ARMS = {
    "class_guardian", "class_consular", "class_sentinel",
    "companion_bastila", "companion_canderous", "companion_carth",
    "companion_hk47", "companion_jolee", "companion_juhani",
    "companion_mission", "companion_t3m4", "companion_zaalbar",
    # StartingClass=random_class's base-class roll -- a KSE_SetCreatureField
    # write on the PC, same heavy classification as companion_class's
    # write, same reasoning (see _queue_heavy).
    "pc_class_soldier", "pc_class_scout", "pc_class_scoundrel",
}

# Every arm name the extender's heartbeat/trampoline batch logic knows how
# to apply -- must stay in sync with AP_ARM_NAMES in extender/src/dllmain.c
# and generate_trampoline_batch.py's APPLIES table.
KNOWN_ARM_NAMES = [
    "computer_use", "demolitions", "stealth", "awareness",
    "persuade", "repair", "security", "treat_injury",
    "companion_bastila", "companion_canderous",
    "xp",
    "class_guardian", "class_consular",
    "credits", "grant_test_ability",
    "companion_carth", "companion_hk47", "companion_jolee",
    "companion_juhani", "companion_mission", "companion_t3m4",
    "companion_zaalbar", "class_sentinel",
    "ability_strength", "ability_dexterity", "ability_constitution",
    "ability_intelligence", "ability_wisdom",
    "force_death",
    "pc_class_soldier", "pc_class_scout", "pc_class_scoundrel",
    # Retired research arms are removed outright from this list (it's
    # just an /ap_apply validation list, no positional-ID constraint) --
    # see DEVELOPMENT_HISTORY.md for the research they concluded and
    # extender/research_archive/ for their raw results. Unlike this list,
    # AP_ARM_NAMES in ap_extender.c and APPLIES in
    # generate_trampoline_batch.py rename rather than remove retired
    # entries, to preserve arm-ID stability.
    "test_grant_active_feat",  # TEMPORARY: grants Critical Strike (an
                            # ACTIVE feat) to the PC to check whether it's
                            # genuinely hotbar-usable, not just present.
                            # Retire once confirmed.
    "test_resolve_item",  # TEMPORARY: live loot-window memory research --
                            # resolves a candidate object id (found via a
                            # container's item-reference-list record) and
                            # logs its type/quantity to kse.log. Retire
                            # once this research concludes.
]

# AP item display name -> extender arm name, derived directly from
# item_table's own arm_name field (see Items.py's ItemData docstring) so
# this can never drift out of sync the way a hand-duplicated dict did --
# that stale copy silently dropped every item it didn't recognize,
# including both filler items, for this entire project's testing so far.
ITEM_NAME_TO_ARM = {name: data.arm_name for name, data in item_table.items()}

# Persistent delivery record, one JSON object per line, append-only across
# sessions -- both the audit trail AND (for everything except class
# switches) the primary mechanism preventing a reconnect from replaying
# already-delivered items. Keyed on (character_name, item index): a fresh
# character (deliberate restart) reads as never-seen and gets everything
# re-granted; reconnecting to the SAME character finds its history already
# logged and skips re-processing it. Class switches keep an independent,
# stronger check on top (has_class(), real in-game state) since a lost
# delivery there is worth actively detecting -- see the has_class() call
# site in _deliver_item for why the log alone isn't enough for those.
DELIVERY_LOG_PATH = "kotor_delivery_log.jsonl"

# Same default every other setup script in this repo hardcodes
# (patch_item_suppression.py, patch_door_randomizer.py, setup_game.py,
# generate_poll_shared.py) -- no shared config file for it yet, so this
# stays consistent with that convention rather than inventing a new one
# just for this call site.
GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"


def _sys_argv_value(flag, default):
    """Same lightweight sys.argv scan patch_item_suppression.py/
    patch_door_randomizer.py use for --archipelago-dir -- reads a flag's
    value before get_base_parser()'s real argparse pass runs, since
    REPO_ROOT below is computed at module-import time (before launch()
    parses args)."""
    for i, a in enumerate(sys.argv):
        if a == flag and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
        if a.startswith(flag + "="):
            return a.split("=", 1)[1]
    return default


def _detect_repo_root() -> str:
    """Auto-detects the PlayerBundle folder (the one with scripts\\ and
    extender\\ in it) by actually checking for scripts/generate_poll_shared.py
    rather than assuming a fixed folder depth -- a hardcoded
    dirname(dirname(__file__)) guess only holds for one specific layout
    and silently breaks for any other. Checks both real layouts this
    project supports:
      - KotorClient.py copied directly into an Archipelago checkout root
        that ALSO has scripts\\/extender\\ merged into it (one level up)
      - KotorClient.py nested inside an Archipelago\\ subfolder of a
        separate PlayerBundle-style folder (two levels up, the original
        dev-machine layout)
    --repo-root below still exists as an explicit override for a
    genuinely unusual layout neither guess can find."""
    here = os.path.dirname(os.path.abspath(__file__))
    for candidate in (here, os.path.dirname(here)):
        if os.path.isfile(os.path.join(candidate, "scripts", "generate_poll_shared.py")):
            return candidate
    return os.path.dirname(here)  # last-resort default, same guess as before this fix


REPO_ROOT = _sys_argv_value("--repo-root", _detect_repo_root())
GENERATE_POLL_SHARED = os.path.join(REPO_ROOT, "scripts", "generate_poll_shared.py")
GENERATE_MAKEJEDI_SUPPRESSOR = os.path.join(REPO_ROOT, "scripts", "generate_makejedi_suppressor.py")
PATCH_ITEM_SUPPRESSION = os.path.join(REPO_ROOT, "scripts", "patch_item_suppression.py")
PATCH_LOOT_DISTURB = os.path.join(REPO_ROOT, "scripts", "patch_loot_disturb.py")
PATCH_DOOR_RANDOMIZER = os.path.join(REPO_ROOT, "scripts", "patch_door_randomizer.py")
PATCH_ADDITIONAL_ENEMIES = os.path.join(REPO_ROOT, "scripts", "patch_additional_enemies.py")
PATCH_GALACTIC_SHOP = os.path.join(REPO_ROOT, "scripts", "patch_galactic_shop.py")
PATCH_NEW_COMPANION_ASSETS = os.path.join(REPO_ROOT, "scripts", "generate_new_companion_assets.py")
ARM_ORCHESTRATOR = os.path.join(REPO_ROOT, "scripts", "arm_orchestrator.py")

# Tracks the last seed_name each of the 3 heavier per-seed patch scripts
# (item suppression, door randomization, additional enemies) was actually
# applied for, so on_package's Connected handler only re-invokes one when
# the seed genuinely changed -- unlike regenerate_poll_shared/
# regenerate_makejedi_suppressor (a single-file NWScript recompile, cheap
# enough to always re-run), these 3 do real per-module RIM edits across
# dozens of files each and always do a full sweep when invoked (no
# internal "already applied" short-circuit of their own), so re-running
# them on every reconnect to the SAME seed would cost real, pointless
# time on every single game launch. Their own backup-once-if-missing
# logic makes re-running safe either way -- this is a UX optimization,
# not a correctness requirement.
PATCHED_SEEDS_MARKER_PATH = os.path.join(REPO_ROOT, "extender", "area_trampolines", "_patched_seeds.json")


def _load_patched_seed(key: str) -> str | None:
    try:
        with open(PATCHED_SEEDS_MARKER_PATH, encoding="utf-8") as f:
            return json.load(f).get(key)
    except Exception:
        return None


def _save_patched_seed(key: str, gate_key: str | None) -> None:
    try:
        os.makedirs(os.path.dirname(PATCHED_SEEDS_MARKER_PATH), exist_ok=True)
        try:
            with open(PATCHED_SEEDS_MARKER_PATH, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
        data[key] = gate_key
        with open(PATCHED_SEEDS_MARKER_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as e:
        logger.warning(f"Could not update {PATCHED_SEEDS_MARKER_PATH}: {e}")


def _slot_data_fingerprint(slot_data: dict) -> str:
    """Hashes every field any of the 3 seed-gated patch scripts
    (item_suppression/door_randomizer/additional_enemies) actually reads,
    so _apply_seed_patch_if_new's once-per-seed gate can't be fooled by a
    reused seed_name with genuinely different options -- AP's seed_name
    isn't guaranteed to change just because the options did, and reusing a
    fixed seed while iterating on other options is a normal workflow.
    Deliberately slightly more conservative than a per-script field list
    (e.g. door_randomizer doesn't actually care about loot_mode) --
    an unnecessary re-run costs a little time; an incorrect skip silently
    serves stale game behavior, which is the worse failure mode."""
    relevant = {
        "loot_mode": slot_data.get("loot_mode", 0),
        "door_mapping": slot_data.get("door_mapping"),
        "area_randomizer": bool(slot_data.get("area_randomizer", False)),
        "starting_class": slot_data.get("starting_class", 0),
        "additional_enemies_mode": slot_data.get("additional_enemies_mode", 0),
        "seed_name": slot_data.get("seed_name"),
        "progression_system": bool(slot_data.get("progression_system", False)),
    }
    return hashlib.sha256(json.dumps(relevant, sort_keys=True).encode("utf-8")).hexdigest()

# The per-seed patch scripts (patch_item_suppression.py/
# patch_door_randomizer.py/patch_loot_disturb.py/patch_additional_enemies.py)
# run as separate subprocesses with no direct access to this client's own
# in-memory slot_data, so it's written out here as plain JSON for them to
# read -- always this connection's own real slot_data, never a locally
# generated seed zip (which only exists on whichever machine ran
# Generate.py, not on a player joining someone else's hosted multiworld).
SLOT_DATA_PATH = os.path.join(REPO_ROOT, "extender", "area_trampolines", "_slot_data.json")


def write_slot_data_for_patch_scripts(
        loot_mode: int, door_mapping: dict | None, area_randomizer: bool, starting_class: int,
        additional_enemies_mode: int = 0, seed_name: str | None = None,
        progression_system: bool = False, galactic_shop: bool = False,
        new_companion: bool = False) -> None:
    """Called on every successful Connect -- see SLOT_DATA_PATH above for
    why this exists. A plain JSON write (not restricted_loads/pickle --
    this project controls both ends, unlike the raw .archipelago format),
    so the patch scripts don't need to import Utils from a real
    Archipelago checkout for this.

    `seed_name` also lets patch_additional_enemies.py derive a
    reproducible RNG seed from the real AP seed, so the same player always
    gets the same additive placements from the same seed instead of a
    fresh random draw on every re-run. Every field here has a real reader
    on the patch-script side -- see each script's own
    `_connected_<option>()`-style helper for which key it expects."""
    try:
        os.makedirs(os.path.dirname(SLOT_DATA_PATH), exist_ok=True)
        with open(SLOT_DATA_PATH, "w", encoding="utf-8") as f:
            json.dump({
                "loot_mode": loot_mode, "door_mapping": door_mapping,
                "area_randomizer": area_randomizer, "starting_class": starting_class,
                "additional_enemies_mode": additional_enemies_mode, "seed_name": seed_name,
                "progression_system": progression_system,
                # Read by patch_galactic_shop.py -- applies the Ebon Hawk
                # cargo-hold module edit when on, restores the vanilla RIM
                # when off.
                "galactic_shop": galactic_shop,
                # Read by generate_trampoline_batch.py at real delivery
                # time to decide arm 20's (companion_hk47) template string
                # -- see that file's NEW_COMPANION_TEMPLATE comment.
                "new_companion": new_companion,
            }, f)
    except Exception as e:
        logger.warning(f"Could not write {SLOT_DATA_PATH} for the patch scripts: {e}")


def regenerate_poll_shared(area_randomizer: bool, additional_enemies_mode: int = 0) -> tuple[bool, str]:
    """Regenerates, compiles, and deploys ap_poll_shared.ncs for the ACTUAL
    connected seed's area_randomizer, straight to GAME_DIR's live Override
    -- a pure local file operation (write .nss, compile via nwnnsscomp.exe,
    copy the .ncs), no extender/DLL round-trip needed.

    package_dist.py's prebuilt dist/Override bundle ships whatever
    area_randomizer happened to be true on the packaging machine at
    packaging time -- wrong for any tester whose own seed differs.
    Calling this on every Connected (see KotorContext.on_package) makes
    the deployed script always match the seed actually being played, no
    manual step required. Returns
    (success, message) rather than raising -- called from a background
    task on Connected, where an unhandled exception would be swallowed
    silently by asyncio anyway; a clear log line either way is more useful
    than a stack trace nobody sees.

    No loot_mode parameter -- Loot Mode's grant/suppression logic lives
    entirely in patch_loot_disturb.py's static template edits (see
    DESIGN.md §4.3), so this script never needs to know loot_mode at all.

    additional_enemies_mode gates CheckBountyCount() the same way
    area_randomizer gates CheckPlanetAvailability() -- only generated into
    the deployed script when a mode other than off is actually connected,
    since the check is meaningless (and would burn a poll cycle for
    nothing) when no bounty carriers exist in this seed at all."""
    try:
        result = subprocess.run(
            [sys.executable, GENERATE_POLL_SHARED,
             f"--game-dir={GAME_DIR}",
             f"--area-randomizer={1 if area_randomizer else 0}",
             f"--additional-enemies={1 if additional_enemies_mode else 0}"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            return False, f"generate_poll_shared.py failed (exit {result.returncode}):\n{result.stdout}\n{result.stderr}"
        return True, result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "done"
    except Exception as e:
        return False, f"regenerate_poll_shared raised: {e}"


def regenerate_makejedi_suppressor(starting_class: int) -> tuple[bool, str]:
    """Regenerates, compiles, and deploys the Dantooine k_pdan_makejedi
    suppression wrapper for the ACTUAL connected seed's starting_class value
    -- same reasoning and same pure-local-file-operation shape as
    regenerate_poll_shared above. See generate_makejedi_suppressor.py's
    module docstring for what this wrapper does and why it's needed
    (starting_class's item-gating is otherwise bypassed for free by simply
    playing the Dantooine trials normally)."""
    try:
        result = subprocess.run(
            [sys.executable, GENERATE_MAKEJEDI_SUPPRESSOR,
             f"--game-dir={GAME_DIR}",
             f"--starting-class={starting_class}"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            return False, f"generate_makejedi_suppressor.py failed (exit {result.returncode}):\n{result.stdout}\n{result.stderr}"
        return True, result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "done"
    except Exception as e:
        return False, f"regenerate_makejedi_suppressor raised: {e}"


def reset_trampolines_if_owner_changed(seed_name: str, slot: str) -> tuple[bool, str]:
    """Guards against cross-slot trampoline leakage when two AP slots of
    the same seed share one physical Override install (see this project's
    docs/MODE_DEPENDENCIES.md, the (seed_name, slot) scoping item): an item
    armed-but-unconfirmed for one slot's session has no per-slot isolation
    in _armed_state.json/_pending_queue.json, so a DIFFERENT slot walking
    into that same area could receive it. Delegates the actual owner
    comparison and reset to arm_orchestrator.py's --reset-if-owner-changed=
    (a no-op if the given seed_name/slot already matches the recorded
    owner, i.e. an ordinary same-slot reconnect)."""
    try:
        result = subprocess.run(
            [sys.executable, ARM_ORCHESTRATOR, f"--game-dir={GAME_DIR}",
             f"--reset-if-owner-changed={seed_name}:{slot}"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            return False, f"arm_orchestrator.py --reset-if-owner-changed failed (exit {result.returncode}):\n{result.stdout}\n{result.stderr}"
        return True, result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "done"
    except Exception as e:
        return False, f"reset_trampolines_if_owner_changed raised: {e}"


def apply_item_suppression() -> tuple[bool, str]:
    """Drives patch_item_suppression.py's apply_progression_checkpoint_wrappers()
    (Sith Papers/Enviro Suit's gate-and-delegate mechanism) -- a no-op
    when progression_system is off. Loot Mode's own destroy/bonus/replace
    handling lives entirely in apply_loot_disturb() below instead (see
    DESIGN.md §4.3 for why the two are separate)."""
    try:
        result = subprocess.run(
            [sys.executable, PATCH_ITEM_SUPPRESSION, f"--game-dir={GAME_DIR}"],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            return False, f"patch_item_suppression.py failed (exit {result.returncode}):\n{result.stdout}\n{result.stderr}"
        return True, result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "done"
    except Exception as e:
        return False, f"apply_item_suppression raised: {e}"


def _run_patch_script(script_path: str, extra_args: list[str] | None = None, timeout: int = 300) -> tuple[bool, str]:
    """Shared subprocess runner for the per-seed patch scripts -- returns
    (ok, raw stdout) so a caller that needs to inspect specific printed
    lines (e.g. apply_all_patches()'s Loot Mode two-line split) can,
    without every other caller needing to change."""
    try:
        result = subprocess.run(
            [sys.executable, script_path, f"--game-dir={GAME_DIR}"] + (extra_args or []),
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            return False, result.stdout + result.stderr
        return True, result.stdout
    except Exception as e:
        return False, f"{script_path} raised: {e}"


def apply_loot_disturb() -> tuple[bool, str]:
    """Runs patch_loot_disturb.py against GAME_DIR for the connected
    seed's destroy/bonus/replace loot handling. Pure static template
    edits (rewrites each loot-bearing placeable/creature's ItemList in
    Override before the game loads) -- no script hook, no relaunch
    requirement, takes effect the moment each module next loads. See
    DESIGN.md §4.3 for why this design replaced two earlier runtime-hook
    attempts. No mode/flags passed -- the script reads loot_mode/
    progression_system straight from SLOT_DATA_PATH. Gated on the seed
    actually having changed via _apply_seed_patch_if_new, same as every
    other patch script here."""
    ok, stdout = _run_patch_script(PATCH_LOOT_DISTURB)
    if not ok:
        return False, f"patch_loot_disturb.py failed:\n{stdout}"
    return True, stdout.strip().splitlines()[-1] if stdout.strip() else "done"


def apply_door_randomizer() -> tuple[bool, str]:
    """Same shape as apply_item_suppression above, for
    patch_door_randomizer.py -- reads door_mapping from SLOT_DATA_PATH
    itself, no flags needed here. Pure GFF field edits, no compiler
    dependency, but still a real multi-module sweep -- same
    once-per-seed gating reasoning applies."""
    try:
        result = subprocess.run(
            [sys.executable, PATCH_DOOR_RANDOMIZER, f"--game-dir={GAME_DIR}"],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            return False, f"patch_door_randomizer.py failed (exit {result.returncode}):\n{result.stdout}\n{result.stderr}"
        return True, result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "done"
    except Exception as e:
        return False, f"apply_door_randomizer raised: {e}"


def apply_additional_enemies() -> tuple[bool, str]:
    """Same shape again, for patch_additional_enemies.py -- reads
    additional_enemies_mode and seed_name from SLOT_DATA_PATH itself (the
    latter is what makes its placements reproducible for this seed rather
    than re-rolling on every re-run)."""
    try:
        result = subprocess.run(
            [sys.executable, PATCH_ADDITIONAL_ENEMIES, f"--game-dir={GAME_DIR}"],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            return False, f"patch_additional_enemies.py failed (exit {result.returncode}):\n{result.stdout}\n{result.stderr}"
        return True, result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "done"
    except Exception as e:
        return False, f"apply_additional_enemies raised: {e}"


def revert_all_game_files() -> tuple[bool, str]:
    """Reverts every per-seed patch this project makes back to a clean
    baseline. Needed when switching a local install between two different
    player YAMLs' seeds: every patch script reads one shared
    _slot_data.json and writes to one shared Modules/Override, so a
    second slot's Connect would otherwise silently corrupt whatever the
    first slot's patches left behind. Run this before reconnecting to a
    different slot on the same install.

    Calls patch_item_suppression.py --restore (reverts every module RIM
    it/patch_door_randomizer.py/patch_additional_enemies.py have touched,
    from their shared backup store) and patch_loot_disturb.py --restore
    (deletes its own loose Override files, since it never touches a RIM
    and has nothing to restore from backup). Does not touch the extender
    DLL or standing features unrelated to per-seed options (Galactic
    Shop, Bounty Card creatures, etc. -- see patch_loot_disturb.py's
    restore())."""
    total_restored = 0
    ok_all = True
    for script in (PATCH_ITEM_SUPPRESSION, PATCH_LOOT_DISTURB):
        try:
            result = subprocess.run(
                [sys.executable, script, "--restore", f"--game-dir={GAME_DIR}"],
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode != 0:
                ok_all = False
                continue
            total_restored += sum(int(n) for n in re.findall(r"(?:[Rr]estored|[Rr]emoved) (\d+)", result.stdout))
        except Exception:
            ok_all = False
    if ok_all:
        return True, f"restored {total_restored} file(s) back from Override backups and module RIMs"
    return False, "one or more restore steps failed -- check the Heartbeat log for detail"


def apply_all_patches() -> tuple[bool, str]:
    """The straightforward counterpart to revert_all_game_files() --
    re-applies every per-seed patch fresh, ignoring the once-per-seed
    marker: the 4 heavier RIM-sweep patches plus Jedi Suppression
    (regenerate_makejedi_suppressor(), which takes starting_class as a
    direct argument rather than reading slot_data itself, unlike the
    subprocess-based patch scripts, so it's read from SLOT_DATA_PATH
    here). Exactly what you want right after revert_all_game_files() or
    when switching to a freshly-connected second slot on the same
    install. Deliberately does NOT include New Companion's asset deploy
    (apply_new_companion_assets()) -- that has no --restore counterpart in
    revert_all_game_files() yet, so adding it here would let this command
    deploy something the revert command can't clean back up; add both
    together if that gap is ever closed, never just one.

    Returns one short `Patching <name> - Status: DONE/FAILED` line per
    operation plus a final ready-to-launch summary line, not each script's
    own raw stdout (still available in each script's own output for
    debugging). Loot Mode reports TWO lines, not one, since
    patch_loot_disturb.py genuinely performs two separate file operations
    in one subprocess call (the main destroy/bonus/replace pass, and the
    "Endar Spire starting locker" fix, ensure_starting_locker_gear()) --
    reported individually rather than assumed to share fate."""
    lines = []
    ok_all = True

    loot_ok, loot_stdout = _run_patch_script(PATCH_LOOT_DISTURB)
    ok_all = ok_all and loot_ok
    lines.append(f"Patching Loot Mode - Disturb Items - Status: {'DONE' if loot_ok else 'FAILED'}")
    # ensure_starting_locker_gear() only ever prints on a real change or a
    # genuine skip -- a silent stdout (already matched target, nothing to
    # do) is a real success case too, so only the explicit skip phrase
    # counts as a failure here, not "printed nothing."
    locker_ok = loot_ok and "skipping starting-locker gear fix" not in loot_stdout
    lines.append(f"Patching Loot Mode - Starting Locker - Status: {'DONE' if locker_ok else 'FAILED'}")
    ok_all = ok_all and locker_ok

    for label, fn in [
        ("Progression Checkpoints", apply_item_suppression),
        ("Randomize Areas", apply_door_randomizer),
        ("Additional Enemies", apply_additional_enemies),
    ]:
        ok, _msg = fn()
        ok_all = ok_all and ok
        lines.append(f"Patching {label} - Status: {'DONE' if ok else 'FAILED'}")

    starting_class = 0
    try:
        with open(SLOT_DATA_PATH, encoding="utf-8") as f:
            starting_class = json.load(f).get("starting_class", 0)
    except Exception:
        pass
    jedi_ok, _jedi_msg = regenerate_makejedi_suppressor(starting_class)
    ok_all = ok_all and jedi_ok
    lines.append(f"Patching Jedi Suppression - Status: {'DONE' if jedi_ok else 'FAILED'}")

    lines.append("Game is ready to launch." if ok_all else "One or more patches failed -- check the Heartbeat log before launching.")
    return ok_all, "\n".join(lines)


def apply_new_companion_assets() -> tuple[bool, str]:
    """Same shape as apply_galactic_shop() -- reads new_companion from
    SLOT_DATA_PATH itself, run on every Connect rather than seed-gated,
    since restoring the true vanilla Tatooine trigger when the option is
    OFF is just as much this call's job as deploying p_meetra.utc/
    k_hmee_dialog.dlg/the new-companion trigger variant when it's on.
    Three Override files, no module RIM edits, cheap enough to always run."""
    try:
        result = subprocess.run(
            [sys.executable, PATCH_NEW_COMPANION_ASSETS, f"--game-dir={GAME_DIR}"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            return False, f"generate_new_companion_assets.py failed (exit {result.returncode}):\n{result.stdout}\n{result.stderr}"
        return True, result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "done"
    except Exception as e:
        return False, f"apply_new_companion_assets raised: {e}"


def apply_galactic_shop() -> tuple[bool, str]:
    """Same shape again, for patch_galactic_shop.py -- reads
    galactic_shop from SLOT_DATA_PATH itself. One module (ebo_m12aa) plus
    three Override files, cheap enough to run on every Connect rather
    than seed-gate: the script is idempotent (skips a RIM already
    retargeted, restores vanilla when the option is off)."""
    try:
        result = subprocess.run(
            [sys.executable, PATCH_GALACTIC_SHOP, f"--game-dir={GAME_DIR}"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            return False, f"patch_galactic_shop.py failed (exit {result.returncode}):\n{result.stdout}\n{result.stderr}"
        return True, result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "done"
    except Exception as e:
        return False, f"apply_galactic_shop raised: {e}"


def _load_galactic_pending() -> dict:
    """See GALACTIC_SHOP_PENDING_PATH. {"deposits": [record, ...],
    "claims": int} -- deposits are full pool records already built at
    deposit time (so the depositor name/time are the REAL ones, not
    whenever the flush happens); claims is just a count of coins spent
    while offline, since a claim carries no data of its own."""
    try:
        with open(GALACTIC_SHOP_PENDING_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {"deposits": list(data.get("deposits", [])), "claims": int(data.get("claims", 0))}
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as e:
        game_events_logger.warning(f"[galactic shop] couldn't read {GALACTIC_SHOP_PENDING_PATH} ({e}) -- starting empty")
    return {"deposits": [], "claims": 0}


class KotorClientCommandProcessor(ClientCommandProcessor):
    def _cmd_ap_check(self, *location_name_parts: str) -> bool:
        """Report a location check by name, e.g. /ap_check Endar Spire: Escape Pod Reached"""
        if not self.ctx.server:
            self.output("Not connected to a server yet. Use /connect first.")
            return False

        location_name = " ".join(location_name_parts).strip()
        lookup = self.ctx.location_names[self.ctx.game]
        name_to_id = {name: loc_id for loc_id, name in lookup.items() if loc_id >= 0}

        if location_name not in name_to_id:
            self.output(f"Unknown location {location_name!r}. Use /ap_locations to list them.")
            return False

        loc_id = name_to_id[location_name]
        if loc_id in self.ctx.checked_locations:
            self.output(f"{location_name!r} is already checked.")
            return False

        self.ctx.locations_checked.add(loc_id)
        asyncio.create_task(self.ctx.send_msgs([
            {"cmd": "LocationChecks", "locations": [loc_id]}
        ]))
        self.output(f"Sent check: {location_name}")
        return True

    def _cmd_ap_locations(self) -> bool:
        """List every test location and whether it's been checked yet."""
        if not self.ctx.server:
            self.output("Not connected to a server yet. Use /connect first.")
            return False
        lookup = self.ctx.location_names[self.ctx.game]
        for loc_id, name in sorted(lookup.items(), key=lambda kv: kv[1]):
            if loc_id < 0:
                continue
            state = "CHECKED" if loc_id in self.ctx.checked_locations else "missing"
            self.output(f"[{state:7}] {name}")
        return True

    def _cmd_ap_apply(self, arm_name: str = "") -> bool:
        """ADMIN/testing safety valve: directly queue an arm with the
        extender, bypassing the AP server entirely -- exactly the same
        call the real item-received path makes. e.g. /ap_apply credits
        Gear items use give_item:<resref>[:<count>], e.g.
        /ap_apply give_item:g1_w_lghtsbr01:1 -- count defaults to 1.
        Companion class randomization uses companion_class:<name>:<class>,
        e.g. /ap_apply companion_class:carth:guardian -- see Options.py's
        CompanionClass and generate_trampoline_batch.py's
        build_companion_class_block for the valid name/class values.
        Additional Feats uses additional_feats:<key>, e.g.
        /ap_apply additional_feats:pc -- valid keys: pc, bastila,
        canderous, carth, jolee, juhani, mission, zaalbar. Traps use
        trap:<type>[:<params>], e.g. /ap_apply trap:reduce_skill."""
        if not arm_name:
            self.output(f"Usage: /ap_apply <name>. Known names: {', '.join(KNOWN_ARM_NAMES)}, "
                        f"or give_item:<resref>[:<count>], or companion_class:<name>:<class>, "
                        f"or additional_feats:<key>, or trap:<type>[:<params>]")
            return False
        if not self.ctx.extender.is_connected:
            self.output("Not connected to the extender (is the game running with the DLL loaded?).")
            return False
        if arm_name.startswith("give_item:"):
            parts = arm_name.split(":")
            resref = parts[1] if len(parts) > 1 else ""
            if not resref:
                self.output("Usage: /ap_apply give_item:<resref>[:<count>]")
                return False
            count = int(parts[2]) if len(parts) > 2 else 1
            asyncio.create_task(self.ctx.extender.send_apply_item(resref, count))
            self.output(f"Admin: queued give_item {resref!r} x{count} directly (bypassing AP server).")
            return True
        if arm_name.startswith("companion_class:"):
            parts = arm_name.split(":")
            if len(parts) != 3 or not parts[1] or not parts[2]:
                self.output("Usage: /ap_apply companion_class:<name>:<class>")
                return False
            # Routed through the heavy queue -- applying this alongside
            # another trampoline-batch grant risks the same crash class
            # HEAVY_ARMS exists to prevent for
            # class_guardian/companion_carth/etc. See _queue_heavy.
            self.ctx._queue_heavy(arm_name, f"(admin) companion_class:{parts[1]}:{parts[2]}")
            self.output(f"Admin: queued companion_class {parts[1]}:{parts[2]} (serialized, bypassing AP server).")
            return True
        if arm_name.startswith("additional_feats:"):
            # Routes through the same _pending_additional_feats +
            # _resolve_additional_feats path a real item receipt uses --
            # still gated on recruited+class-finalized, so it may not
            # apply instantly if that character isn't ready yet.
            _valid_feat_keys = ("pc", "bastila", "canderous", "carth", "jolee",
                                 "juhani", "mission", "zaalbar")
            parts = arm_name.split(":", 1)
            npc_key = parts[1] if len(parts) > 1 else ""
            if npc_key not in _valid_feat_keys:
                self.output(f"Usage: /ap_apply additional_feats:<key>, valid keys: {', '.join(_valid_feat_keys)}")
                return False
            self.ctx._admin_trap_counter = getattr(self.ctx, "_admin_trap_counter", 0) - 1
            key = (self.ctx.seed_name, getattr(self.ctx, "username", None), self.ctx._admin_trap_counter)
            self.ctx._pending_additional_feats[key] = (f"(admin) {arm_name}", arm_name)
            self.output(f"Admin: queued additional_feats {npc_key!r} -- resolves once recruited+class-finalized (bypassing AP server).")
            return True
        if arm_name.startswith("trap:"):
            # trap:<type> is a dynamically-parameterized action, not a
            # static registered name (same category as give_item:/
            # companion_class: above). Routes through the same
            # _pending_traps + _resolve_trap path a real trap item
            # receipt uses -- resolves on the next poll cycle, not
            # instantly, matching real delivery behavior.
            parts = arm_name.split(":", 2)
            if len(parts) < 2 or not parts[1]:
                self.output("Usage: /ap_apply trap:<type>[:<params>], e.g. /ap_apply trap:cut_max_hp")
                return False
            if arm_name == "trap:remove_credits":
                # Mirrors _deliver_item's own real-item shortcut for this
                # one trap -- no pending/resolution step involved at all.
                asyncio.create_task(self.ctx.extender.send_apply_value("set_credits", 0))
                self.output("Admin: queued trap:remove_credits directly (set_credits:0, bypassing AP server).")
                return True
            # Unique NEGATIVE index per admin call (real AP item indices are
            # never negative) -- a fixed sentinel here would let a second
            # admin-triggered trap silently overwrite a first one still
            # sitting in _pending_traps before a poll cycle consumes it,
            # since dict writes with the same key just clobber each other.
            self.ctx._admin_trap_counter = getattr(self.ctx, "_admin_trap_counter", 0) - 1
            key = (self.ctx.seed_name, getattr(self.ctx, "username", None), self.ctx._admin_trap_counter)
            self.ctx._pending_traps[key] = (f"(admin) {arm_name}", arm_name)
            self.output(f"Admin: queued trap {arm_name!r} -- resolves on the next poll cycle (bypassing AP server).")
            return True
        if arm_name.startswith("force_power:"):
            # TSL Force Power port pilot: force_power:<spells.2da
            # row id>. For a ported power the id is whatever row
            # patch_tsl_powers.py appended (it prints them; 133+ on a
            # vanilla table); any vanilla FORCE_POWER_* row works too.
            # Deliberately admin-only for now -- the pilot's whole point is
            # live-testing the 3 ported powers before deciding whether they
            # become real AP items.
            raw = arm_name.split(":", 1)[1]
            if not raw.isdigit():
                self.output("Usage: /ap_apply force_power:<spells.2da row id>, e.g. /ap_apply force_power:133")
                return False
            asyncio.create_task(self.ctx.extender.send_force_power(int(raw)))
            self.output(f"Admin: queued force_power {raw} directly (bypassing AP server) -- "
                        f"lands on your next area transition.")
            return True
        if arm_name in ("xp", "credits"):
            # Mirrors _do_deliver's real-item handling for these two
            # exactly: a real "xp"/"credits" AP item is bookkeeping-only,
            # note_item_received() bumps the expected total and the
            # reconciler's own bidirectional clamp (set_xp/set_credits)
            # does the actual grant on its next transition/poll. Routing
            # through the same call here (rather than the raw fixed-
            # increment arm, GiveGoldToCreature/GiveXPToCreature) makes
            # this a genuinely representative test of the real path --
            # sending the raw arm directly desyncs the reconciler, since
            # its clamp doesn't know about a grant it didn't expect and
            # corrects the "extra" straight back out.
            self.ctx.reconciler.note_item_received(arm_name)
            self.output(f"Admin: recorded a {arm_name!r} receipt (bypassing AP server) -- "
                        f"the reconciler will apply the correction on its own next poll/transition, "
                        f"same as a real item.")
            return True
        if arm_name not in KNOWN_ARM_NAMES:
            self.output(f"Unknown arm name {arm_name!r}. Known names: {', '.join(KNOWN_ARM_NAMES)}")
            return False
        if arm_name in HEAVY_ARMS:
            # Same reasoning as companion_class above -- the admin bypass
            # used to send straight through regardless of HEAVY_ARMS
            # membership, meaning even class_guardian/companion_carth/etc.
            # were only ever actually protected from batching on the real
            # AP-item path, never when triggered via /ap_apply.
            self.ctx._queue_heavy(arm_name, f"(admin) {arm_name}")
            self.output(f"Admin: queued {arm_name!r} (serialized, bypassing AP server).")
        else:
            asyncio.create_task(self.ctx.extender.send_apply(arm_name))
            self.ctx._maybe_queue_companion_class(arm_name)
            self.output(f"Admin: queued {arm_name!r} directly (bypassing AP server).")
        return True

    def _cmd_ap_regen_poll(self) -> bool:
        """Manual fallback: force-regenerate/compile/deploy ap_poll_shared.ncs
        for this session's already-connected area_randomizer (normally done
        automatically on Connect -- see on_package). Use this if the
        automatic regeneration failed (check the log for a
        "[poll_shared] regeneration FAILED" line) or if you just want to
        re-sync after manually editing the game install's Override."""
        self.output(f"Admin: regenerating ap_poll_shared.ncs for "
                    f"area_randomizer={self.ctx.area_randomizer}, "
                    f"additional_enemies_mode={self.ctx.additional_enemies_mode} ...")
        ok, msg = regenerate_poll_shared(self.ctx.area_randomizer, self.ctx.additional_enemies_mode)
        self.output(("OK: " if ok else "FAILED: ") + msg)
        return ok

    def _cmd_ap_regen_makejedi(self) -> bool:
        """Manual fallback: force-regenerate/compile/deploy the Dantooine
        make-jedi suppression wrapper for this session's already-connected
        starting_class (normally done automatically on Connect -- see
        on_package). Use this if the automatic regeneration failed (check
        the log for a "[makejedi] regeneration FAILED" line) or if you
        just want to re-sync after manually editing the game install's
        Override."""
        self.output(f"Admin: regenerating the Dantooine make-jedi suppressor for "
                    f"starting_class={self.ctx.starting_class} ...")
        ok, msg = regenerate_makejedi_suppressor(self.ctx.starting_class)
        self.output(("OK: " if ok else "FAILED: ") + msg)
        return ok

    def _revert_all_game_files_and_log(self) -> None:
        """Background-thread body for _cmd_ap_restore_all -- logs via
        game_events_logger, not self.output, since this runs off the
        event loop thread (same reasoning as every other _and_log helper
        here)."""
        ok, msg = revert_all_game_files()
        if ok:
            game_events_logger.info(f"[ap_restore_all] {msg}")
        else:
            game_events_logger.warning(f"[ap_restore_all] {msg}")

    def _cmd_ap_restore_all(self) -> bool:
        """Reverts EVERY per-seed patch (loot_disturb, item_suppression,
        door_randomizer, additional_enemies) back to a clean vanilla
        baseline in one call. Real use case: testing two different player
        YAMLs' seeds on the SAME local KOTOR install -- run this BEFORE
        disconnecting from one slot and reconnecting to a different one,
        so the second slot's Connect starts from clean vanilla rather than
        the first slot's leftover patches. Does not touch the extender DLL
        itself or standing features unrelated to per-seed options
        (Galactic Shop/Bounty Cards left alone). See /ap_patch_all to
        re-patch fresh afterward.

        Dispatched via run_in_executor rather than calling
        revert_all_game_files() directly on the event loop thread, which
        would block the whole client (network heartbeat included) for the
        full subprocess runtime -- same reasoning as /ap_patch_all's own
        dispatch below."""
        self.output("Admin: restoring all per-seed game files to vanilla in the background (watch the Heartbeat log for completion) ...")
        asyncio.get_event_loop().run_in_executor(None, self._revert_all_game_files_and_log)
        return True

    def _apply_all_patches_and_log(self) -> None:
        """Background-thread body for _cmd_ap_patch_all -- logs via
        game_events_logger, not self.output, since this runs off the
        event loop thread (same reasoning as every other _and_log helper
        here)."""
        ok, msg = apply_all_patches()
        if ok:
            game_events_logger.info(f"[ap_patch_all]\n{msg}")
        else:
            game_events_logger.warning(f"[ap_patch_all]\n{msg}")

    def _cmd_ap_patch_all(self) -> bool:
        """Re-applies all per-seed patches fresh (loot_disturb split into
        its 2 real sub-operations, item_suppression, door_randomizer,
        additional_enemies, plus Jedi Suppression) for whichever seed
        you're currently connected to, ignoring the once-per-seed marker
        entirely. Pairs with /ap_restore_all -- run that first when
        switching to a different local KOTOR install/slot on the same
        machine, then this to patch it fresh. See apply_all_patches()'s
        own docstring for exactly what's covered and why New Companion's
        asset deploy deliberately isn't (no matching --restore yet).

        Dispatched via run_in_executor rather than calling
        apply_all_patches() directly on the event loop thread, which would
        block the whole client (network heartbeat included) for the full
        combined runtime of 4 subprocess-based RIM sweeps.
        apply_all_patches() itself is already correctly sequenced
        (loot_disturb first, in a plain for-loop) -- see
        _apply_module_rim_patches_in_order's docstring for the Connect-
        time ordering this relies on."""
        self.output("Admin: applying all 4 per-seed patches fresh in the background (watch the Heartbeat log for completion) ...")
        asyncio.get_event_loop().run_in_executor(None, self._apply_all_patches_and_log)
        return True

    def _cmd_ap_apply_galactic_shop(self) -> bool:
        """Same again, for patch_galactic_shop.py (normally run on every
        Connect -- see on_package)."""
        self.output("Admin: re-applying the Galactic Shop module patch ...")
        ok, msg = apply_galactic_shop()
        self.output(("OK: " if ok else "FAILED: ") + msg)
        return ok

    def _cmd_ap_apply_new_companion(self) -> bool:
        """Same again, for generate_new_companion_assets.py (normally run
        on every Connect -- see on_package). Re-deploys the vanilla-or-new
        Tatooine trigger variant plus, when new_companion is on,
        p_meetra.utc/k_hmee_dialog.dlg."""
        self.output("Admin: re-applying the New Companion assets ...")
        ok, msg = apply_new_companion_assets()
        self.output(("OK: " if ok else "FAILED: ") + msg)
        return ok

    def _cmd_ap_shop(self) -> bool:
        """Galactic Shop status: what this client still owes the server
        (deposits/claims logged while disconnected), and a live dump of
        the shared pool (arrives a moment later, on the server's reply)."""
        ctx = self.ctx
        pending = ctx._galactic_pending
        self.output(f"Galactic Shop: option {'ON' if ctx.galactic_shop else 'off'} for this slot; "
                    f"{len(pending['deposits'])} deposit(s) and {pending['claims']} claim(s) waiting to be "
                    f"sent to the server; {len(ctx._galactic_claims_in_flight)} claim(s) in flight.")
        if not ctx.server:
            self.output("Not connected to a server -- can't read the shared pool.")
            return True
        ctx._galactic_status_requested = True
        asyncio.create_task(ctx.send_msgs([{"cmd": "Get", "keys": [GALACTIC_SHOP_KEY], "kotor_shop_status": True}]))
        self.output("Requested the shared pool from the server -- contents follow.")
        return True

    def _cmd_ap_raw(self, *parts: str) -> bool:
        """TEMPORARY/research: send a raw diagnostic command straight to the
        extender socket, e.g. /ap_raw DUMPMEM:16EBB958:64 (hex address, no
        0x prefix, decimal size). Also READBYTE:<hexaddr>, WRITEBYTE:<hexaddr>:<value>,
        SCANBYTES:<comma-separated-hex-bytes>, SNAPSHOT:<name> -- whatever
        ap_extender.c's ap_dispatch_command understands. Output (e.g. a
        DUMPMEM dump) goes to a file next to kse.log, NOT this console.
        Kept for the Force Powers memory-offset hunt this was built for."""
        command = " ".join(parts)
        if not command:
            self.output("Usage: /ap_raw <command>, e.g. /ap_raw DUMPMEM:16EBB958:64")
            return False
        if not self.ctx.extender.is_connected:
            self.output("Not connected to the extender (is the game running with the DLL loaded?).")
            return False
        asyncio.create_task(self.ctx.extender.send_raw(command))
        self.output(f"Admin: sent raw command {command!r} directly (bypassing AP server).")
        return True

    def _cmd_ap_status(self) -> bool:
        """Show extender connection status and pending/recent deliveries."""
        ext = self.ctx.extender
        self.output(f"Extender: {'CONNECTED' if ext.is_connected else 'not connected'}")
        if self.ctx._character_confirmed is False:
            character = self.ctx.reconciler.current_character_name
            self.output(f"SAFEGUARD ACTIVE: character {character!r} (level {self.ctx.current_level}) unrecognized -- "
                        f"all deliveries/corrections paused. Run /ap_confirm_character if this is intentional.")
        pending = ext.pending_deliveries()
        queued = [d for d in pending if delivery_state(d) == "Queued"]
        staged = [d for d in pending if delivery_state(d) == "Staged"]
        if queued:
            self.output(f"Queued (sent, not yet confirmed received): {[d.arm_name for d in queued]}")
        else:
            self.output("Queued: none")
        if staged:
            self.output(f"Staged (armed for next area entry): {[d.arm_name for d in staged]}")
        else:
            self.output("Staged: none")
        settled = ext.recently_settled(10)
        self.output("Recently Settled:" if settled else "Recently Settled: none")
        for d in settled:
            self.output(f"  {d.arm_name}: settled ({d.detail})")
        return True

    def _cmd_ap_confirm_character(self) -> bool:
        """Overrides the new-character safeguard (see
        KotorContext._evaluate_character_safety) -- use this once you've
        confirmed the currently-connected character/save really is what
        you intend, despite not being a recognized name or a fresh
        level-1 start. All paused deliveries/corrections resume
        immediately once confirmed."""
        character = self.ctx.reconciler.current_character_name
        level = self.ctx.current_level
        if self.ctx._character_confirmed is True:
            self.output(f"Nothing to confirm -- {character!r} was already recognized as safe.")
            return True
        if self.ctx._character_confirmed is None:
            self.output("Nothing to confirm yet -- still waiting on the character name/level from the game.")
            return False
        self.ctx._character_confirmed = True
        self.output(f"Confirmed: proceeding with character {character!r} (level {level}). "
                    f"Paused deliveries/corrections will resume.")
        game_events_logger.info(f"[SAFEGUARD] Manually confirmed by admin: {character!r} (level {level}).")
        return True


# Outcomes meaning "we already decided what to do with this, don't
# reprocess it" -- everything except a genuine send failure, which should
# still be eligible for retry on the next reconnect.
_SETTLED_OUTCOMES = {"sent", "reconciled", "skipped_already_has_class"}


def _load_delivered_keys() -> set:
    """Reads DELIVERY_LOG_PATH (if it exists) into a set of
    (seed_name, slot, item_index) tuples already settled in a previous
    session. Keyed on (seed_name, slot), not character -- a slot name gets
    reused across many unrelated seeds in real testing (confirmed live: a
    single slot name covered 13+ different characters/seeds in this
    project's own log), so character alone can't tell an old, dead seed's
    entry apart from the current one. Entries logged before this field
    existed have seed_name=None, which can never match a real lookup (the
    live seed_name is never None), so old entries are automatically inert
    rather than needing an explicit migration to be safe. Missing/
    unreadable log = empty set, not an error -- a first run (or a deleted
    log) just means nothing's been delivered yet, which is the correct
    starting assumption."""
    keys = set()
    try:
        with open(DELIVERY_LOG_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("outcome") in _SETTLED_OUTCOMES and "index" in entry:
                    keys.add((entry.get("seed_name"), entry.get("slot"), entry["index"]))
    except FileNotFoundError:
        pass
    except OSError as e:
        game_events_logger.warning(f"[delivery log] failed to read ({e}), starting with an empty delivery history")
    return keys


def _load_known_characters() -> set:
    """Every distinct character name that has EVER appeared in the
    delivery log, regardless of outcome -- unlike _load_delivered_keys
    above (which only counts SETTLED deliveries), any entry at all proves
    we've connected to this character before. Used by the new-character
    safeguard (see KotorContext._evaluate_character_safety) to tell
    "genuinely never seen" from "we have real history for this name."
    Missing/unreadable log = empty set, same reasoning as
    _load_delivered_keys."""
    names = set()
    try:
        with open(DELIVERY_LOG_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                character = entry.get("character")
                if character:
                    names.add(character)
    except FileNotFoundError:
        pass
    except OSError as e:
        game_events_logger.warning(f"[delivery log] failed to read known characters ({e})")
    return names


_REAL_COMPANION_KEYS = {
    "bastila", "canderous", "carth", "hk47", "jolee", "juhani", "mission", "t3m4", "zaalbar",
}


def _load_recruited_companions() -> set:
    """Every (seed_name, slot, npc_key) triple whose actual join arm
    (companion_<key> -- the real CreateObject+AddPartyMember action) has a
    SETTLED delivery-log entry. Deliberately NOT the recruit-moment CHECK
    (AP|CHECK|COMPANION|N): under companion_mode=ap_gated the check fires
    before the real join (the companion only actually joins once their
    item is received), so the check alone is not proof they're in the
    party. Used by the Additional Feats feature's "is this character
    actually recruited yet" gate. Missing/unreadable log = empty set,
    same reasoning as _load_delivered_keys above.

    Keys are whitelisted against _REAL_COMPANION_KEYS (matches
    _COMPANION_NPC_CONST_ALL in generate_trampoline_batch.py) rather than
    excluded by prefix, since a retired item's arm_name can otherwise
    resurrect as a fake companion key and crash the remove_companion
    trap's lookup.

    Keyed on (seed_name, slot, npc_key), not a bare npc_key set, so a past
    admin-triggered companion_<key> test from a different seed/slot can't
    permanently mark that companion "recruited" for every later player too
    -- callers filter by the CURRENT (seed_name, slot) (see
    _is_companion_recruited / _resolve_trap's remove_companion branch),
    the same protection (seed_name, slot, index) already gives
    _delivered_keys for free. See _load_delivered_keys' own docstring for
    why (seed_name, slot) is the identity, not character."""
    keys: typing.Set[typing.Tuple[typing.Optional[str], typing.Optional[str], str]] = set()
    try:
        with open(DELIVERY_LOG_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("outcome") not in _SETTLED_OUTCOMES:
                    continue
                arm = entry.get("arm", "")
                if not arm.startswith("companion_") or arm.startswith("companion_class:"):
                    continue
                key = arm[len("companion_"):]
                if key in _REAL_COMPANION_KEYS:
                    keys.add((entry.get("seed_name"), entry.get("slot"), key))
    except FileNotFoundError:
        pass
    except OSError as e:
        game_events_logger.warning(f"[delivery log] failed to read recruited companions ({e})")
    return keys


def _load_finalized_companion_classes() -> set:
    """Every npc_key whose companion_class:<key>:<class> action has a
    SETTLED delivery-log entry -- covers BOTH CompanionClass=no_jedi/
    randomize_all's automatic follow-up (queued by
    _maybe_queue_companion_class) and jedi_companion's real "Jedi
    Training: ..." AP item, since both go through the identical
    companion_class:<key>:<class> arm shape in _do_deliver. Used by the
    Additional Feats feature's "has this companion's class actually
    settled" gate -- see KotorContext._is_companion_class_finalized for
    the full check (a companion with NO class roll pending at all is also
    considered finalized, trivially, which this loader alone can't tell --
    it only covers the "a roll existed and it landed" half).

    Keyed on (seed_name, slot, npc_key), not a bare npc_key set, same bug
    class as _load_recruited_companions: a past admin-triggered test from
    a different seed/slot must not permanently mark that companion's class
    "finalized" for every later player too -- see
    _is_companion_class_finalized for the current-(seed_name, slot) filter."""
    keys: typing.Set[typing.Tuple[typing.Optional[str], typing.Optional[str], str]] = set()
    try:
        with open(DELIVERY_LOG_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("outcome") not in _SETTLED_OUTCOMES:
                    continue
                arm = entry.get("arm", "")
                if arm.startswith("companion_class:"):
                    keys.add((entry.get("seed_name"), entry.get("slot"), arm.split(":", 2)[1]))
    except FileNotFoundError:
        pass
    except OSError as e:
        game_events_logger.warning(f"[delivery log] failed to read finalized companion classes ({e})")
    return keys


def _load_pc_class_settled() -> set:
    """(seed_name, slot) pairs for which a pc_class_soldier/scout/scoundrel
    arm (StartingClass=random_class's base-class write) has ever settled.
    Used by the Additional Feats feature's PC finalization gate -- see
    KotorContext._is_pc_class_finalized for the full check (StartingClass
    values other than random_class need no wait at all, which this loader
    alone can't tell). Previously a single global bool with no key at all
    -- fixed to key on (seed_name, slot), same reasoning as
    _load_delivered_keys, since a bare global bool would let one seed's
    settled PC class incorrectly mark every other seed/slot as settled
    too."""
    settled = set()
    try:
        with open(DELIVERY_LOG_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("outcome") in _SETTLED_OUTCOMES and entry.get("arm", "") in (
                    "pc_class_soldier", "pc_class_scout", "pc_class_scoundrel",
                ):
                    settled.add((entry.get("seed_name"), entry.get("slot")))
    except FileNotFoundError:
        pass
    except OSError as e:
        game_events_logger.warning(f"[delivery log] failed to read PC class settlement ({e})")
    return settled


def _load_failed_offline_deliveries(seed_name, slot) -> dict:
    """Reconstructs which deliveries most recently ended in
    "failed_extender_offline" for THIS (seed_name, slot) -- i.e. the
    extender socket was disconnected at the exact moment this item was
    processed (the classic case: the local game crashed, the player
    reopened it and kept playing without noticing the item never landed).
    See ExtenderBridge.send_apply()'s own docstring -- a send_apply()-
    family call only ever logs this outcome when self._writer is None,
    meaning the write never left this process at all, so re-driving it
    through the normal _deliver_item() pipeline is exactly as safe as
    processing it for the first time; no risk of a duplicate having
    already reached the game.

    Same "latest line wins" reconstruction as _load_pending_additional_
    feats below (the log is append-only in time order) -- an index whose
    latest outcome is something else (a prior manual /ap_apply, or an
    earlier automatic resend this same process already ran, already
    resolved it) is correctly excluded. Returns {index: (item_name,
    arm_name)}."""
    latest_outcome: dict = {}
    latest_pair: dict = {}
    try:
        with open(DELIVERY_LOG_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("seed_name") != seed_name or entry.get("slot") != slot:
                    continue
                index = entry.get("index")
                if index is None:
                    continue
                latest_outcome[index] = entry.get("outcome")
                latest_pair[index] = (entry.get("item"), entry.get("arm"))
    except FileNotFoundError:
        pass
    except OSError as e:
        game_events_logger.warning(f"[delivery log] failed to read ({e}), skipping automatic resend")
        return {}
    return {
        index: latest_pair[index]
        for index, outcome in latest_outcome.items()
        if outcome == "failed_extender_offline"
    }


def _load_pending_additional_feats() -> dict:
    """Reconstructs which AdditionalFeats items are still awaiting their
    recruited+class-finalized gates, by finding the LATEST log entry for
    each (seed_name, slot, index) triple with an additional_feats: arm
    (the log is append-only in time order, so later lines simply overwrite
    earlier ones for the same key here) and keeping only the ones whose
    latest outcome is still "pending" -- i.e. never resolved to a real
    send outcome (sent/failed_extender_offline/etc.) since. Returns
    {(seed_name, slot, index): (item_name, arm_name)}. Keyed on
    (seed_name, slot), not character, same reasoning as
    _load_delivered_keys. Missing/unreadable log = empty dict, same
    reasoning as _load_delivered_keys above."""
    latest: dict = {}
    try:
        with open(DELIVERY_LOG_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                arm = entry.get("arm", "")
                if not arm.startswith("additional_feats:"):
                    continue
                key = (entry.get("seed_name"), entry.get("slot"), entry.get("index"))
                latest[key] = entry
    except FileNotFoundError:
        pass
    except OSError as e:
        game_events_logger.warning(f"[delivery log] failed to read pending additional feats ({e})")
    return {
        key: (entry.get("item"), entry.get("arm"))
        for key, entry in latest.items()
        if entry.get("outcome") == "pending"
    }


def _load_pending_traps() -> dict:
    """Same shape/reasoning as _load_pending_additional_feats above, for
    trap: arms instead -- reconstructs which received Traps items
    (Options.py) are still awaiting resolution (their latest log entry's
    outcome is "pending", meaning the poll cycle hadn't completed yet
    when the process last shut down)."""
    latest: dict = {}
    try:
        with open(DELIVERY_LOG_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                arm = entry.get("arm", "")
                if not arm.startswith("trap:"):
                    continue
                key = (entry.get("seed_name"), entry.get("slot"), entry.get("index"))
                latest[key] = entry
    except FileNotFoundError:
        pass
    except OSError as e:
        game_events_logger.warning(f"[delivery log] failed to read pending traps ({e})")
    return {
        key: (entry.get("item"), entry.get("arm"))
        for key, entry in latest.items()
        if entry.get("outcome") == "pending"
    }


class KotorContext(CommonContext):
    command_processor = KotorClientCommandProcessor
    game = "KotOR"
    items_handling = 0b111  # full remote: get everything, including our own items and starting inventory

    def __init__(self, server_address, password):
        super().__init__(server_address, password)
        self.extender = ExtenderBridge(on_event=self._on_extender_event, on_connect=self._on_extender_connected)
        self.extender_task: asyncio.Task | None = None
        # New-character safeguard -- see _evaluate_character_safety() for
        # the full reasoning. Set here, before ReconciliationTracker below,
        # since its guarded callbacks read these at call time.
        self.current_level: typing.Optional[int] = None
        self._known_characters: typing.Set[str] = _load_known_characters()
        # None = not yet evaluated (waiting on name+level), True = safe to
        # proceed, False = BLOCKED pending /ap_confirm_character.
        self._character_confirmed: typing.Optional[bool] = None
        # Which character name _character_confirmed's verdict applies to --
        # lets _evaluate_character_safety() notice a mid-session character
        # change (reconnecting to a different save without restarting this
        # process) and re-evaluate from scratch, instead of a stale verdict
        # from an earlier character silently carrying over.
        self._character_confirmed_for: typing.Optional[str] = None
        self.reconciler = ReconciliationTracker(
            send_apply=self._guarded_send_apply,
            send_apply_value=self._guarded_send_apply_value,
            send_delevel=self._guarded_send_delevel,
            on_death=self._on_local_death,
        )
        self.location_tracker = LocationTracker()
        self._delivered_count = 0
        self.ui = None
        # 0=ap_gated, 1=normal, 2=none -- set from slot_data on Connect,
        # matching Options.py's CompanionMode default until then.
        self.companion_mode = 0
        # CompanionClass=no_jedi/randomize_all companion->class assignments
        # (empty for off/jedi_companion) -- set from slot_data on Connect,
        # see __init__.py's fill_slot_data().
        self.companion_class_rolls: typing.Dict[str, str] = {}
        # 0=off/1=no_jedi/2=jedi_companion/3=randomize_all -- the raw
        # CompanionClass option value, set from slot_data on Connect.
        # companion_class_rolls alone can't distinguish off from
        # jedi_companion (both leave it empty); this is needed for that
        # (see _is_companion_class_finalized).
        self.companion_class_mode = 0
        # Match Options.py's defaults until slot_data overrides them on Connect.
        self.consumable_stack_count = 3
        self.shop_item_count = 0
        # TrapLink -- see Options.py's TrapLink and
        # update_trap_link/_send_trap_link/_on_trap_link below. traps_mode is
        # the raw Traps option value (0=off/1=item_filler/2=fixed_amount);
        # an incoming link is ignored when 0. _last_trap_link_time mirrors
        # CommonContext.last_death_link: the server echoes our own Bounce
        # back to us, so the timestamp we sent is how we recognize (and
        # skip) that echo. _trap_link_counter is a decrementing synthetic
        # item index for linked traps (same negative-index trick as
        # _admin_heavy_counter) -- distinct from _admin_trap_counter so an
        # admin test and a linked receipt in the same session can't share
        # a key.
        self.trap_link = False
        self.traps_mode = 0
        self._last_trap_link_time = 0.0
        self._trap_link_counter = -1_000_000
        # Galactic Shop -- see GALACTIC_SHOP_KEY and the
        # _galactic_* methods below. _galactic_pending is the offline
        # backlog (persisted); _galactic_claims_in_flight is {claim_id:
        # attempts_so_far} for coins currently mid-round-trip with the
        # server (a Get has been sent, or a pop is awaiting its SetReply).
        self.galactic_shop = False
        self._galactic_pending: dict = _load_galactic_pending()
        self._galactic_claims_in_flight: typing.Dict[str, int] = {}
        self._galactic_claim_counter = 0
        self._galactic_status_requested = False
        # area_randomizer's bool -- set from slot_data on Connect, used to
        # regenerate ap_poll_shared.ncs for the ACTUAL connected seed (see
        # regenerate_poll_shared() above and on_package's Connected handler).
        self.area_randomizer = False
        # additional_enemies_mode's int -- set from slot_data on Connect,
        # used to regenerate ap_poll_shared.ncs's CheckBountyCount() gate
        # for the ACTUAL connected seed (see regenerate_poll_shared() above
        # and on_package's Connected handler). 0 = off, matches Options.py's
        # AdditionalEnemies default.
        self.additional_enemies_mode = 0
        # Options.py's StartingClass value -- set from slot_data on Connect,
        # used to regenerate the Dantooine make-jedi suppression wrapper
        # for the ACTUAL connected seed (see
        # regenerate_makejedi_suppressor() above).
        self.starting_class = 0
        # 0=defeat_malak, 1=true_balance, 2=max_level, 3=reach_leviathan --
        # matches Options.py's Goal default until slot_data overrides it on
        # Connect. See
        # _check_goal(): sets self.finished_game, which CommonClient's own
        # server loop turns into a real StatusUpdate(CLIENT_GOAL) send.
        self.goal = 0
        # asyncio.create_task() returns a Task the event loop only holds a
        # WEAK reference to -- per Python's own docs, an unreferenced task
        # "may get garbage collected at any time, even before it's done."
        # _check_pending_traps()/_check_pending_additional_feats() must
        # keep the return value here rather than firing create_task(...)
        # and discarding it, or the resolution can silently never happen
        # (zero error, zero confirmation log line). This set is the
        # standard fix -- keep a strong reference until the task finishes,
        # then let it drop.
        self._background_tasks: set = set()
        self._session_id = int(time.time())
        # See _on_extender_event/_watch_for_staleness -- tracks whether the
        # extender's kse.log-tail relay is actually still alive. That
        # relay thread can freeze inside the game process (game keeps
        # polling fine, but nothing reaches this client any more) with
        # zero visible symptom beyond "commands stop having any effect" --
        # this surfaces it as an explicit message instead of silent
        # confusion.
        self._last_game_event_time = time.time()
        self._staleness_warned = False
        self._staleness_task: typing.Optional[asyncio.Task] = None
        # See _watch_for_server_disconnect() below -- separate concern from
        # the extender-staleness watcher above (that one is about the GAME
        # process going quiet; this one is about the AP SERVER connection
        # itself dying silently without this client noticing or prompting
        # a reconnect).
        self._server_watch_task: typing.Optional[asyncio.Task] = None
        self._server_disconnect_warned = False
        # Loaded once at startup -- (seed_name, slot, item_index) triples
        # already settled in a previous session. Keyed on (seed_name,
        # slot), not character -- see _load_delivered_keys' docstring for
        # why. See DELIVERY_LOG_PATH.
        self._delivered_keys = _load_delivered_keys()
        # Additional Feats feature: client-side tracking of which
        # companions are actually recruited and which (seed_name, slot)
        # players' classes have settled -- see _load_recruited_companions/
        # _load_finalized_companion_classes/_load_pc_class_settled above
        # for what each one means, and _is_companion_recruited/
        # _is_companion_class_finalized/_is_pc_class_finalized below for
        # the full gating logic (a trivial "no class change applies at
        # all" case counts as finalized too, which these sets alone don't
        # capture). Loaded once at startup, updated live by _log_delivery.
        self._recruited_companions: typing.Set[typing.Tuple[typing.Optional[str], typing.Optional[str], str]] = \
            _load_recruited_companions()
        self._finalized_companion_classes: typing.Set[typing.Tuple[typing.Optional[str], typing.Optional[str], str]] = \
            _load_finalized_companion_classes()
        self._pc_class_settled: typing.Set[typing.Tuple[typing.Optional[str], typing.Optional[str]]] = \
            _load_pc_class_settled()
        # {(seed_name, slot, index): (item_name, arm_name)} for every
        # received additional_feats: item still waiting on its gates -- see
        # _load_pending_additional_feats and _check_pending_additional_feats.
        self._pending_additional_feats: typing.Dict[typing.Tuple[str, str, int], typing.Tuple[str, str]] = \
            _load_pending_additional_feats()
        # {(seed_name, slot, index): (item_name, arm_name)} for every
        # received trap: item not yet resolved -- see _load_pending_traps
        # and _check_pending_traps. Same shape as _pending_additional_feats
        # above, but every trap resolves on the very next poll cycle (no
        # recruited/class-finalized gating concept).
        self._pending_traps: typing.Dict[typing.Tuple[str, str, int], typing.Tuple[str, str]] = \
            _load_pending_traps()
        # Indices already automatically resent this PROCESS lifetime by
        # _resend_failed_offline_deliveries() -- see that method's own
        # docstring. Purely in-memory (not persisted): a genuinely new
        # process re-derives from the delivery log fresh, and correctly
        # retries again if still stuck; this set only prevents the same
        # index being resent twice within one run (e.g. two reconnects in
        # quick succession).
        self._resent_offline_indices: typing.Set[int] = set()
        # In-flight guard for HEAVY_ARMS/companion_class: sends:
        # _delivered_keys only gains an entry once _log_delivery sees a
        # SETTLED outcome, which for a class switch can be minutes away
        # (up to ~10s waiting on classes_known in _do_deliver, then
        # however long _process_heavy_queue takes to reach it, then up to
        # 10 more minutes waiting for CLASSREPORT confirmation). If
        # _deliver_item fires again for the same (character, index) inside
        # that window -- a client reconnect replaying ReceivedItems is the
        # normal trigger, not an edge case -- the _delivered_keys check
        # alone can't catch it, and a second send races ahead of the
        # first's own has_class()/CLASSREPORT confirmation, defeating that
        # safety check entirely (a reconnect can resend a class arm onto
        # an already-multiclassed character and crash the game). Not
        # persisted across restarts on purpose -- this only needs to
        # survive within one running process, and a process restart
        # naturally clears any genuinely-abandoned send back to
        # retryable.
        self._pending_heavy_indices: typing.Set[typing.Tuple[str, int]] = set()
        # HEAVY_ARMS get pushed here instead of sent immediately -- see
        # _process_heavy_queue(), started from launch(). Only one heavy
        # item is ever in flight at a time, confirmed-applied before the
        # next one sends, so the orchestrator's pending queue can never
        # accumulate more than one multiclass/party-member operation for
        # a single trampoline firing to crash on.
        self._heavy_queue: asyncio.Queue = asyncio.Queue()
        # Decrementing counter for the (character, index) identity of a
        # heavy send that didn't come from a real AP item (an admin
        # /ap_apply, or the automatic no_jedi/randomize_all companion_class
        # follow-up) -- see _queue_heavy(). Always negative, so it can
        # never collide with a real item's non-negative index, and always
        # unique per call, so back-to-back admin sends of the same arm
        # never look like duplicates to _delivered_keys.
        self._admin_heavy_counter = 0

    def _track_background_task(self, task: "asyncio.Task") -> None:
        """Pairs with self._background_tasks (see __init__) -- keeps the
        strong reference until done, THEN checks whether the task actually
        finished with an unhandled exception before discarding it.
        Without this, a real bug inside _resolve_trap()/_resolve_
        additional_feats() (unrelated to the GC issue that set exists to
        fix) would still vanish silently: asyncio's own default handler
        for an unretrieved task exception only logs through its OWN
        internal logger, not game_events_logger, so it may never actually
        surface in this console. Logs loudly instead, through the same
        channel every other visible [game]/[extender] line already uses."""
        self._background_tasks.discard(task)
        if not task.cancelled():
            exc = task.exception()
            if exc is not None:
                game_events_logger.error(f"[background task FAILED] {task.get_name()}: {exc!r}", exc_info=exc)

    def _log_delivery(self, character: str, index: int, item_name: str, arm_name: str, outcome: str) -> None:
        """Appends one line to DELIVERY_LOG_PATH and updates the in-memory
        settled-keys set for outcomes that should block reprocessing on a
        future reconnect. See DELIVERY_LOG_PATH's comment for the full
        design -- this is the primary reconnect-safety mechanism for
        everything except class switches, not just an audit trail.

        The dedup identity is (seed_name, slot), not character: a slot
        name gets reused across many unrelated seeds in real testing
        (confirmed live -- a single slot name covered 13+ different
        characters/seeds in this project's own delivery log), and a
        character-keyed set can't tell those apart. character is still
        recorded on the log line and kept as _log_delivery's own parameter
        for readability/audit, but it plays no part in the dedup key."""
        seed_name = self.seed_name
        slot = getattr(self, "username", None)
        # Release the in-flight guard regardless of outcome -- "pending"
        # (additional_feats:/trap: arms) never set this in the first place
        # (discard is a no-op then), but every HEAVY_ARMS/companion_class:
        # outcome that reaches _log_delivery ("sent", "skipped_already_has_
        # class", "failed_extender_offline", "reconciled") represents this
        # attempt reaching a terminal decision -- including the offline
        # case, which must stay retryable on the next real reconnect rather
        # than being stuck permanently "in flight."
        self._pending_heavy_indices.discard((character, index))
        if outcome in _SETTLED_OUTCOMES:
            self._delivered_keys.add((seed_name, slot, index))
            # Additional Feats feature: keep the recruited/class-finalized
            # tracking sets live, same data the startup
            # loaders derive from the log -- see those functions'
            # docstrings for why each prefix check is shaped this way.
            if arm_name.startswith("companion_class:"):
                self._finalized_companion_classes.add((seed_name, slot, arm_name.split(":", 2)[1]))
            elif arm_name.startswith("companion_"):
                self._recruited_companions.add((seed_name, slot, arm_name[len("companion_"):]))
            elif arm_name in ("pc_class_soldier", "pc_class_scout", "pc_class_scoundrel"):
                self._pc_class_settled.add((seed_name, slot))
        entry = {
            "time": time.time(),
            "session": self._session_id,
            "seed_name": seed_name,
            "slot": slot,
            "character": character,
            "index": index,
            "item": item_name,
            "arm": arm_name,
            "outcome": outcome,
        }
        try:
            with open(DELIVERY_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError as e:
            game_events_logger.warning(f"[delivery log] failed to write ({e}), continuing without it")

    def _is_companion_recruited(self, npc_key: str) -> bool:
        """Additional Feats feature: is this companion actually in the
        party yet? See _load_recruited_companions' docstring for why this
        is the join arm, not the recruit-moment check. Filtered to the
        CURRENT (seed_name, slot) -- see _load_recruited_companions'
        docstring for why the set holds (seed_name, slot, npc_key) tuples,
        not bare keys."""
        return (self.seed_name, getattr(self, "username", None), npc_key) in self._recruited_companions

    def _is_companion_class_finalized(self, npc_key: str) -> bool:
        """Additional Feats feature: has this companion's class settled --
        either a real class-change action for them has already landed, or
        none was ever coming in the first place under the current
        CompanionClass mode. See Options.py's CompanionClass for what
        each mode value means. Filtered to the CURRENT (seed_name, slot),
        same reasoning as _is_companion_recruited."""
        if (self.seed_name, getattr(self, "username", None), npc_key) in self._finalized_companion_classes:
            return True
        if self.companion_class_mode == 0:  # off -- no roll ever applies
            return True
        if self.companion_class_mode == 2:  # jedi_companion
            # Only the 4 non-Jedi companions ever get a roll under this
            # mode; the other 3 (Bastila/Jolee/Juhani) are untouched and
            # so are trivially finalized.
            return npc_key not in NON_JEDI_COMPANION_KEYS
        # no_jedi/randomize_all: every companion gets a roll, reflected in
        # companion_class_rolls -- absence there means none is coming
        # (shouldn't happen under these modes, but trivially finalized if so).
        return npc_key not in self.companion_class_rolls

    def _is_pc_class_finalized(self) -> bool:
        """Additional Feats feature: PC equivalent of
        _is_companion_class_finalized. StartingClass=random_class applies
        immediately/automatically at game start (not item-gated), so this
        is near-instantly true in practice -- tracked properly anyway
        rather than assumed."""
        if (self.seed_name, getattr(self, "username", None)) in self._pc_class_settled:
            return True
        return self.starting_class != 3  # random_class

    def _check_pending_additional_feats(self) -> None:
        """Runs once per poll cycle (see _on_extender_event's SKILLREPORT
        hook, the same "poll cycle complete" marker ReconciliationTracker
        already uses). For every still-pending additional_feats: item,
        checks whether its target is both recruited and class-finalized;
        once both clear, picks 3 random feats from ADDITIONAL_FEATS_POOL
        and hands off to _resolve_additional_feats to actually send it.
        PC has no "recruited" concept at all -- always considered present.
        Cheap to run unconditionally every cycle: this dict is normally
        empty or very small (at most 8 entries ever, one per eligible
        character).

        The draw excludes feats the target already knows -- the real grant
        NWScript also guards each one with GetHasFeat before granting, so
        skipping a known feat here just avoids wasting an item with no
        observable effect, it isn't required for correctness. This filter
        is PC-only: current_feats (FEATREPORT) only ever tracks the PC,
        never companions (no per-companion feat poll exists), so a
        companion draw can't be deduped against what they already know.

        The draw also excludes the 3 Jedi-signature feats (Force Jump/
        Force Focus/Force Immunity: Fear) whenever the target isn't
        currently Jedi -- those are dead weight on a character with no
        Force levels/Force Points to use them with. Unlike the
        already-known filter above, this check works for companions too:
        class is knowable even without a feat poll, via
        companion_class_rolls (this seed's roll, if CompanionClass
        touched them) falling back to vanilla lore (NON_JEDI_COMPANION_KEYS)
        for one it didn't."""
        if not self._pending_additional_feats:
            return
        _JEDI_ONLY_FEATS = {101, 88, 98}  # Force Jump / Force Focus / Force Immunity: Fear
        for key in list(self._pending_additional_feats.keys()):
            item_name, arm_name = self._pending_additional_feats[key]
            npc_key = arm_name.split(":", 1)[1]
            if npc_key == "pc":
                ready = self._is_pc_class_finalized()
                jedi_levels = ("guardian", "consular", "sentinel")
                is_jedi = any(self.reconciler.current_classes.get(k, 0) for k in jedi_levels)
            else:
                ready = self._is_companion_recruited(npc_key) and self._is_companion_class_finalized(npc_key)
                rolled_class = self.companion_class_rolls.get(npc_key)
                if rolled_class is not None:
                    is_jedi = rolled_class in ("guardian", "consular", "sentinel")
                else:
                    is_jedi = npc_key not in NON_JEDI_COMPANION_KEYS  # vanilla lore
            if not ready:
                continue
            pool = [f for f in ADDITIONAL_FEATS_POOL if f not in _JEDI_ONLY_FEATS or is_jedi]
            if npc_key == "pc":
                pool = [f for f in pool if f not in self.reconciler.current_feats]
            if not pool:
                del self._pending_additional_feats[key]
                self._trap_noop(key, item_name, arm_name, f"{npc_key} has no eligible feats left in the pool")
                continue
            del self._pending_additional_feats[key]
            feat_ids = random.sample(pool, min(3, len(pool)))
            task = asyncio.create_task(self._resolve_additional_feats(key, item_name, arm_name, npc_key, feat_ids))
            self._background_tasks.add(task)
            task.add_done_callback(self._track_background_task)

    async def _resolve_additional_feats(self, key: typing.Tuple[str, str, int], item_name: str, arm_name: str,
                                         npc_key: str, feat_ids: typing.List[int]) -> None:
        """The actual send, once _check_pending_additional_feats decides a
        pending item's gates have cleared. On failure (extender offline),
        puts the item back into _pending_additional_feats so the next
        poll cycle retries automatically -- no separate terminal failure
        state needed, "pending" already correctly describes "not yet
        resolved" either way."""
        _seed_name, _slot, index = key
        character = self.reconciler.current_character_name
        sent = await self.extender.send_additional_feats(npc_key, feat_ids)
        if sent:
            # See _resolve_trap's own comment on wait_staged -- same
            # real-vs-local-only confirmation gap closed the same way.
            sent = await self.extender.wait_staged(f"additional_feats:{npc_key}")
        if sent:
            logger.info(f"[queued for game] {item_name} -> additional_feats:{npc_key}:{feat_ids}")
            self._log_delivery(character, index, item_name, arm_name, "sent")
        else:
            game_events_logger.warning(f"[NOT SENT -- extender offline] {item_name} -> additional_feats:{npc_key}. "
                            f"Will retry next poll cycle.")
            self._pending_additional_feats[key] = (item_name, arm_name)

    def _check_pending_traps(self) -> None:
        """Runs once per poll cycle (see _on_extender_event's SKILLREPORT
        hook). Every pending trap resolves on the VERY NEXT cycle after
        receipt -- unlike additional_feats, there's no recruited/class-
        finalized gate to wait on; whatever state a given trap_type needs
        (current feats/powers/inventory/abilities/level/companions) is
        always current by the time a poll cycle has completed at least
        once. Cheap to run unconditionally every cycle: this dict is
        normally empty."""
        if not self._pending_traps:
            return
        for key in list(self._pending_traps.keys()):
            item_name, arm_name = self._pending_traps[key]
            trap_type = arm_name.split(":", 1)[1]
            del self._pending_traps[key]
            task = asyncio.create_task(self._resolve_trap(key, item_name, arm_name, trap_type))
            self._background_tasks.add(task)
            task.add_done_callback(self._track_background_task)

    def _trap_noop(self, key: typing.Tuple[str, str, int], item_name: str, arm_name: str, reason: str) -> None:
        """Marks a trap settled with no effect -- the "0 or 1 of
        something to halve" case Options.py's Traps docstring
        promises is a safe no-op, not a retry-forever or an error."""
        _seed_name, _slot, index = key
        game_events_logger.info(f"[trap no-op] {item_name} -> {reason}, nothing to do")
        self._log_delivery(self.reconciler.current_character_name, index, item_name, arm_name, "sent")

    async def _resolve_trap(self, key: typing.Tuple[str, str, int], item_name: str, arm_name: str, trap_type: str) -> None:
        """The actual per-trap-type computation + send, once
        _check_pending_traps decides a pending trap is ready to resolve
        (immediately, always). Every branch reads live state from
        self.reconciler.current_* (ability scores, classes/level, held
        feats/powers, backpack inventory -- all kept current by
        kotor_reconciliation.py's handle_event, see its Traps-era report
        additions) or self._recruited_companions, never generation-time
        data. On send failure (extender offline), puts the item back into
        _pending_traps so the next poll cycle retries -- same reasoning
        as _resolve_additional_feats."""
        _seed_name, _slot, index = key
        character = self.reconciler.current_character_name
        reconciler = self.reconciler
        sent = None  # tri-state: None = no-op path taken below (already logged), else bool

        if trap_type == "reduce_skill":
            # Retired cut_level's replacement -- SetXP can't reduce XP
            # below the current level's threshold once it's already
            # banked, so a level/XP trap can never be made reliable. This
            # reuses EffectSkillDecrease, the same plain-effect approach
            # used by the 5 ability traps below, picking one random
            # currently-known
            # skill (>0) and halving it -- persuade's -1 "untrained cross-
            # class" sentinel is excluded, same reasoning as skipping a
            # feat/power pool of 0-1.
            eligible = [k for k, v in reconciler.current_skills.items() if v > 0]
            if not eligible:
                self._trap_noop(key, item_name, arm_name, "no skill above 0 to reduce")
                return
            skill_key = random.choice(eligible)
            current = reconciler.current_skills[skill_key]
            decrease = current - (current // 2)
            params = f"{skill_key}:{decrease}"
            sent = await self.extender.send_trap("reduce_skill", params)

        elif trap_type == "remove_half_feats":
            held = list(reconciler.current_feats)
            if len(held) <= 1:
                self._trap_noop(key, item_name, arm_name, f"only {len(held)} known feat(s)")
                return
            chosen = random.sample(held, len(held) // 2)
            params = ",".join(str(i) for i in chosen)
            sent = await self.extender.send_trap("remove_half_feats", params)

        elif trap_type == "remove_half_powers":
            held = list(reconciler.current_powers)
            if len(held) <= 1:
                self._trap_noop(key, item_name, arm_name, f"only {len(held)} known force power(s)")
                return
            chosen = random.sample(held, len(held) // 2)
            params = ",".join(str(i) for i in chosen)
            sent = await self.extender.send_trap("remove_half_powers", params)

        elif trap_type == "cut_max_hp":
            con_decrease = _con_decrease_for_half_max_hp(reconciler.current_classes, reconciler.current_abilities)
            if con_decrease <= 0:
                self._trap_noop(key, item_name, arm_name, "Max HP already minimal (or state not yet known)")
                return
            sent = await self.extender.send_trap("cut_max_hp", str(con_decrease))

        elif trap_type == "remove_companion":
            # Filtered to the CURRENT (seed_name, slot), not the whole
            # _recruited_companions set -- otherwise a stale admin-test
            # entry from a different seed/slot could get "removed" from a
            # player who never actually had that companion. See
            # _load_recruited_companions' docstring.
            current_seed_slot = (self.seed_name, getattr(self, "username", None))
            candidates = sorted(npc for (sn, sl, npc) in self._recruited_companions
                                if (sn, sl) == current_seed_slot)
            if not candidates:
                self._trap_noop(key, item_name, arm_name, "no companions recruited yet")
                return
            target = random.choice(candidates)
            sent = await self.extender.send_trap("remove_companion", target)
            if sent:
                # Untrack immediately, not just on confirmation -- the
                # companion arms' own untrack-on-confirm equivalent
                # doesn't exist (recruit tracking only ever ADDS, see
                # _load_recruited_companions), and leaving this stale
                # would incorrectly let a later Additional Feats/
                # companion_class action target a companion that was
                # just removed.
                self._recruited_companions.discard((*current_seed_slot, target))

        elif trap_type == "remove_half_inventory":
            # Does not read reconciler.current_inventory (removed along
            # with ap_poll_shared.nss's CheckInventory(), the
            # 512-byte-truncation-prone periodic report; see
            # kotor_reconciliation.py's own removal comment). The
            # backpack walk, quest_dependent
            # exemption, and random half-selection now all happen natively
            # in NWScript at delivery time (see generate_trampoline_batch.py's
            # build_trap_block, remove_half_inventory branch) -- no params
            # needed here at all, and the 0-or-1-eligible no-op case is
            # handled gracefully in-game (nRemoved simply comes back 0).
            # NOTE: params is a placeholder "-", not "" -- ap_extender.c's
            # incoming APPLYVALUE:trap: parser uses sscanf's %s for params
            # (requires matching at least one non-whitespace char), so a
            # truly empty params string fails that parse (sscanf returns 1,
            # not 2) and the trap would silently never queue. build_trap_block
            # ignores params_str entirely for this trap_type, so any
            # non-empty placeholder is harmless.
            sent = await self.extender.send_trap("remove_half_inventory", "-")

        elif trap_type in ("reduce_str", "reduce_dex", "reduce_int", "reduce_wis", "reduce_cha"):
            ability_key = trap_type[len("reduce_"):]  # "str"/"dex"/"int"/"wis"/"cha"
            current = reconciler.current_abilities.get(ability_key, 0)
            if current <= 1:
                self._trap_noop(key, item_name, arm_name, f"{ability_key} already minimal ({current})")
                return
            decrease = current - (current // 2)
            sent = await self.extender.send_trap(trap_type, str(decrease))

        elif trap_type == "remove_credits":
            # A REAL item takes _deliver_item's direct shortcut and never
            # lands here; this branch exists for TrapLink, whose
            # locally-rolled trap can be any of the 12 and goes
            # through _pending_traps like everything else. Same
            # set_credits:0 send, same reconciler-clamp safety argument as
            # that shortcut's comment.
            sent = await self.extender.send_apply_value("set_credits", 0)

        else:
            game_events_logger.warning(f"[trap] unknown trap_type {trap_type!r} for {item_name} -- dropping.")
            self._log_delivery(character, index, item_name, arm_name, "sent")
            return

        if sent:
            # Wait for the extender's real STAGED: ack before considering
            # this settled -- see ExtenderBridge.wait_staged's docstring
            # for the casualty this closes (a write can succeed locally
            # even while the game process is already dying, silently
            # never reaching a live extender).
            staged_key = "set_credits" if trap_type == "remove_credits" else f"trap:{trap_type}"
            sent = await self.extender.wait_staged(staged_key)
        if sent:
            logger.info(f"[queued for game] {item_name} -> trap:{trap_type}")
            self._log_delivery(character, index, item_name, arm_name, "sent")
            self._send_trap_link_if_real(index, item_name)
        else:
            game_events_logger.warning(f"[NOT SENT -- extender offline] {item_name} -> trap:{trap_type}. "
                            f"Will retry next poll cycle.")
            self._pending_traps[key] = (item_name, arm_name)

    # ------------------------------------------------------------------
    # TrapLink -- Options.py's TrapLink. Same bounce-tag
    # opt-in/broadcast structure as DeathLink (CommonClient.py's
    # update_death_link/send_death/on_deathlink), different payload
    # semantics: DeathLink mirrors one shared event, TrapLink broadcasts a
    # trigger every recipient resolves into their OWN random trap. Wire
    # format matches the existing cross-game TrapLink convention (see
    # worlds/smw/Client.py): Bounce tags=["TrapLink"], data={time, source,
    # trap_name} -- so a linked non-KotOR game's traps reach us and ours
    # reach them, even though neither side can apply the other's specific
    # trap_name.
    # ------------------------------------------------------------------

    async def update_trap_link(self, trap_link: bool) -> None:
        """Mirrors CommonContext.update_death_link exactly, for the
        "TrapLink" connection tag."""
        old_tags = self.tags.copy()
        if trap_link:
            self.tags.add("TrapLink")
        else:
            self.tags -= {"TrapLink"}
        if old_tags != self.tags and self.server and not self.server.socket.closed:
            await self.send_msgs([{"cmd": "ConnectUpdate", "tags": self.tags}])

    def _send_trap_link_if_real(self, index: int, item_name: str) -> None:
        """Outgoing half. Only a REAL received Trap item (non-negative AP
        item index) broadcasts: admin /ap_apply tests and incoming linked
        traps both use negative synthetic indices, so neither re-triggers
        the link -- that's the "never ping-pong" guarantee in the option's
        docstring. Fire-and-forget, same as send_death."""
        if index < 0 or "TrapLink" not in self.tags or not self.server or self.slot is None:
            return
        asyncio.create_task(self._send_trap_link(item_name))

    async def _send_trap_link(self, trap_name: str) -> None:
        self._last_trap_link_time = time.time()
        await self.send_msgs([{
            "cmd": "Bounce", "tags": ["TrapLink"],
            "data": {
                "time": self._last_trap_link_time,
                "source": self.player_names[self.slot],
                "trap_name": trap_name,
            },
        }])
        logger.info(f"[TrapLink] sent {trap_name!r} to your linked friends")

    def _on_trap_link(self, data: dict) -> None:
        """Incoming half -- roll our own trap type and queue it through the
        normal _pending_traps path (resolves next poll cycle from live
        state, safe no-op if there's nothing to halve, exactly like a real
        Trap item). Skipped entirely when this slot has traps off, per the
        option docstring."""
        source = data.get("source", "?")
        their_trap = data.get("trap_name", "a trap")
        if self.traps_mode == 0:
            logger.info(f"[TrapLink] {source} triggered {their_trap!r} -- ignored, traps are off for this slot")
            return
        display_name, arm_name = random.choice(TRAP_LINK_CANDIDATES)
        self._trap_link_counter -= 1
        key = (self.seed_name, getattr(self, "username", None), self._trap_link_counter)
        item_name = f"(TrapLink from {source}) {display_name}"
        self._pending_traps[key] = (item_name, arm_name)
        logger.info(f"[TrapLink] {source} triggered {their_trap!r} -> rolled {display_name!r} "
                    f"for you, resolves next poll cycle")

    # ------------------------------------------------------------------
    # Galactic Shop -- Options.py's GalacticShop. The game
    # side (extender/scripts_src/ap_galtradebox.nss) only ever destroys
    # the deposited item/coin and logs one line; EVERYTHING that touches
    # the shared pool happens here, over AP Data Storage. The withdrawn
    # item is granted through the ordinary give_item path (next area
    # transition), which is also what naturally absorbs the network
    # round-trip delay the design entry flagged.
    # ------------------------------------------------------------------

    def _save_galactic_pending(self) -> None:
        try:
            with open(GALACTIC_SHOP_PENDING_PATH, "w", encoding="utf-8") as f:
                json.dump(self._galactic_pending, f)
        except OSError as e:
            game_events_logger.warning(f"[galactic shop] couldn't write {GALACTIC_SHOP_PENDING_PATH} ({e})")

    def _galactic_own_name(self) -> str:
        if self.slot is not None and self.slot in self.player_names:
            return self.player_names[self.slot]
        return getattr(self, "username", None) or "?"

    def _galactic_on_deposit(self, resref: str, count: int) -> None:
        """A real item just went into a box in-game (already destroyed
        there, coin already handed back). Build the pool record NOW so the
        depositor/time are truthful even if it can't be sent until later."""
        record_id = f"{self._galactic_own_name()}-{int(time.time() * 1000)}-{random.randint(0, 9999):04d}"
        record = {"id": record_id, "player": self._galactic_own_name(), "game": self.game,
                  "resref": resref, "count": max(1, count), "time": time.time()}
        self._galactic_pending["deposits"].append(record)
        self._save_galactic_pending()
        game_events_logger.info(f"[galactic shop] deposited {resref} x{record['count']} -> queued for the shared pool")
        asyncio.create_task(self._galactic_flush_pending())

    def _galactic_on_claim(self) -> None:
        """A Galactic Coin just went into a box in-game (already
        destroyed). Counted, then settled against the server."""
        self._galactic_pending["claims"] += 1
        self._save_galactic_pending()
        game_events_logger.info("[galactic shop] coin used -> looking for another player's item")
        asyncio.create_task(self._galactic_flush_pending())

    async def _galactic_flush_pending(self) -> None:
        """Pushes every backlogged deposit (one atomic "update" each) and
        starts a pool lookup for every backlogged claim. No-op while not
        connected -- re-run from on_package's Connected handler."""
        if not self.server or self.slot is None:
            return
        deposits = self._galactic_pending["deposits"]
        while deposits:
            record = deposits.pop(0)
            self._save_galactic_pending()
            await self.send_msgs([{
                "cmd": "Set", "key": GALACTIC_SHOP_KEY, "default": {}, "want_reply": False,
                "operations": [{"operation": "update", "value": {record["id"]: record}}],
            }])
            game_events_logger.info(f"[galactic shop] {record['resref']} x{record['count']} is now in the shared pool")
        while self._galactic_pending["claims"] > 0:
            self._galactic_pending["claims"] -= 1
            self._save_galactic_pending()
            self._galactic_claim_counter += 1
            claim_id = f"{self._galactic_own_name()}-{self._galactic_claim_counter}-{int(time.time())}"
            self._galactic_claims_in_flight[claim_id] = 0
            await self._galactic_request_pool(claim_id)

    async def _galactic_request_pool(self, claim_id: str) -> None:
        """Step 1 of a withdrawal: plain Get. The extra kotor_claim field
        is echoed back on the Retrieved packet (protocol guarantee), which
        is how _galactic_on_pool knows which claim it's answering."""
        await self.send_msgs([{"cmd": "Get", "keys": [GALACTIC_SHOP_KEY], "kotor_claim": claim_id}])

    async def _galactic_on_pool(self, claim_id: str, pool: typing.Any) -> None:
        """Step 2: filter locally (KotOR only, never our own deposits),
        pick one at random, try to atomically pop it. Empty -> default
        item, no retry (nothing to race for)."""
        if claim_id not in self._galactic_claims_in_flight:
            return
        pool = pool if isinstance(pool, dict) else {}
        own = self._galactic_own_name()
        eligible = [rec for rec in pool.values()
                    if isinstance(rec, dict) and rec.get("game") == self.game and rec.get("player") != own
                    and rec.get("resref")]
        if not eligible:
            others = sum(1 for rec in pool.values() if isinstance(rec, dict) and rec.get("player") == own)
            del self._galactic_claims_in_flight[claim_id]
            game_events_logger.info(f"[galactic shop] nothing from another KotOR player in the pool "
                                    f"({others} of your own deposit(s) waiting for someone else) -> default item")
            await self._galactic_grant(GALACTIC_SHOP_DEFAULT_ITEM[0], GALACTIC_SHOP_DEFAULT_ITEM[1], "default")
            return
        chosen = random.choice(eligible)
        await self.send_msgs([{
            "cmd": "Set", "key": GALACTIC_SHOP_KEY, "default": {}, "want_reply": True,
            "operations": [{"operation": "pop", "value": chosen["id"]}],
            "kotor_claim": claim_id, "kotor_record": chosen,
        }])

    async def _galactic_on_withdraw_reply(self, claim_id: str, record: dict, original_value: typing.Any) -> None:
        """Step 3: the SetReply for our pop. If the record was still in
        original_value, the pop was ours -- grant it. If not, someone else
        popped it first (the race the design insisted on handling): pull
        the pool again and retry, bounded by GALACTIC_SHOP_MAX_ATTEMPTS."""
        attempts = self._galactic_claims_in_flight.get(claim_id)
        if attempts is None:
            return
        original = original_value if isinstance(original_value, dict) else {}
        if record.get("id") in original:
            del self._galactic_claims_in_flight[claim_id]
            game_events_logger.info(f"[galactic shop] got {record['resref']} x{record.get('count', 1)} "
                                    f"(deposited by {record.get('player', '?')})")
            await self._galactic_grant(record["resref"], int(record.get("count", 1)), record.get("player", "?"))
            return
        attempts += 1
        if attempts >= GALACTIC_SHOP_MAX_ATTEMPTS:
            del self._galactic_claims_in_flight[claim_id]
            game_events_logger.warning(f"[galactic shop] lost the withdraw race {attempts} times in a row -> default item")
            await self._galactic_grant(GALACTIC_SHOP_DEFAULT_ITEM[0], GALACTIC_SHOP_DEFAULT_ITEM[1], "default")
            return
        self._galactic_claims_in_flight[claim_id] = attempts
        game_events_logger.info(f"[galactic shop] someone else took {record['resref']} first -- retrying ({attempts})")
        await self._galactic_request_pool(claim_id)

    async def _galactic_grant(self, resref: str, count: int, source: str) -> None:
        """Delivers through the same give_item path every gear item uses
        (build_give_item_block: granted_exempt_ + per-unit
        CreateItemOnObject), so loot_mode=destroy/replace can't eat it and
        the count is honored regardless of the item's own StackSize.
        Extender offline -> back onto the persisted backlog as a
        synthetic deposit-to-self? No: re-queued as a plain give_item
        retry would need a new mechanism, and the item is already gone
        from the pool -- so log loudly and hand it to /ap_apply instead,
        same honest gap every other offline give_item has."""
        while not self.extender.is_connected:
            # Normal sequence (the game may be mid-load); the item is
            # already ours server-side, so waiting is correct, not
            # dropping. Bounded only by the process lifetime.
            await asyncio.sleep(1.0)
        sent = await self.extender.send_apply_item(resref, count)
        if sent:
            game_events_logger.info(f"[galactic shop] {resref} x{count} (from {source}) queued -- "
                                    f"lands on your next area transition")
            asyncio.create_task(self.extender.send_notify(f"Galactic Shop: {resref} x{count}"))
        else:
            game_events_logger.warning(f"[galactic shop] extender dropped mid-send -- grant manually: "
                                       f"/ap_apply give_item:{resref}:{count}")

    def _galactic_handle_retrieved(self, args: dict) -> None:
        if args.get("kotor_shop_status") and self._galactic_status_requested:
            self._galactic_status_requested = False
            pool = args.get("keys", {}).get(GALACTIC_SHOP_KEY) or {}
            if not isinstance(pool, dict) or not pool:
                game_events_logger.info("[galactic shop] shared pool is empty")
            else:
                game_events_logger.info(f"[galactic shop] shared pool ({len(pool)} item(s)):")
                for rec in sorted(pool.values(), key=lambda r: r.get("time", 0) if isinstance(r, dict) else 0):
                    if isinstance(rec, dict):
                        game_events_logger.info(f"    {rec.get('resref')} x{rec.get('count', 1)} "
                                                f"from {rec.get('player')} ({rec.get('game')})")
        claim_id = args.get("kotor_claim")
        if claim_id:
            pool = args.get("keys", {}).get(GALACTIC_SHOP_KEY)
            asyncio.create_task(self._galactic_on_pool(claim_id, pool))

    def _galactic_handle_set_reply(self, args: dict) -> None:
        claim_id = args.get("kotor_claim")
        record = args.get("kotor_record")
        if claim_id and isinstance(record, dict):
            asyncio.create_task(self._galactic_on_withdraw_reply(claim_id, record, args.get("original_value")))

    def _on_extender_connected(self) -> None:
        """Fires on every extender socket (re)connect, including the
        automatic reconnect after the LOCAL game process restarts -- see
        ExtenderBridge's own comment on _on_connect for why this can't
        wait for the AP server's "Connected" package (that session
        usually stays open across a game crash/relaunch, so it never
        refires). Resets only the reconciler's live-polled state (see
        reset_live_state()'s own docstring) -- NOT expected_scalar/
        expected_companions/option config, which must survive a mere
        game restart and are only reset by reset_for_new_connection() on
        a genuine new AP slot Connect."""
        self.reconciler.reset_live_state()
        game_events_logger.info("[extender] reconnected -- reconciler live-state cleared, waiting for fresh reports.")
        self._resend_failed_offline_deliveries()

    def _resend_failed_offline_deliveries(self) -> None:
        """Automatic resend for deliveries that failed ONLY because the
        extender was offline at send time -- the real-world case: the
        local game crashed, the player reopened it and kept playing
        without noticing the item never actually landed (this project's
        own delivery-log warnings called this out three times over as
        "a resend mechanism (not yet built)" before this method existed).

        Safe to fire on every reconnect unconditionally: _deliver_item()
        re-applies its own full set of gates (NAMEREPORT/level wait,
        _delivered_keys/_pending_heavy_indices dedup) exactly as if this
        were a brand new ReceivedItems arrival, so re-entering it here
        can't skip a real safety check or double-apply something that
        already settled. self._resent_offline_indices only guards against
        firing the SAME resend twice within one process's life (e.g. two
        reconnects in quick succession); it deliberately isn't persisted,
        since a genuinely new process should always re-derive from the
        delivery log and retry again if still stuck."""
        seed_name = self.seed_name
        slot = getattr(self, "username", None)
        if seed_name is None:
            return
        stuck = _load_failed_offline_deliveries(seed_name, slot)
        stuck = {index: pair for index, pair in stuck.items() if index not in self._resent_offline_indices}
        if not stuck:
            return
        game_events_logger.info(
            f"[extender] retrying {len(stuck)} item(s) that failed to deliver during a previous disconnect...")
        for index, (item_name, arm_name) in stuck.items():
            if not arm_name:
                continue
            self._resent_offline_indices.add(index)
            asyncio.create_task(self._deliver_item(item_name, arm_name, index))

    def _on_extender_event(self, event: str) -> None:
        # Surface every AP| marker to its own "Heartbeat" GUI tab (not the
        # main "Archipelago" tab) -- this is the raw heartbeat/status-poll
        # firehose (XPREPORT, INVENTORY, CHECK|AREA, TRAMPOLINE_BATCH_FIRED,
        # etc.), useful for debugging but not part of the curated 4-item
        # summary (extender connecting, AP server connecting, checks found,
        # items sent) the main tab is scoped to.
        game_events_logger.info(f"[game] {event}")
        # Queue-bloat diagnostic -- see arm_orchestrator.py's
        # _push_queue_bloat_warning_to_client(). Deliberately on the main
        # visible tab (plain `logger`, not game_events_logger) rather than
        # buried in Heartbeat: this exists specifically to help notice and
        # diagnose the "extender silently died" symptom while it's
        # happening, not after the fact in a log nobody's watching.
        m = _QUEUE_BLOAT_RE.search(event)
        if m:
            logger.warning(f"[queue] WARNING: {m.group(1)} items pending confirmation -- "
                           "this usually means confirmations aren't flowing back (the "
                           "extender's relay may have stalled) rather than a real backlog. "
                           "If deliveries seem stuck, a full game relaunch is the known fix.")
        # Galactic Shop: the container script's two lines.
        # Handled regardless of self.galactic_shop -- if the box exists in
        # the player's game at all, an item already physically went into
        # it, and silently eating that would be worse than honoring it.
        m = _VOIDTRADE_DEPOSIT_RE.search(event)
        if m:
            self._galactic_on_deposit(m.group(1), int(m.group(2)))
        elif _VOIDTRADE_CLAIM_RE.search(event):
            self._galactic_on_claim()
        # Feeds _watch_for_staleness() below -- every relayed line proves
        # the extender's kse.log-tail thread is alive and forwarding right
        # now, regardless of which specific report type this is.
        self._last_game_event_time = time.time()
        self._staleness_warned = False
        # Feeds the new-character safeguard below -- see
        # _evaluate_character_safety(). Tracked here unconditionally
        # (previously only read transiently inside _check_goal's
        # max_level branch) since the safeguard needs the current level
        # regardless of which Goal option is active.
        m = _LEVEL_RE.search(event)
        if m:
            self.current_level = int(m.group(1))
        self._evaluate_character_safety()
        # Computed once per event (this runs on every single extender
        # event, a real hot path during gameplay) and reused below for
        # both location-check dedup and the ap_limited XP formula (own
        # checks completed x experience_limiter), which needs this
        # event's up-to-date count including any check THIS event itself
        # just added a moment earlier in this same method.
        already = self.checked_locations | self.locations_checked
        self.reconciler.checked_location_count = len(already)
        self.reconciler.handle_event(event)

        if "AP|SKILLREPORT|" in event:
            # Same "poll cycle complete" marker ReconciliationTracker uses
            # (poll_shared's own LAST report each cycle) -- Additional
            # Feats re-checks its pending items here rather than on every
            # single event, since recruited/class-finalized state only
            # meaningfully changes once per cycle at most.
            self._check_pending_additional_feats()
            # Traps: same "poll cycle complete" hook -- every pending
            # trap resolves on the very next cycle after receipt
            # (no gating concept the way additional_feats has, the state
            # each trap_type needs is always available by the time a poll
            # cycle finishes).
            self._check_pending_traps()

        if self.server:
            # Usually 0 or 1 id, but an alignment jump can cross several
            # 10-point thresholds in one poll -- see kotor_location_tracker.py.
            loc_ids = self.location_tracker.check_event(event, already)
            if loc_ids:
                self.locations_checked.update(loc_ids)
                for loc_id in loc_ids:
                    name = self.location_names[self.game].get(loc_id, str(loc_id))
                    logger.info(f"[check] {name}")
                asyncio.create_task(self.send_msgs([{"cmd": "LocationChecks", "locations": loc_ids}]))

                # vanilla companion mode: the check still fires (for
                # tracking), but the companion is self-granted immediately
                # instead of waiting on a received AP item -- see
                # Options.py's CompanionMode docstring.
                if self.companion_mode == 1:
                    for loc_id in loc_ids:
                        loc_data = _ID_TO_LOCATION_DATA.get(loc_id)
                        if loc_data is not None and loc_data.location_type == "companion":
                            arm_name = COMPANION_IDX_TO_ARM[loc_data.companion_idx]
                            name = self.location_names[self.game].get(loc_id, str(loc_id))
                            logger.info(f"[vanilla] auto-granting {name} -> {arm_name}")
                            # Routed through _queue_heavy -- companion_*
                            # arms are all in HEAVY_ARMS, and this path must
                            # not send straight through regardless (the same
                            # gap _cmd_ap_apply had).
                            self._queue_heavy(arm_name, f"(vanilla auto-grant) {arm_name}")
                            self._maybe_queue_companion_class(arm_name)

            self._check_goal(event)

        if self.ui is not None:
            self.ui.refresh_status()

    async def _watch_for_staleness(self) -> None:
        """Runs for the life of the connection, checking every 10s whether
        ANY line has been relayed from the extender in the last 30s. The
        extender's kse.log-tail relay thread can freeze inside the game
        process (the game itself keeps polling fine, but nothing reaches
        this client any more) with no visible symptom beyond "nothing I
        do seems to have any effect," which is indistinguishable at a
        glance from a much more common, benign cause: the game window
        losing OS focus pauses ALL of its script/dispatcher activity,
        including polling, until refocused. This can't tell the two
        apart from here (both look identical: silence), so the message
        covers both rather than guessing which one it is.
        `_staleness_warned` gates this to fire once per stall, not every
        10s -- cleared the moment a fresh event arrives."""
        while True:
            await asyncio.sleep(10)
            idle = time.time() - self._last_game_event_time
            if idle > 30 and not self._staleness_warned:
                self._staleness_warned = True
                game_events_logger.warning(
                    f"[STALE] No message from the game in {int(idle)}s. If KOTOR isn't the "
                    f"focused window, click into it -- this game pauses all script/polling "
                    f"activity while unfocused, and resumes the instant it's refocused. If "
                    f"it's already focused and this persists, the extender's own relay thread "
                    f"may have frozen inside the game process -- a client restart won't fix "
                    f"that, only a full close-and-relaunch of KOTOR itself will.")

    async def _watch_for_server_disconnect(self) -> None:
        """Runs for the life of the connection, actively checking every
        150s (2.5 min) whether the AP server connection is genuinely
        still alive. Needed because this project's own Archipelago core
        (CommonClient.py's server_loop) connects with
        `ping_interval=None, ping_timeout=None` -- the underlying
        websockets library's own automatic keepalive/liveness-check is
        deliberately disabled. With no ping/pong at all, a closed
        connection is only ever discovered passively, whenever this client
        next happens to try sending or receiving something -- if nothing
        is actively flowing, a dead connection can sit silent indefinitely
        with no visible symptom.

        Fix: actively exercise the connection on a timer instead of
        waiting for something else to eventually notice. `Sync` is a real,
        standard, already-used-elsewhere AP client command (CommonClient.py's
        own desync recovery, and several other game clients in this same
        checkout use it identically) -- harmless to send repeatedly, and
        forces a real network round trip that will surface a genuinely
        dead socket immediately via an exception, rather than waiting on
        the next real gameplay-triggered send. `_server_disconnect_warned`
        gates the log message to fire once per outage, not every 150s --
        cleared the instant a fresh Connected event starts a new watch
        cycle (see on_package's Connected handler)."""
        while True:
            await asyncio.sleep(150)
            if self._server_disconnect_warned:
                continue
            if not self.server or self.server.socket.closed:
                self._server_disconnect_warned = True
                game_events_logger.warning(
                    "[DISCONNECTED] Lost connection to the Archipelago server -- "
                    "reconnect with /connect <address> (or restart the client) to resume.")
                continue
            try:
                await self.send_msgs([{"cmd": "Sync"}])
            except Exception as e:
                self._server_disconnect_warned = True
                game_events_logger.warning(
                    f"[DISCONNECTED] Lost connection to the Archipelago server ({e}) -- "
                    f"reconnect with /connect <address> (or restart the client) to resume.")

    def _check_goal(self, event: str) -> None:
        """Sets self.finished_game once the configured Goal option's
        condition is met -- CommonClient's own server loop turns that into
        a real StatusUpdate(CLIENT_GOAL) send on its next cycle, no extra
        wiring needed here beyond setting the flag. Called after
        location_tracker.check_event() above so true_balance sees this
        event's up-to-date alignment-extreme state."""
        if self.finished_game:
            return
        if self.goal == 0:  # defeat_malak
            if _GOAL_MALAK_RE.search(event):
                game_events_logger.info("[goal] Malak defeated -- goal complete!")
                self.finished_game = True
        elif self.goal == 1:  # true_balance
            if self.location_tracker.true_balance_reached(self.checked_locations | self.locations_checked):
                game_events_logger.info("[goal] True Balance reached (both alignment extremes) -- goal complete!")
                self.finished_game = True
        elif self.goal == 2:  # max_level
            m = _LEVEL_RE.search(event)
            if m and int(m.group(1)) >= MAX_LEVEL:
                game_events_logger.info(f"[goal] Max level ({MAX_LEVEL}) reached -- goal complete!")
                self.finished_game = True
        elif self.goal == 3:  # reach_leviathan
            m = _GOAL_LEVIATHAN_RE.search(event)
            if m and int(m.group(1)) >= 99:
                game_events_logger.info("[goal] Captured by the Leviathan -- goal complete!")
                self.finished_game = True

    def _on_local_death(self) -> None:
        """Called by ReconciliationTracker once per death episode -- see its
        _cycle_saw_death/_was_dead dedup. Outgoing DeathLink half."""
        asyncio.create_task(self.send_death("died in the Star Wars galaxy."))

    def on_deathlink(self, data: dict) -> None:
        """Incoming DeathLink half -- another linked player died, kill this
        one too via the force_death arm (see extender/scripts_src and
        generate_trampoline_batch.py's APPLIES[32])."""
        super().on_deathlink(data)
        if self.extender.is_connected:
            asyncio.create_task(self.extender.send_apply("force_death"))
        else:
            game_events_logger.warning("DeathLink received but extender isn't connected -- not applied.")

    async def server_auth(self, password_requested: bool = False):
        if password_requested and not self.password:
            await super().server_auth(password_requested)
        await self.get_username()
        await self.send_connect()

    def on_package(self, cmd: str, args: dict):
        super().on_package(cmd, args)
        if cmd == "Bounced":
            # TrapLink incoming half -- same shape as
            # CommonClient's own DeathLink dispatch just above this in
            # process_server_cmd: skip our own echoed bounce via the
            # timestamp we sent (and the source name, belt and braces).
            tags = args.get("tags", [])
            if "TrapLink" in tags and "TrapLink" in self.tags:
                data = args.get("data", {}) or {}
                if data.get("time") != self._last_trap_link_time and data.get("source") != self._galactic_own_name():
                    self._on_trap_link(data)
        if cmd == "Retrieved":
            self._galactic_handle_retrieved(args)
        if cmd == "SetReply" and args.get("key") == GALACTIC_SHOP_KEY:
            self._galactic_handle_set_reply(args)
        if cmd == "RoomInfo":
            # Uses RoomInfo's own "seed_name" field rather than
            # self.server_seed_name, a CommonContext attribute present
            # only on Archipelago's unreleased main-branch dev snapshot
            # and absent from every tagged release. RoomInfo's seed_name
            # is genuine, long-standing network-protocol data present
            # across every version -- capturing it here (RoomInfo always
            # arrives before Connected) is a version-safe replacement
            # that doesn't depend on which CommonContext attributes
            # happen to exist.
            self.seed_name = args.get("seed_name") or self.seed_name
        if cmd == "Connected":
            # _delivered_count must be reset here, not just in __init__:
            # switching to a DIFFERENT slot without restarting this Python
            # process (e.g. WaterKnight after FireKnight) otherwise
            # silently skips delivering any item whose index in the NEW
            # slot's ReceivedItems list falls below whatever
            # _delivered_count already reached in the PREVIOUS slot's
            # session. self.items_received itself IS correctly re-scoped
            # per-slot by CommonContext, so this bug is invisible unless
            # counts are compared across a real slot switch. Reset here,
            # at the very start of Connected handling, so every fresh
            # connection (new slot OR reconnecting to the same one)
            # re-processes its own full ReceivedItems list from scratch
            # rather than trusting a stale count from whatever slot
            # connected before it in this same process.
            self._delivered_count = 0
            # Same bug, generalized: self.reconciler's own internal state
            # (expected_scalar/expected_skills/expected_companions,
            # current_classes/current_character_name, every in-flight dedup
            # guard) had the identical "only ever set in __init__" flaw --
            # see reset_for_new_connection()'s own docstring for the full
            # writeup. Reset alongside _delivered_count above so both halves
            # of the delivery pipeline start genuinely clean together.
            self.reconciler.reset_for_new_connection()
            # _pending_heavy_indices is the one remaining in-process-only
            # dedup guard still keyed on bare character (see its own
            # comment on why: it never needs to survive a restart, only
            # this running process). A slot switch without a restart could
            # otherwise leave a PREVIOUS slot's in-flight heavy send
            # permanently blocking that same (character, index) pair from
            # ever being considered for the new slot -- clearing here,
            # same as _delivered_count/reset_for_new_connection above,
            # guarantees a genuinely clean slate on every fresh connection.
            self._pending_heavy_indices.clear()
            slot_data = args.get("slot_data", {}) or {}
            write_slot_data_for_patch_scripts(
                slot_data.get("loot_mode", 0), slot_data.get("door_mapping"),
                bool(slot_data.get("area_randomizer", False)), slot_data.get("starting_class", 0),
                slot_data.get("additional_enemies_mode", 0), self.seed_name,
                bool(slot_data.get("progression_system", False)),
                bool(slot_data.get("galactic_shop", False)),
                bool(slot_data.get("new_companion", False)))
            self.companion_mode = slot_data.get("companion_mode", 0)
            self.companion_class_rolls = slot_data.get("companion_class_rolls", {})
            self.companion_class_mode = slot_data.get("companion_class_mode", 0)
            # "Companion Recruited: HK-47" and "Companion Recruited: New
            # Companion" share the same companion_idx (3) in location_table
            # (see Locations.py) -- LocationTracker built its _companion_index
            # from the raw, unfiltered module table at __init__ time, before
            # slot_data existed, so index 3 defaulted to whichever of the two
            # names is LAST in that dict regardless of this seed's real
            # option. Must be corrected here, the first point slot_data is
            # actually known, or the client would report the wrong location
            # name for every companion_idx=3 check under whichever choice
            # didn't win the dict-iteration-order default.
            self.location_tracker.set_new_companion(bool(slot_data.get("new_companion", False)))
            asyncio.get_event_loop().run_in_executor(None, self._apply_new_companion_assets_and_log)
            self.reconciler.experience_mode = slot_data.get("experience_mode", 0)
            self.reconciler.experience_limiter = slot_data.get("experience_limiter", 600)
            self.reconciler.experience_item = slot_data.get("experience_item", 4000)
            self.reconciler.credit_mode = slot_data.get("credit_mode", 0)
            self.reconciler.credit_limiter = slot_data.get("credit_limiter", 100)
            self.reconciler.credit_item = slot_data.get("credit_item", 5000)
            self.consumable_stack_count = slot_data.get("consumable_stack_count", 3)
            self.shop_item_count = slot_data.get("shop_item_count", 0)
            self.goal = slot_data.get("goal", 0)
            asyncio.create_task(self.update_death_link(bool(slot_data.get("death_link", False))))
            # TrapLink / Galactic Shop -- see fill_slot_data.
            self.trap_link = bool(slot_data.get("trap_link", False))
            self.traps_mode = int(slot_data.get("traps_mode", 0))
            asyncio.create_task(self.update_trap_link(self.trap_link))
            self.galactic_shop = bool(slot_data.get("galactic_shop", False))
            asyncio.get_event_loop().run_in_executor(None, self._apply_galactic_shop_and_log)
            # Anything deposited/claimed while this client was offline (or
            # before this Connect) settles now.
            asyncio.create_task(self._galactic_flush_pending())

            if self._staleness_task is None or self._staleness_task.done():
                self._last_game_event_time = time.time()
                self._staleness_warned = False
                self._staleness_task = asyncio.create_task(self._watch_for_staleness())

            if self._server_watch_task is None or self._server_watch_task.done():
                self._server_disconnect_warned = False
                self._server_watch_task = asyncio.create_task(self._watch_for_server_disconnect())

            self.area_randomizer = bool(slot_data.get("area_randomizer", False))
            self.additional_enemies_mode = slot_data.get("additional_enemies_mode", 0)
            asyncio.get_event_loop().run_in_executor(
                None, self._regenerate_poll_shared_and_log, self.area_randomizer, self.additional_enemies_mode)

            self.starting_class = slot_data.get("starting_class", 0)
            asyncio.get_event_loop().run_in_executor(
                None, self._regenerate_makejedi_suppressor_and_log, self.starting_class)

            # write_slot_data_for_patch_scripts above already wrote this
            # connection's real loot_mode/door_mapping/
            # additional_enemies_mode/seed_name synchronously before this
            # point, so it's safe to fire the module-RIM patches here the
            # same way poll_shared/makejedi already do -- gated by a
            # fingerprint of the actual relevant slot_data fields, not
            # bare seed_name (see _slot_data_fingerprint()'s docstring:
            # this project's own test workflow can reuse the same
            # seed_name across differently-configured connects, e.g.
            # loot_mode changing while seed_name stays identical, which a
            # bare-seed_name gate would silently miss) so a
            # truly-unchanged reconnect doesn't re-pay the full RIM-sweep
            # cost every launch (see PATCHED_SEEDS_MARKER_PATH).
            # Sequenced, not run as independent run_in_executor calls --
            # see _apply_module_rim_patches_in_order's own docstring for
            # the data-loss race this closes.
            patch_gate_key = _slot_data_fingerprint(slot_data)
            asyncio.get_event_loop().run_in_executor(
                None, self._apply_module_rim_patches_in_order, patch_gate_key, False)

            # Always sent, even when every planet's list is empty (a
            # shop_randomizer=off seed): _shop_stock.json persists on disk
            # across sessions/seeds, so skipping the send for an empty
            # dict would leave a PREVIOUS seed's stock in place
            # indefinitely when reconnecting to one with shop_randomizer
            # off. __init__.py's _shop_stock() always returns real
            # (possibly empty) lists for all 5 planets so every fresh
            # Connect unconditionally overwrites all of them with the
            # current seed's real answer.
            shop_stock = slot_data.get("shop_stock") or {}
            asyncio.create_task(self._send_shop_stock_when_ready(shop_stock))

            # Best-effort in-game confirmation, independent of whether the
            # extender is connected yet (send_notify no-ops silently if
            # not) -- shows on the player's next area transition, same lag
            # as every other notify/grant.
            asyncio.create_task(self.extender.send_notify("Connected to AP Server"))

            lookup = self.location_names[self.game]
            n_locations = len([lid for lid in lookup if lid >= 0])
            game_events_logger.info("")
            game_events_logger.info(f"Connected. {n_locations} locations tracked (auto-detected from game state --")
            game_events_logger.info("see /ap_locations for the full list, or /ap_status for progress).")
            game_events_logger.info("")
            game_events_logger.info("Try: /ap_status      (extender connection + delivery status)")
            game_events_logger.info("Try: /ap_apply credits  (admin: apply directly, bypassing AP)")
            game_events_logger.info("Try: /ap_check <name>   (manual override -- normally checks fire automatically)")
        if cmd == "ReceivedItems":
            # NOT args["items"] -- that's only the full cumulative list on
            # the very first connect (index=0); every later push sends just
            # the delta with a nonzero index. self.items_received is
            # CommonContext's own list, already correctly assembled by
            # respecting that index (see CommonClient.py's ReceivedItems
            # handling, which runs before on_package). Slicing args["items"]
            # directly would silently drop every delivery after the first.
            for index, network_item in enumerate(self.items_received[self._delivered_count:], start=self._delivered_count):
                item_name = self.item_names.lookup_in_game(network_item.item, self.game)
                arm_name = ITEM_NAME_TO_ARM.get(item_name)
                if arm_name is None:
                    game_events_logger.warning(f"Received {item_name!r} but no extender mapping exists for it yet -- skipped.")
                    continue
                asyncio.create_task(self._deliver_item(item_name, arm_name, index))
            self._delivered_count = len(self.items_received)
        if self.ui is not None:
            self.ui.refresh_status()

    async def _send_shop_stock_when_ready(self, planet_stock: typing.Dict[str, typing.List[str]]) -> None:
        """Set once per Connect -- see SHOPSTOCK: in kotor_extender_bridge.py.
        Waits for the extender rather than dropping the send if the game
        isn't up yet at connect time (a normal sequence, not an edge case --
        see the same reasoning for the unbounded NAMEREPORT wait below).
        Safe to resend on reconnect: the orchestrator just overwrites the
        same _shop_stock.json entries and force-regenerates, no dedup
        needed. planet_stock is {planet_name: [resrefs]} -- one distinct
        catalog per planet, not a single universal list."""
        while not self.extender.is_connected:
            await asyncio.sleep(1.0)
        await self.extender.send_shop_stock(planet_stock)

    async def _deliver_item(self, item_name: str, arm_name: str, index: int) -> None:
        # Wait for the first NAMEREPORT -- the delivery-log gate below needs
        # a character name to key on, and there's no sound fallback if we
        # don't have one (a bounded timeout here previously "failed open"
        # by processing with character=None, which can never match a real
        # name later and silently defeated the whole dedup for anything
        # that arrived before the game had actually launched -- connecting
        # the AP client before the game is up is a normal sequence, not an
        # edge case, so this can't be a short wait).
        # Unbounded is fine -- this is one lightweight sleeping task per
        # item, not something blocking anything else, and it resolves
        # naturally the moment the player launches the game.
        while self.reconciler.current_character_name is None:
            await asyncio.sleep(0.5)
        character = self.reconciler.current_character_name

        # New-character safeguard -- wait for a level too
        # (needed to evaluate safety, see _evaluate_character_safety), and
        # if the character turns out to be unrecognized and not a fresh
        # level-1 start, keep waiting here rather than proceeding -- this
        # item's delivery is paused, not dropped, until a human runs
        # /ap_confirm_character (or reconnects with the right save,
        # meaning current_character_name changes and gets re-evaluated
        # from scratch). Same "normal sequence, not an edge case" reasoning
        # as the NAMEREPORT wait above -- unbounded is fine, this is one
        # lightweight sleeping task per item.
        while self.current_level is None:
            await asyncio.sleep(0.5)
        while self._character_confirmed is False:
            await asyncio.sleep(2.0)

        if arm_name in ("xp", "credits"):
            # MUST run every session regardless of the delivery-log gate:
            # expected_scalar is pure in-memory accounting with no
            # persistence of its own, rebuilt from note_item_received()
            # calls. Gating this the same way as real one-time arm sends
            # would leave expected_scalar["xp"] at 0 on a fresh process
            # even though XP had legitimately been earned, and since both
            # xp AND credits clamps are bidirectional, the very next area
            # transition/poll would queue a corrective set_xp/set_credits
            # down to the stale expected value -- a real, immediate risk
            # of wiping out already-earned XP or credits, not just a
            # bookkeeping quirk. Safe to always replay: this has no real
            # one-time side effect, just updates a counter.
            self.reconciler.note_item_received(arm_name)
            game_events_logger.info(f"[queued for game] {item_name} -> {arm_name} (applied via reconciliation)")
            self._log_delivery(character, index, item_name, arm_name, "reconciled")
            return

        # Primary reconnect-safety gate for everything except class
        # switches: if this exact (seed_name, slot, index) was already
        # settled in a previous session, don't reprocess it at all -- no
        # expected-total update, no send. A fresh (seed_name, slot) (never
        # in the log) still gets everything; reconnecting to the same one
        # doesn't replay it. See _log_delivery's docstring for why the key
        # is (seed_name, slot), not character.
        if (self.seed_name, getattr(self, "username", None), index) in self._delivered_keys:
            game_events_logger.info(f"[already delivered] {item_name} -> {arm_name} (character {character!r}, item #{index})")
            return

        if (character, index) in self._pending_heavy_indices:
            # A previous call already queued this exact item and it hasn't
            # settled yet (see _pending_heavy_indices' own comment) -- this
            # is the reconnect-replay case, not a genuinely new send. Don't
            # requeue; the in-flight one will settle (or time out) and
            # _log_delivery will clear this on its own.
            game_events_logger.info(f"[already queued] {item_name} -> {arm_name} still waiting on prior send to confirm")
            return

        if arm_name.startswith("additional_feats:"):
            # Additional Feats: doesn't send anything to the
            # game yet -- the item is just a marker. Record it as pending
            # (a NON-settled outcome, so a reconnect before its gates clear
            # correctly re-establishes this same wait rather than being
            # treated as a brand new item OR as already-delivered) and let
            # _check_pending_additional_feats (run every poll cycle, see
            # _on_extender_event's SKILLREPORT hook) pick it up once the
            # target character is both recruited and their class has
            # settled.
            self._pending_additional_feats[(self.seed_name, getattr(self, "username", None), index)] = (item_name, arm_name)
            self._log_delivery(character, index, item_name, arm_name, "pending")
            game_events_logger.info(f"[pending] {item_name} -> waiting on recruited+class-finalized")
            return

        if arm_name == "trap:remove_credits":
            # The one trap that's a byte-for-byte reuse of an
            # already-existing action (set_credits) -- no new wire action,
            # no pending/resolution step needed, just fire it directly.
            # Zeroing credits is safe under credit_mode's reconciliation
            # clamp too: the existing purchase-detection logic
            # (kotor_reconciliation.py) treats ANY drop in credits between
            # polls as legitimate spend and folds it into
            # _cumulative_credit_spend, which both ap_limited and ap_gated
            # already subtract from their expected total -- the clamp
            # won't fight this.
            sent = await self.extender.send_apply_value("set_credits", 0)
            if sent:
                # See _resolve_trap's own comment on wait_staged -- same
                # real-vs-local-only confirmation gap closed the same way.
                sent = await self.extender.wait_staged("set_credits")
            outcome = "sent" if sent else "failed_extender_offline"
            self._log_delivery(character, index, item_name, arm_name, outcome)
            game_events_logger.info(f"[queued for game] {item_name} -> set_credits:0 (trap:remove_credits)")
            if sent:
                self._send_trap_link_if_real(index, item_name)
            return

        if arm_name.startswith("trap:"):
            # Every other trap (Options.py's Traps): the item is
            # just a marker, same "decided client-side at delivery" shape
            # as additional_feats -- _check_pending_traps (run every poll
            # cycle) computes the real specifics from currently-tracked
            # state and resolves it, no gating needed (unlike
            # additional_feats' recruited/class-finalized wait).
            self._pending_traps[(self.seed_name, getattr(self, "username", None), index)] = (item_name, arm_name)
            self._log_delivery(character, index, item_name, arm_name, "pending")
            game_events_logger.info(f"[pending] {item_name} -> resolving next poll cycle")
            return

        if arm_name in HEAVY_ARMS or arm_name.startswith("companion_class:"):
            # Multiclassing/level-up-GUI/party-member arms don't send
            # immediately: batching several of these together (even all
            # first-time applications, no repeats involved) crashes the
            # game. Queued instead; _process_heavy_queue() sends one at a
            # time, waiting for each to actually confirm-applied before
            # the next one goes out, so the pending queue can never
            # accumulate more than one of these for a single trampoline
            # firing to crash on.
            #
            # companion_class: hits the EXACT same crash risk (a real
            # jedi_companion item's companion_class:carth:guardian can
            # land in a batch alongside unrelated grants) despite doing an
            # equally heavy SetCreatureField+4-feat-array write, but is
            # never in HEAVY_ARMS itself -- a plain `in HEAVY_ARMS` check
            # can never match a colon-parameterized string, so this needs
            # its own explicit prefix check, not just a set entry.
            self._pending_heavy_indices.add((character, index))
            await self._heavy_queue.put((item_name, arm_name, index, character))
            return

        await self._do_deliver(item_name, arm_name, index, character)

    def _gear_item_count(self, resref: str) -> int:
        """Equipment (has a real equipment_slot) always grants exactly 1 --
        it doesn't make sense to grant multiples of something you can only
        wear/wield one of. Consumables grant consumable_stack_count, capped
        by the item's own real in-game stack_limit either way. Unknown
        resref (gear_items.json missing/edited out from under a live seed)
        falls back to 1 rather than guessing higher."""
        data = GEAR_ITEMS.get(resref)
        if data is None:
            return 1
        if data.get("equipment_slot"):
            return 1
        stack_limit = data.get("stack_limit") or 1
        return max(1, min(self.consumable_stack_count, stack_limit))

    def _regenerate_poll_shared_and_log(self, area_randomizer: bool, additional_enemies_mode: int = 0) -> None:
        """Runs regenerate_poll_shared() (a blocking subprocess call, hence
        this being invoked via run_in_executor from on_package rather than
        awaited directly) and logs the outcome either way -- see
        regenerate_poll_shared()'s own docstring for why this exists.
        Also callable directly from _cmd_ap_regen_poll as the manual
        fallback, using whatever area_randomizer/additional_enemies_mode
        this context currently has cached from the last Connected."""
        ok, msg = regenerate_poll_shared(area_randomizer, additional_enemies_mode)
        if ok:
            game_events_logger.info(f"[poll_shared] regenerated for area_randomizer={area_randomizer}, "
                                     f"additional_enemies_mode={additional_enemies_mode}: {msg}")
        else:
            game_events_logger.warning(f"[poll_shared] regeneration FAILED (area_randomizer={area_randomizer}, "
                                        f"additional_enemies_mode={additional_enemies_mode}): {msg}")

    def _regenerate_makejedi_suppressor_and_log(self, starting_class: int) -> None:
        """Same shape as _regenerate_poll_shared_and_log above, for the
        Dantooine make-jedi suppression wrapper -- see
        regenerate_makejedi_suppressor()'s docstring. Also callable
        directly from _cmd_ap_regen_makejedi as the manual fallback."""
        ok, msg = regenerate_makejedi_suppressor(starting_class)
        if ok:
            game_events_logger.info(f"[makejedi] regenerated for starting_class={starting_class}: {msg}")
        else:
            game_events_logger.warning(f"[makejedi] regeneration FAILED (starting_class={starting_class}): {msg}")

    def _apply_seed_patch_if_new(self, key: str, gate_key: str | None, apply_fn, force: bool = False) -> None:
        """Shared gate for the 3 heavier per-seed patch scripts (item
        suppression, door randomization, additional enemies) -- see
        PATCHED_SEEDS_MARKER_PATH's docstring for why these are gated
        rather than always re-run like poll_shared/makejedi. `gate_key` is
        a `_slot_data_fingerprint()` hash, NOT the bare seed_name (see that
        function's docstring for the real live bug this fixes -- this
        project's own testing workflow reuses the same seed_name across
        differently-configured connects, so seed_name alone can't be
        trusted to mean "same options"). `force=True` (the manual
        admin-command fallback) bypasses the marker check entirely --
        always re-applies regardless of what's recorded, then updates the
        marker same as a normal run. A missing/unknown gate_key (shouldn't
        happen by the time Connected fires, but matches this project's
        general "log and continue rather than raise from a background
        task" style for anything running via run_in_executor) still
        applies once and records whatever was given, rather than silently
        skipping forever."""
        if not force and gate_key is not None and _load_patched_seed(key) == gate_key:
            game_events_logger.info(f"[{key}] already applied for this option set -- skipping re-run.")
            return
        ok, msg = apply_fn()
        if ok:
            game_events_logger.info(f"[{key}] applied: {msg}")
            _save_patched_seed(key, gate_key)
        else:
            game_events_logger.warning(f"[{key}] APPLY FAILED: {msg}")

    def _apply_module_rim_patches_in_order(self, gate_key: str | None, force: bool = False) -> None:
        """Runs all 4 module-RIM-editing patch scripts (item_suppression,
        loot_disturb, door_randomizer, additional_enemies) SEQUENTIALLY in
        one executor task, rather than as 4 independent run_in_executor
        calls that would race each other as separate OS subprocesses with
        no ordering guarantee.

        Necessary because all 4 scripts share the same backup directory
        (extender/backup/modules/ -- every one of them sets
        BACKUP_DIR/LOCKER_BACKUP_DIR to that identical path).
        patch_additional_enemies.py and the others always read the LIVE
        .rim unconditionally and only use the backup as a --restore
        snapshot -- but patch_loot_disturb.py's own
        apply_module_rim_contents() is the one outlier: it reads FROM THE
        BACKUP instead of live whenever one already exists, specifically
        so a second loot_disturb run doesn't compound its own prior edits.
        If additional_enemies ran first (creating that shared backup as a
        side effect of placing new enemies into the live .rim),
        loot_disturb would then read that backup -- the PRISTINE,
        pre-additional-enemies state -- process it, and write its own
        result back to live, SILENTLY ERASING every enemy
        additional_enemies had just placed. Not just stale loot -- a real
        data-loss race with no ordering guarantee to prevent it.

        Fix: loot_disturb always runs FIRST, before anything else can
        create that shared backup out from under it. The other 3 read live
        unconditionally, so their relative order among themselves is safe
        either way -- kept in their original order (item_suppression,
        door_randomizer, additional_enemies) for minimal behavior change.
        Running them one at a time (rather than as 4 concurrent
        subprocess.run() calls competing for the same disk/CPU) also
        avoids needlessly loading the client process on apply.

        The trampoline owner-check runs LAST, deliberately after all 4
        patches finish rather than as its own independent Connect-time
        executor call -- it also writes into the Override folder (see
        reset_trampolines_if_owner_changed()), and this project's own
        docs/MODE_DEPENDENCIES.md documents Override as a GLOBAL, no-
        module-scoping surface where an unordered second writer is exactly
        the class of race this method exists to prevent for the 4 patches
        above. Same reasoning applies to a 5th writer."""
        self._apply_loot_disturb_and_log(gate_key, force)
        self._apply_item_suppression_and_log(gate_key, force)
        self._apply_door_randomizer_and_log(gate_key, force)
        self._apply_additional_enemies_and_log(gate_key, force)
        self._reset_trampolines_and_log()

    def _apply_item_suppression_and_log(self, gate_key: str | None, force: bool = False) -> None:
        """Runs apply_item_suppression() (a blocking subprocess call,
        hence run_in_executor from on_package rather than awaited
        directly), gated by _apply_seed_patch_if_new. Also callable
        directly (force=True) from the manual admin-command fallback.
        Only drives Progression System's checkpoint wrappers now, see
        apply_item_suppression()'s own docstring."""
        self._apply_seed_patch_if_new("item_suppression", gate_key, apply_item_suppression, force)

    def _apply_loot_disturb_and_log(self, gate_key: str | None, force: bool = False) -> None:
        """Same shape as _apply_item_suppression_and_log, for
        apply_loot_disturb() -- the real destroy/bonus/replace loot
        handling now lives here, not in item_suppression."""
        self._apply_seed_patch_if_new("loot_disturb", gate_key, apply_loot_disturb, force)

    def _apply_door_randomizer_and_log(self, gate_key: str | None, force: bool = False) -> None:
        """Same shape as _apply_item_suppression_and_log, for
        apply_door_randomizer()."""
        self._apply_seed_patch_if_new("door_randomizer", gate_key, apply_door_randomizer, force)

    def _apply_additional_enemies_and_log(self, gate_key: str | None, force: bool = False) -> None:
        """Same shape again, for apply_additional_enemies()."""
        self._apply_seed_patch_if_new("additional_enemies", gate_key, apply_additional_enemies, force)

    def _reset_trampolines_and_log(self) -> None:
        """See reset_trampolines_if_owner_changed()'s own docstring for
        what this guards against. No-ops silently if seed_name/slot aren't
        known yet (shouldn't happen at the point this is called, since
        RoomInfo/Connected always precede it, but a missing value here
        should never crash the patch chain over a cosmetic ordering
        concern)."""
        seed_name = self.seed_name
        slot = getattr(self, "username", None)
        if not seed_name or not slot:
            return
        ok, msg = reset_trampolines_if_owner_changed(seed_name, slot)
        if ok:
            game_events_logger.info(f"[trampoline owner check] {msg}")
        else:
            game_events_logger.warning(f"[trampoline owner check] FAILED -- {msg}")

    def _apply_new_companion_assets_and_log(self) -> None:
        """apply_new_companion_assets() on every Connect, same not-seed-
        gated reasoning as _apply_galactic_shop_and_log() -- must be able
        to restore the vanilla trigger the instant a later seed turns
        new_companion back off. Runs in an executor like the other patch
        scripts (subprocess call, must never block the event loop)."""
        ok, msg = apply_new_companion_assets()
        if ok:
            game_events_logger.info(f"[new companion] {msg}")
        else:
            game_events_logger.warning(f"[new companion] PATCH FAILED -- {msg}\n"
                                       f"  (run /ap_apply_new_companion to retry once fixed)")

    def _apply_galactic_shop_and_log(self) -> None:
        """apply_galactic_shop() on every Connect (not seed-gated -- one
        module, idempotent, and it has to be able to RESTORE vanilla when
        a later seed turns the option off, which a once-per-seed marker
        would skip). Runs in an executor like the other patch scripts."""
        ok, msg = apply_galactic_shop()
        if ok:
            game_events_logger.info(f"[galactic shop] {msg}")
        else:
            game_events_logger.warning(f"[galactic shop] PATCH FAILED -- {msg}\n"
                                       f"  (run /ap_apply_galactic_shop to retry once fixed)")

    def _queue_heavy(self, arm_name: str, label: str) -> None:
        """The ONE place any heavy send not already going through
        _deliver_item's real-item path enters _heavy_queue -- used by the
        automatic no_jedi/randomize_all companion_class follow-up below and
        by /ap_apply's admin bypass. A companion_class send that skips
        this queue can land in the same TRAMPOLINE_BATCH_FIRED batch as
        unrelated grants and crash the game -- the exact same crash class
        HEAVY_ARMS/_heavy_queue exists to prevent for
        class_guardian/companion_carth/etc.; companion_class: needs its
        own routing here since it's a colon-parameterized string, not a
        static HEAVY_ARMS entry. Rather than have three separate call
        sites each remember to check HEAVY_ARMS/route correctly (and risk
        a fourth future call site forgetting to), every non-real-item
        heavy send funnels through here. item_name/character are cosmetic
        (log/delivery-log labels only) for an admin-or-automatic send with
        no real AP item behind it; index is a unique negative counter so
        it can never collide with a real item's index or with another
        admin send of the same arm in _delivered_keys.

        Also gated on the new-character safeguard -- an admin/auto heavy
        send is just as capable of mutating the wrong character's state
        as a real item delivery is, so it gets the same
        pause-until-confirmed treatment. See _evaluate_character_safety().

        Records the real current character (or None if genuinely not
        known yet), not a hardcoded None -- purely for the delivery log's
        readable "character" field (see _log_delivery); the actual
        recruited/class-finalized dedup is scoped to (seed_name, slot),
        not character (see _load_recruited_companions' docstring)."""
        if self._character_confirmed is False:
            game_events_logger.warning(f"[SAFEGUARD] Skipping {arm_name!r} -- unrecognized character, "
                            f"run /ap_confirm_character first if this is intentional.")
            return
        self._admin_heavy_counter -= 1
        character = self.reconciler.current_character_name
        asyncio.create_task(self._heavy_queue.put(
            (label, arm_name, self._admin_heavy_counter, character)))

    async def _guarded_send_apply(self, arm_name: str) -> bool:
        """Wraps ExtenderBridge.send_apply for ReconciliationTracker's own
        corrective sends (skills/credits/etc.) -- see
        _evaluate_character_safety(). The reconciler runs synchronously off
        each incoming event rather than as its own sleeping task, so it
        gets a no-op-and-log instead of _deliver_item's wait-and-retry;
        the reconciler already tolerates a send returning False gracefully
        (same as an offline extender), and it'll naturally retry on its own
        next tick once confirmed anyway."""
        if self._character_confirmed is False:
            game_events_logger.warning(f"[SAFEGUARD] Skipping reconciliation send ({arm_name!r}) -- "
                            f"unrecognized character, run /ap_confirm_character first if this is intentional.")
            return False
        return await self.extender.send_apply(arm_name)

    async def _guarded_send_apply_value(self, action: str, value: int) -> bool:
        """Same as _guarded_send_apply, for the APPLYVALUE half (set_xp/
        set_credits) -- see that method's docstring."""
        if self._character_confirmed is False:
            game_events_logger.warning(f"[SAFEGUARD] Skipping reconciliation send ({action}={value}) -- "
                            f"unrecognized character, run /ap_confirm_character first if this is intentional.")
            return False
        return await self.extender.send_apply_value(action, value)

    async def _guarded_send_delevel(self, new_level: int, new_xp: int, new_force: int) -> bool:
        """Same guard as _guarded_send_apply/_guarded_send_apply_value, for
        the delevel reconciler fix -- see ExtenderBridge.send_delevel's
        own docstring for what this actually does."""
        if self._character_confirmed is False:
            game_events_logger.warning(f"[SAFEGUARD] Skipping reconciliation send "
                            f"(delevel level={new_level} xp={new_xp} force={new_force}) -- "
                            f"unrecognized character, run /ap_confirm_character first if this is intentional.")
            return False
        return await self.extender.send_delevel(new_level, new_xp, new_force)

    def _evaluate_character_safety(self) -> None:
        """Safeguard: if the currently-connected character's name has
        NEVER appeared in the
        delivery log before, AND they're not a fresh level-1 start, pause
        every delivery/reconciliation action until a human confirms this
        is intentional (/ap_confirm_character).

        The failure mode this protects against: an EXISTING, already-
        leveled character this log has never seen (wrong save loaded, a
        stale/unexpected connection, testing against the wrong character)
        would otherwise silently get the entire "you should have received
        N items by now" backlog dumped on it at once -- exactly the
        scenario the delivery-log's own "fresh character gets everything"
        fast path was built for a GENUINE new game, not an accidental
        connection to the wrong one. A real level-1 character can't have
        any prior AP history by definition, so that case is always safe
        to wave through automatically without asking -- no false positives
        on an actual fresh start.

        Called on every extender event (cheap: early-returns until both
        pieces of information are known, and again once already decided
        FOR THE CURRENT CHARACTER NAME) rather than hooked precisely to
        the NAMEREPORT/LEVELREPORT lines themselves -- simpler, and it
        naturally (re-)evaluates on its own the moment both are available,
        from whichever order they arrive in. Also naturally re-evaluates
        if the character name itself ever changes mid-session (a
        reconnect to a different save without restarting this process) --
        see _character_confirmed_for."""
        character = self.reconciler.current_character_name
        if character is None or self.current_level is None:
            return
        if self._character_confirmed is not None and self._character_confirmed_for == character:
            return
        self._character_confirmed_for = character
        if character in self._known_characters or self.current_level <= 1:
            self._character_confirmed = True
            game_events_logger.info(f"[SAFEGUARD] Character {character!r} (level {self.current_level}) "
                            f"recognized -- proceeding normally.")
            return
        self._character_confirmed = False
        known = ", ".join(sorted(self._known_characters)) if self._known_characters else "(none logged yet)"
        game_events_logger.warning("=" * 70)
        game_events_logger.warning(f"[SAFEGUARD] Connected character {character!r} (level {self.current_level}) "
                        f"is not a character we recognize, and isn't a fresh level-1 start.")
        game_events_logger.warning("All item deliveries and corrections are PAUSED until this is resolved.")
        game_events_logger.warning(f"Previously known character(s) on this log: {known}")
        game_events_logger.warning("If this is genuinely a new/different playthrough on this seed, run "
                        "/ap_confirm_character to proceed. Otherwise, load the correct "
                        "character/save and reconnect.")
        game_events_logger.warning("=" * 70)

    def _maybe_queue_companion_class(self, arm_name: str) -> None:
        """CompanionClass=no_jedi/randomize_all: right after a companion
        recruit arm is sent (either path -- the ap_gated real-item flow via
        _do_deliver below, or the CompanionMode=normal self-grant branch in
        on_package above), also queue their assigned class if one exists.
        A no-op for jedi_companion/off (self.companion_class_rolls empty) and
        for HK-47/T3-M4 (droids, never given an assignment). Routed through
        _queue_heavy -- same crash class as any other companion_class
        send, see that method's
        docstring. Fire-and-forget regardless of exact timing relative to
        the recruit actually landing -- the companion_class action's own
        GetObjectByTag+IsNPCPartyMember guard (see generate_trampoline_
        batch.py's build_companion_class_block) makes it safe either way,
        and the heavy queue now guarantees it never races another heavy
        send in the same trampoline batch either."""
        if not arm_name.startswith("companion_"):
            return
        npc_key = arm_name[len("companion_"):]
        class_name = self.companion_class_rolls.get(npc_key)
        if class_name:
            self._queue_heavy(f"companion_class:{npc_key}:{class_name}",
                               f"(auto-follow-up) companion_class:{npc_key}:{class_name}")

    async def _do_deliver(self, item_name: str, arm_name: str, index: int, character: typing.Optional[str]) -> None:
        """The actual send -- shared by the immediate (light-arm) path in
        _deliver_item and the serialized consumer in _process_heavy_queue."""
        if arm_name.startswith("give_item:"):
            parts = arm_name.split(":")
            resref = parts[1] if len(parts) > 1 else ""
            # An explicit third segment (give_item:<resref>:<count>) overrides
            # the normal consumable_stack_count-derived amount -- used for
            # fixed-quantity grants like the LootMode=destroy/replace Security
            # Spike safety net below, where the count is a deliberate design
            # constant, not something the player's stack-size preference
            # should shrink or inflate.
            count = int(parts[2]) if len(parts) > 2 else self._gear_item_count(resref)
            sent = await self.extender.send_apply_item(resref, count)
            if sent:
                # A local write() succeeding is NOT proof the extender
                # actually received it -- see ExtenderBridge.wait_staged's
                # docstring for the real casualty this closes (a give_item
                # write that succeeded locally while the game process was
                # already dying from an unrelated crash, permanently
                # logged "sent" despite never reaching a live extender).
                sent = await self.extender.wait_staged(f"give_item:{resref}")
            if sent:
                logger.info(f"[queued for game] {item_name} -> give_item:{resref} x{count}")
                self._log_delivery(character, index, item_name, arm_name, "sent")
            else:
                game_events_logger.warning(f"[NOT SENT -- extender offline] {item_name} -> give_item:{resref}. "
                                f"Will need /ap_apply manually once the game is up, "
                                f"or a resend mechanism (not yet built).")
                self._log_delivery(character, index, item_name, arm_name, "failed_extender_offline")
            return
        if arm_name.startswith("companion_class:"):
            # CompanionClass=jedi_companion's real AP item -- a fixed
            # (companion, class) pair already decided at generation time
            # (see Items.py's "Jedi Training: ..." entries), not something
            # that needs the CLASS_ARM_TO_KEY re-fire guard below: repeating
            # a KSE_SetCreatureField write is a harmless no-op (confirmed
            # live -- unlike AddMultiClass/ShowLevelUpGUI, it's a pure field
            # write), and the standard delivery-log dedup above already
            # covers the reconnect-replay case anyway.
            _, npc_key, class_name = arm_name.split(":", 2)
            sent = await self.extender.send_companion_class(npc_key, class_name)
            if sent:
                # See give_item's own comment on wait_staged above -- same
                # real-vs-local-only confirmation gap closed the same way.
                sent = await self.extender.wait_staged(f"companion_class:{npc_key}")
            if sent:
                logger.info(f"[queued for game] {item_name} -> companion_class:{npc_key}:{class_name}")
                self._log_delivery(character, index, item_name, arm_name, "sent")
            else:
                game_events_logger.warning(f"[NOT SENT -- extender offline] {item_name} -> companion_class:{npc_key}:{class_name}. "
                                f"Will need /ap_apply manually once the game is up, "
                                f"or a resend mechanism (not yet built).")
                self._log_delivery(character, index, item_name, arm_name, "failed_extender_offline")
            return
        if arm_name in CLASS_ARM_TO_KEY:
            # Class switches are one-shot (AddMultiClass + ShowLevelUpGUI)
            # and NOT safe to re-fire -- a reconnect resending a class arm
            # to an already-multiclassed character crashes the game. The
            # delivery log above already blocks most reconnect replays,
            # but this is a
            # SECOND, independent check specifically for class switches --
            # real in-game state, authoritative even if the log entry was
            # somehow lost (e.g. a crash before it could be written). Wait
            # briefly for the first CLASSREPORT poll if we haven't heard
            # one yet, rather than guessing.
            for _ in range(20):  # ~10s max at 0.5s/poll
                if self.reconciler.classes_known:
                    break
                await asyncio.sleep(0.5)
            if self.reconciler.has_class(arm_name):
                game_events_logger.info(f"[skipped] {item_name} -> {arm_name} (character already has this class)")
                self._log_delivery(character, index, item_name, arm_name, "skipped_already_has_class")
                return
        sent = await self.extender.send_apply(arm_name)
        if sent:
            # See give_item's own comment on wait_staged above -- same
            # real-vs-local-only confirmation gap closed the same way.
            sent = await self.extender.wait_staged(arm_name)
        if sent:
            self.reconciler.note_item_received(arm_name)
            logger.info(f"[queued for game] {item_name} -> {arm_name}")
            self._log_delivery(character, index, item_name, arm_name, "sent")
            self._maybe_queue_companion_class(arm_name)
        else:
            game_events_logger.warning(f"[NOT SENT -- extender offline] {item_name} -> {arm_name}. "
                            f"Will need /ap_apply {arm_name} manually once the game is up, "
                            f"or a resend mechanism (not yet built).")
            self._log_delivery(character, index, item_name, arm_name, "failed_extender_offline")

    async def _process_heavy_queue(self) -> None:
        """Consumes HEAVY_ARMS (and companion_class:) deliveries one at a
        time, waiting for each to confirm-applied (AP|APPLIED|<arm>|...)
        before sending the next -- see HEAVY_ARMS and the queuing comment
        in _deliver_item for why."""
        while True:
            item_name, arm_name, index, character = await self._heavy_queue.get()
            # companion_class:<name>:<class> sends are tracked in the
            # extender's delivery table under just "companion_class:<name>"
            # (no class suffix) -- see kotor_extender_bridge.py's
            # send_companion_class()/_track_delivery_from_event, which
            # re-keys AP|APPLIED|companion_class events the same way (both
            # a real delivery only ever has ONE candidate class per
            # companion per seed, so the class itself adds no useful
            # distinguishing information to the key). Poll under that
            # shorter key, not the full parameterized arm_name, or
            # confirmation can never match and every companion_class send
            # would silently eat the full 10-minute timeout below.
            poll_key = arm_name
            if arm_name.startswith("companion_class:"):
                poll_key = "companion_class:" + arm_name.split(":", 2)[1]
            already_applied_at = None
            record = self.extender.deliveries.get(poll_key)
            if record is not None:
                already_applied_at = record.applied_at

            await self._do_deliver(item_name, arm_name, index, character)

            # Wait for confirmation this specific send actually landed --
            # i.e. applied_at advanced past whatever it was before this
            # send (guards against reading a stale confirmation from an
            # EARLIER delivery of the same arm_name). Bounded so a lost
            # confirmation can't stall every later heavy item forever.
            for _ in range(600):  # ~10 minutes max at 1s/poll
                record = self.extender.deliveries.get(poll_key)
                if record is not None and record.applied_at is not None and record.applied_at != already_applied_at:
                    break
                await asyncio.sleep(1.0)
            else:
                game_events_logger.warning(f"[heavy queue] no confirmation for {arm_name} after 10 minutes, "
                                f"proceeding to the next item anyway")
            self._heavy_queue.task_done()

    def run_gui(self):
        from kvui import GameManager
        from kivy.clock import Clock
        from kivy.uix.boxlayout import BoxLayout
        from kivymd.uix.label import MDLabel

        class KotorStatusView(BoxLayout):
            def __init__(self, ctx: "KotorContext", **kwargs):
                super().__init__(orientation="vertical", padding=10, spacing=6, **kwargs)
                self.ctx = ctx
                self.connection_label = MDLabel(text="Extender: not connected", size_hint_y=None, height=30)
                # The new-character safeguard (_evaluate_character_safety)
                # can silently pause EVERY delivery/reconciliation send for
                # a whole session with no in-game indication at all -- a
                # mid-session "New Game" (fresh random PC name) can leave
                # deliveries paused indefinitely with the only visible
                # symptom being "[SAFEGUARD] Skipping..." lines buried in
                # the Heartbeat log, easy to miss unless someone's actively
                # watching it. This label is the fix: impossible-to-miss
                # on the main Status tab, matching connection_label's own
                # visibility, not just another log line.
                self.character_label = MDLabel(text="", size_hint_y=None, height=30)
                self.checks_label = MDLabel(text="Checks: 0 / 0", size_hint_y=None, height=30)
                self.pending_label = MDLabel(text="Pending delivery: none", size_hint_y=None, height=60)
                self.recent_label = MDLabel(text="Recent items: none")
                self.add_widget(self.connection_label)
                self.add_widget(self.character_label)
                self.add_widget(self.checks_label)
                self.add_widget(self.pending_label)
                self.add_widget(self.recent_label)

            def refresh(self):
                ext = self.ctx.extender
                self.connection_label.text = f"Extender: {'CONNECTED' if ext.is_connected else 'NOT CONNECTED'}"
                if self.ctx._character_confirmed is False:
                    name = self.ctx._character_confirmed_for or "(unknown)"
                    self.character_label.text = (
                        f"⚠ CHARACTER NOT CONFIRMED: {name!r} -- all deliveries/"
                        f"corrections are PAUSED. Run /ap_confirm_character if this is "
                        f"really you (e.g. you started a fresh save mid-session)."
                    )
                else:
                    self.character_label.text = ""
                checked = len(self.ctx.checked_locations)
                total = len([lid for lid in self.ctx.location_names[self.ctx.game] if lid >= 0])
                self.checks_label.text = f"Checks: {checked} / {total}"

                pending = ext.pending_deliveries()
                queued = [d for d in pending if delivery_state(d) == "Queued"]
                staged = [d for d in pending if delivery_state(d) == "Staged"]
                if queued or staged:
                    sections = []
                    if queued:
                        sections.append(
                            f"Queued ({len(queued)}, sent but not yet confirmed received):\n"
                            + ", ".join(d.arm_name for d in queued)
                        )
                    if staged:
                        sections.append(
                            f"Staged ({len(staged)}, armed for your next area entry):\n"
                            + ", ".join(d.arm_name for d in staged)
                        )
                    self.pending_label.text = "\n".join(sections)
                else:
                    self.pending_label.text = "Queued: none\nStaged: none"

                settled = ext.recently_settled(8)
                if settled:
                    lines = [f"  {d.arm_name}: settled ({d.detail})" for d in settled]
                    self.recent_label.text = "Recently Settled:\n" + "\n".join(lines)
                else:
                    self.recent_label.text = "Recently Settled: none"

        class KotorManager(GameManager):
            logging_pairs = [
                ("Client", "Archipelago"),
                ("Extender", "Game"),
                ("Heartbeat", "Heartbeat"),
            ]
            base_title = "KOTOR Archipelago Client"

            def build(self):
                container = super().build()
                self.status_view = KotorStatusView(self.ctx)
                self.add_client_tab("Status", self.status_view)

                def tick(_dt):
                    self.status_view.refresh()
                Clock.schedule_interval(tick, 1.0)
                return container

            def refresh_status(self):
                if hasattr(self, "status_view"):
                    self.status_view.refresh()

        self.ui = KotorManager(self)
        self.ui_task = asyncio.create_task(self.ui.async_run(), name="UI")


def launch():
    import colorama

    async def main(args):
        ctx = KotorContext(args.connect, args.password)
        if args.name:
            ctx.username = args.name
        ctx.server_task = asyncio.create_task(server_loop(ctx), name="server loop")
        ctx.extender_task = asyncio.create_task(ctx.extender.connect_forever(), name="extender bridge")
        ctx.heavy_queue_task = asyncio.create_task(ctx._process_heavy_queue(), name="heavy item queue")
        if gui_enabled:
            ctx.run_gui()
        ctx.run_cli()

        await ctx.exit_event.wait()
        ctx.server_address = None
        await ctx.shutdown()

    parser = get_base_parser(description="KotOR Archipelago client (Phase 1: real extender bridge).")
    parser.add_argument("--name", default=None, help="Slot name to connect as (skips the interactive prompt).")
    parser.add_argument("--repo-root", default=None,
                         help="Path to your PlayerBundle folder (the one with scripts\\generate_poll_shared.py "
                              "and scripts\\generate_makejedi_suppressor.py in it). Auto-detected in the two common "
                              "layouts (see _detect_repo_root above) -- only pass this if auto-detection can't find "
                              "it, e.g. scripts\\ living somewhere unrelated to this file entirely. Read via an "
                              "early sys.argv scan (see REPO_ROOT above), not through this parser value directly "
                              "-- listed here so --help/argparse still recognize it.")
    args, rest = parser.parse_known_args()

    colorama.init()
    asyncio.run(main(args))
    colorama.deinit()


if __name__ == "__main__":
    launch()
