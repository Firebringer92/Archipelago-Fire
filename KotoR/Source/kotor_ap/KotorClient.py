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
import contextlib
import hashlib
import json
import logging
import os
import random
import re
import subprocess
import sys
import threading
import time
import typing

import ModuleUpdate
ModuleUpdate.update()

import Utils

if __name__ == "__main__":
    Utils.init_logging("KotorClient", exception_logger="Client")

from NetUtils import ClientStatus
from CommonClient import (
    ClientCommandProcessor,
    CommonContext,
    get_base_parser,
    gui_enabled,
    logger,
    server_loop,
)

from kotor_extender_bridge import ExtenderBridge, delivery_state
from kotor_dispatcher import DispatchClient
from kotor_reconciliation import ReconciliationTracker, CLASS_ARM_TO_KEY
from entitlement import HEAVY_ARMS, PROGRESSION_ITEM_RESREFS, is_heavy_arm
from kotor_location_tracker import JUHANI_KILLED_RE, LocationTracker
from worlds.kotor.Items import item_table, TRAP_ITEMS
from worlds.kotor.Locations import location_table
from worlds.kotor import NON_JEDI_COMPANION_KEYS, WORLD_VERSION

# NPC_* index (nwscript.nss) -> the arm that re-grants that companion.
# Order matches Locations.py's generator COMPANIONS list.
# CompanionMode=ap_limited: how many of the player's own checks earn each companion (fixed, not an option)
COMPANION_LIMITER_CHECKS = 25

COMPANION_IDX_TO_ARM = [
    "companion_bastila", "companion_canderous", "companion_carth",
    "companion_hk47", "companion_jolee", "companion_juhani",
    "companion_mission", "companion_t3m4", "companion_zaalbar",
]

_ID_TO_LOCATION_DATA = {data.id: data for data in location_table.values()}

# Anchors DELIVERY_LOG_PATH/GALACTIC_SHOP_PENDING_PATH below to the folder
# KotorClient.py actually lives in, NOT the process's current working
# directory. A bare relative filename silently resolves against whatever
# CWD happened to be active at launch (a shortcut, a different terminal
# tab, a wrapper script) -- if that ever differs from run to run, each of
# those state files gets "lost" (read back empty) and recreated from
# scratch, which for DELIVERY_LOG_PATH specifically means the reconnect-
# safety gate at _delivered_keys sees no history and replays every
# already-delivered item as if it were brand new.
_CLIENT_DIR = os.path.dirname(os.path.abspath(__file__))

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
# DELIVERY_LOG_PATH below (anchored to _CLIENT_DIR, next to the client).
GALACTIC_SHOP_PENDING_PATH = os.path.join(_CLIENT_DIR, "kotor_galactic_shop_pending.json")
# Emitted by extender/scripts_src/ap_galtradebox.nss's OnInvDisturbed
# handler (KSE_Diag 142) -- relayed here like every other AP| line.
_VOIDTRADE_DEPOSIT_RE = re.compile(r"AP\|VOIDTRADE\|DEPOSIT\|([^|\s]+)\|(\d+)")
_VOIDTRADE_CLAIM_RE = re.compile(r"AP\|VOIDTRADE\|CLAIM\b")

# How long after the game applies an incoming DeathLink's death the death the poll then sees still counts as caused by that link.
LINK_DEATH_ECHO_SECONDS = 45
# A Remove a Companion trap waits for a target that the live reports show present, and gives up (settles as a no-op) after this many area entries.
TRAP_COMPANION_WAIT_AREAS = 6

_GOAL_MALAK_RE = re.compile(r"AP\|CHECK\|GOAL\|MALAK_DEAD")
# reach_leviathan Goal option -- complete on entering the first Leviathan area
# ("Visited: Leviathan - Prison Block"), the same area event that location
# fires on. Its index comes from Locations.py so the two can't drift apart.
_GOAL_LEVIATHAN_AREA_IDX = location_table["Visited: Leviathan - Prison Block"].area_idx
_GOAL_LEVIATHAN_RE = re.compile(r"AP\|CHECK\|AREA\|" + str(_GOAL_LEVIATHAN_AREA_IDX) + r"(?!\d)")
_LEVEL_RE = re.compile(r"AP\|LEVELREPORT\|(\d+)")
# arm_orchestrator.py's own diagnostic -- not written by the KSE DLL, but
# the log-tail thread relays ANY line in kse.log containing
# an AP| marker regardless of writer, so this reaches here the same way
# every real KSE_Diag marker does. See that file's
# _push_queue_bloat_warning_to_client() for why this exists: the original
# print-only warning never reached the client at all (only this script's
# own stdout, which the C extender discards on a successful exit).
_QUEUE_BLOAT_RE = re.compile(r"AP\|WARNING\|QUEUE_BLOAT\|(\d+)")
# CheckPlayerId() (generate_poll_shared.py): the name of the character's Player ID item, "Player ID: <slot> <hash>",
# or NONE when the character has no such item. The hash is the LAST space-separated word.
_PLAYERID_RE = re.compile(r'AP\|PLAYERID\|([^"]+)')


def world_version_problem(slot_data: dict) -> typing.Optional[str]:
    """None when the seed was made by the same KOTOR world release as this client, else a plain-language reason it cannot be played.
    Item and location ids differ between releases, so a seed from another one would hand out the wrong items."""
    theirs = slot_data.get("world_version")
    if theirs == WORLD_VERSION:
        return None
    if theirs is None:
        return ("This seed was generated by an older version of the KOTOR world (before 0.2.0), so its items and locations do not match this client. "
                "Generate the seed again with this release's kotor.apworld.")
    return (f"This seed was generated with KOTOR world {theirs}, but this client is release {WORLD_VERSION}. Install the same release of both "
            f"downloads (the kotor.apworld zip and the PlayerBundle zip), generate the seed again if needed, then connect again.")


def save_id_for(seed_name, slot) -> str:
    """The short id of a (seed, slot): the first 9 hex characters of sha1("<seed_name>|<slot>"). The Player ID
    item's name carries it (patch_player_id.py writes the template on every Connect); the poll reports the
    item the character holds, and _note_player_id() compares the two. Passive: nothing is paused on it."""
    return hashlib.sha1(f"{seed_name}|{slot}".encode("utf-8")).hexdigest()[:9]
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

# How long _process_heavy_queue() waits for a heavy send's AP|APPLIED|
# confirmation before giving up and moving to the next queued item -- see
# that function's own comment. Also used by ReconciliationTracker (passed
# in as is_awaiting_confirmation) to know how long the normal delivery
# pipeline should get exclusive custody of a companion arm before the
# reconciler's own missing-companion deficit check is allowed to retry it
# -- see that constructor argument's docstring for the race this closes.
HEAVY_SEND_CONFIRM_TIMEOUT_SECONDS = 600  # ~10 minutes at 1s/poll

# HEAVY_ARMS/is_heavy_arm moved to entitlement.py -- the single canonical
# classification, imported here and by kotor_reconciliation.py (which
# can't import from this file, since the dependency runs the other way).
# See entitlement.py's own comment on HEAVY_ARMS for why this used to be
# two parallel definitions.

# Every arm name the extender's heartbeat/trampoline batch logic knows how
# to apply -- must stay in sync with AP_ARM_NAMES in extender/src_k1se/ap_extender.c
# and generate_trampoline_batch.py's APPLIES table.
KNOWN_ARM_NAMES = [
    "computer_use", "demolitions", "stealth", "awareness",
    "persuade", "repair", "security", "treat_injury",
    "companion_bastila", "companion_canderous",
    "xp",
    "class_guardian", "class_consular",
    "credits", "ability_charisma",
    "companion_carth", "companion_hk47", "companion_jolee",
    "companion_juhani", "companion_mission", "companion_t3m4",
    "companion_zaalbar", "class_sentinel",
    "ability_strength", "ability_dexterity", "ability_constitution",
    "ability_intelligence", "ability_wisdom",
    "force_death",
    "pc_class_soldier", "pc_class_scout", "pc_class_scoundrel", "pc_droid",
    # One-shot research pair -- see generate_trampoline_batch.py's APPLIES
    # table (arms 58/59) for what these test and why. Supersedes the
    # retired diag_journal_persist_write/_read (arms 55/56) -- an
    # undeclared plot ID couldn't even be written, so this pair targets a
    # properly-declared quest tag ("ap_tracker") instead.
    "diag_ap_tracker_write", "diag_ap_tracker_read",
    # The real "Archipelago Tracker" journal stages (arms 60-64) -- sent
    # by kotor_reconciliation.py's own check-percentage branch. Listed
    # here too so /ap_apply can trigger one directly for testing.
    "journal_tracker_20", "journal_tracker_40", "journal_tracker_60",
    "journal_tracker_80", "journal_tracker_100", "journal_tracker_1",
    # Retired research arms are removed outright from this list (it's
    # just an /ap_apply validation list, no positional-ID constraint) --
    # see DEVELOPMENT_HISTORY.md for the research they concluded and
    # extender/research_archive/ for their raw results. Unlike this list,
    # AP_ARM_NAMES in ap_extender.c and APPLIES in
    # generate_trampoline_batch.py rename rather than remove retired
    # entries, to preserve arm-ID stability.
]

# AP item display name -> extender arm name, derived directly from
# item_table's own arm_name field (see Items.py's ItemData docstring) so
# this can never drift out of sync the way a hand-duplicated dict did --
# that stale copy silently dropped every item it didn't recognize,
# including both filler items, for this entire project's testing so far.
ITEM_NAME_TO_ARM = {name: data.arm_name for name, data in item_table.items()}
# arm_name of the four goal-progress items in worlds/kotor/Items.py.
GOAL_MARKER_ARM = "goal_marker"

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
DELIVERY_LOG_PATH = os.path.join(_CLIENT_DIR, "kotor_delivery_log.jsonl")
# Per-playthrough alignment history (the last alignment value seen), keyed "seed|slot". Small
# JSON rewritten whenever it changes, next to the delivery log, so it survives client restarts.
ALIGNMENT_STATE_PATH = os.path.join(_CLIENT_DIR, "kotor_alignment_state.json")

# The standard Steam location, used only when nothing below names the game
# folder. GAME_DIR itself is resolved right after _sys_argv_value is defined.
_DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"


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


def _resolve_game_dir() -> str:
    """Where the KOTOR install is, for every script the client launches
    (--game-dir=). In order: --game-dir on the command line, the
    KOTOR_GAME_DIR environment variable, the folder install_playerbundle.py
    recorded in %LOCALAPPDATA%\\KotorAP\\install_manifest.json when it
    installed (the same record the Launcher button already uses), then the
    default Steam location. A tester whose game is not on C:\\Program Files
    (x86)\\Steam would otherwise have every patch step run against a
    folder that does not exist."""
    explicit = _sys_argv_value("--game-dir", None) or os.environ.get("KOTOR_GAME_DIR")
    if explicit:
        return explicit
    try:
        state_dir = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "KotorAP")
        with open(os.path.join(state_dir, "install_manifest.json"), encoding="utf-8") as f:
            recorded = json.load(f).get("game_dir")
        # Only a folder that really holds the game: the record outlives an
        # uninstall or a test install into a scratch folder.
        if recorded and os.path.isfile(os.path.join(recorded, "swkotor.exe")):
            return recorded
    except Exception:
        pass
    return _DEFAULT_GAME_DIR


GAME_DIR = _resolve_game_dir()


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
PATCH_STORY_GATES = os.path.join(REPO_ROOT, "scripts", "patch_story_gates.py")
PATCH_LOOT_DISTURB = os.path.join(REPO_ROOT, "scripts", "patch_loot_disturb.py")
PATCH_DOOR_RANDOMIZER = os.path.join(REPO_ROOT, "scripts", "patch_door_randomizer.py")
PATCH_ADDITIONAL_ENEMIES = os.path.join(REPO_ROOT, "scripts", "patch_additional_enemies.py")
PATCH_BAZAAR_TOKENS = os.path.join(REPO_ROOT, "scripts", "patch_bazaar_tokens.py")
PATCH_GALACTIC_SHOP = os.path.join(REPO_ROOT, "scripts", "patch_galactic_shop.py")
PATCH_BOSS_DATAPADS = os.path.join(REPO_ROOT, "scripts", "patch_boss_datapads.py")
PATCH_PLAYER_ID = os.path.join(REPO_ROOT, "scripts", "patch_player_id.py")
PATCH_NEW_COMPANION_ASSETS = os.path.join(REPO_ROOT, "scripts", "generate_new_companion_assets.py")
PATCH_PARTY_CONSOLE = os.path.join(REPO_ROOT, "scripts", "patch_party_console.py")
BUILD_GAME_ASSETS = os.path.join(REPO_ROOT, "scripts", "build_game_assets.py")
PATCH_DROID_ASSETS = os.path.join(REPO_ROOT, "scripts", "generate_droid_assets.py")
PATCH_SHOP_ITEM_COSTS = os.path.join(REPO_ROOT, "scripts", "patch_shop_item_costs.py")
PATCH_AREA_POLL_HOOKS = os.path.join(REPO_ROOT, "scripts", "patch_area_poll_hooks.py")
CLIENT_FILES = os.path.join(REPO_ROOT, "scripts", "client_files.py")
BUILD_AP_TRACKER_QUEST = os.path.join(REPO_ROOT, "scripts", "build_ap_tracker_quest.py")
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


def _patched_marker_is_current(key: str, verify=None) -> bool:
    """True only when the "already patched" record can be trusted: it was written for THIS game folder (a marker
    from before the folder was recorded, or from another install, is not trusted) and the files the patch writes are
    still there (an uninstall, a reinstall or a manual cleanup removes them but leaves the record)."""
    try:
        with open(PATCHED_SEEDS_MARKER_PATH, encoding="utf-8") as f:
            recorded_dir = json.load(f).get("__game_dir__")
    except Exception:
        return False
    if recorded_dir != GAME_DIR:
        game_events_logger.info(f"[{key}] the record of what was patched is for a different game folder -- applying again.")
        return False
    if verify is not None and not verify():
        game_events_logger.warning(f"[{key}] recorded as applied, but its files are missing from {GAME_DIR} -- applying again.")
        return False
    return True


def _story_gate_files_present() -> bool:
    """With the Progression System on, the story gate patch writes one item template per progression item into
    Override. Without it on there is nothing to check."""
    try:
        with open(SLOT_DATA_PATH, encoding="utf-8") as f:
            if not json.load(f).get("progression_system"):
                return True
    except Exception:
        return True
    override = os.path.join(GAME_DIR, "Override")
    return all(os.path.isfile(os.path.join(override, f"{resref}.uti"))
               for resref in PROGRESSION_ITEM_RESREFS.values() if resref.startswith("ap_tk_"))


def _save_patched_seed(key: str, gate_key: str | None) -> None:
    try:
        os.makedirs(os.path.dirname(PATCHED_SEEDS_MARKER_PATH), exist_ok=True)
        try:
            with open(PATCHED_SEEDS_MARKER_PATH, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
        data[key] = gate_key
        data["__game_dir__"] = GAME_DIR
        with open(PATCHED_SEEDS_MARKER_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as e:
        logger.warning(f"Could not update {PATCHED_SEEDS_MARKER_PATH}: {e}")


def _slot_data_fingerprint(slot_data: dict) -> str:
    """Hashes every field any of the 5 seed-gated patch scripts
    (loot_disturb/item_suppression/story_gates/door_randomizer/additional_enemies) actually reads,
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
        loot_mode: int, door_mapping: dict | None, area_randomizer: int, starting_class: int,
        additional_enemies_mode: int = 0, seed_name: str | None = None,
        progression_system: bool = False, galactic_shop: bool = False,
        new_companion: int = 0, door_mapping_repairs: list | None = None,
        archipelago_vendor: bool = False,
        companion_class_mode: int = 0, companion_droid_plan: dict | None = None,
        bazaar: bool = False, new_companion_classes: dict | None = None) -> None:
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
                # Read by generate_trampoline_batch.py -- spawns the Archipelago Vendor
                # NPC in the Hawk's trampoline when on.
                "archipelago_vendor": archipelago_vendor,
                # Read by generate_trampoline_batch.py -- spawns the Bazaar's Jawa trader next to the Vendor when on.
                "bazaar": bazaar,
                # Read by generate_trampoline_batch.py at real delivery
                # time to decide arm 20's (companion_hk47) template string
                # -- see that file's NEW_COMPANION_TEMPLATE comment.
                "new_companion": new_companion,
                # Read by generate_new_companion_assets.py when new_companion is 2 (random_class): {character key: class name}.
                "new_companion_classes": new_companion_classes or {},
                # Read by scripts/review_door_mapping.py to label a
                # repaired entry separately from a cleanly-coupled one.
                "door_mapping_repairs": door_mapping_repairs or [],
                # Read by generate_droid_assets.py: companion_class=droid (mode 4) and the seed's
                # {companion key: [appearance row, droid class]} deal.
                "companion_class_mode": companion_class_mode,
                "companion_droid_plan": companion_droid_plan or {},
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
    command = [sys.executable, GENERATE_POLL_SHARED,
               f"--game-dir={GAME_DIR}",
               f"--area-randomizer={1 if area_randomizer else 0}",
               f"--additional-enemies={1 if additional_enemies_mode else 0}"]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
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


def ensure_vendor_spawn() -> tuple[bool, str]:
    """See KotorContext._ensure_vendor_and_log. Delegates to arm_orchestrator.py --ensure-vendor."""
    try:
        result = subprocess.run(
            [sys.executable, ARM_ORCHESTRATOR, f"--game-dir={GAME_DIR}", "--ensure-vendor"],
            capture_output=True, text=True, timeout=180,
        )
        if result.returncode != 0:
            return False, f"arm_orchestrator.py --ensure-vendor failed (exit {result.returncode}):\n{result.stdout}\n{result.stderr}"
        return True, result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "done"
    except Exception as e:
        return False, f"ensure_vendor_spawn raised: {e}"


def clear_staged_queue(everything: bool = False) -> tuple[bool, str]:
    """Drops staged-but-unapplied entries from the old trampoline queue (arm_orchestrator.py --clear-derived, or --clear-all
    when everything is True). Deliveries no longer use that queue (they are dispatcher jobs), so this only removes entries an
    earlier version left on disk, which would otherwise fire at the next area entry. Every extender (re)connect and every
    Connect runs the --clear-all form; --clear-derived drops only what the reconciler recomputes (exact-value XP/credit/level
    corrections, companion class assignments, Archipelago Tracker stages) and keeps the rest."""
    flag = "--clear-all" if everything else "--clear-derived"
    try:
        result = subprocess.run(
            [sys.executable, ARM_ORCHESTRATOR, f"--game-dir={GAME_DIR}", flag],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            return False, f"arm_orchestrator.py {flag} failed (exit {result.returncode}):\n{result.stdout}\n{result.stderr}"
        return True, result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "done"
    except Exception as e:
        return False, f"clear_staged_queue raised: {e}"


def restore_dropped_queue() -> tuple[bool, str]:
    """Re-stages the entries an admin /ap_clear_queue dropped that nothing else brings back (gear and item grants, traps,
    force powers, additional feats, plain arms): arm_orchestrator.py --restore-dropped. The exact-value corrections,
    companion class assignments, Tracker stages and DeathLink deaths are never journaled, since the reconciler recomputes
    them or they only matter when they arrive. An entry already staged is not added twice."""
    try:
        result = subprocess.run(
            [sys.executable, ARM_ORCHESTRATOR, f"--game-dir={GAME_DIR}", "--restore-dropped"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            return False, f"arm_orchestrator.py --restore-dropped failed (exit {result.returncode}):\n{result.stdout}\n{result.stderr}"
        return True, result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "done"
    except Exception as e:
        return False, f"restore_dropped_queue raised: {e}"


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


def apply_story_gates() -> tuple[bool, str]:
    """Drives patch_story_gates.py: the Progression System's progression items and story-gate scripts (deployed when
    progression_system is on for the connected seed, removed when it is off). Compiles a few small scripts, so
    it needs nwnnsscomp like the Jedi suppressor does."""
    ok, stdout = _run_patch_script(PATCH_STORY_GATES)
    if not ok:
        return False, f"patch_story_gates.py failed:\n{stdout}"
    return True, stdout.strip().splitlines()[-1] if stdout.strip() else "done"


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


def apply_bazaar_tokens() -> tuple[bool, str]:
    """Same shape again, for patch_bazaar_tokens.py -- reads bazaar and seed_name from SLOT_DATA_PATH itself, and places
    the Archipelago Bazaar's 100 tokens in module containers when the Loot Exchange is on. Must run after apply_loot_disturb
    (it copies container templates that patch has already rewritten)."""
    try:
        result = subprocess.run(
            [sys.executable, PATCH_BAZAAR_TOKENS, f"--game-dir={GAME_DIR}"],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            return False, f"patch_bazaar_tokens.py failed (exit {result.returncode}):\n{result.stdout}\n{result.stderr}"
        return True, result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "done"
    except Exception as e:
        return False, f"apply_bazaar_tokens raised: {e}"


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
    # The boss datapad patch takes its own datapads back out of the live module files (it must not copy
    # a backup over them, which would also undo the other patchers' edits), so it goes last.
    # the last four undo what the client writes on every connect (the Jedi-trial suppressor, the shop price fixes, the New Companion files, the tracker journal and its
    # dialog.tlk strings); client_files.py then removes the Override tables that are back to the game's own. A reconnect writes them again.
    for script in (PATCH_ITEM_SUPPRESSION, PATCH_STORY_GATES, PATCH_LOOT_DISTURB, PATCH_BAZAAR_TOKENS, PATCH_BOSS_DATAPADS, PATCH_DROID_ASSETS,
                   GENERATE_MAKEJEDI_SUPPRESSOR, PATCH_SHOP_ITEM_COSTS, PATCH_NEW_COMPANION_ASSETS, BUILD_AP_TRACKER_QUEST, CLIENT_FILES):
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
    re-applies every per-seed patch fresh, ignoring the once-per-option-set
    marker: the heavier RIM-sweep patches plus Jedi Suppression
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
        ("Story Gates", apply_story_gates),
        ("Randomize Areas", apply_door_randomizer),
        ("Additional Enemies", apply_additional_enemies),
        ("Bazaar Tokens", apply_bazaar_tokens),
        ("Boss Datapads", apply_boss_datapads),
        ("Droid Assets", apply_droid_assets),
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
            capture_output=True, text=True, timeout=600,      # the first run also makes Malak's model from the game's own (model_builders.py, about half a minute)
        )
        if result.returncode != 0:
            return False, f"generate_new_companion_assets.py failed (exit {result.returncode}):\n{result.stdout}\n{result.stderr}"
        return True, result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "done"
    except Exception as e:
        return False, f"apply_new_companion_assets raised: {e}"


def apply_game_assets() -> tuple[bool, str]:
    """build_game_assets.py: the Override files that are made from the player's own game (the original scripts the wrappers call, the edited scene dialogs,
    the extra saber colours). Install.bat builds them; this runs on every Connect and only builds what is missing or changed."""
    try:
        result = subprocess.run([sys.executable, BUILD_GAME_ASSETS, f"--game-dir={GAME_DIR}"], capture_output=True, text=True, timeout=900)
        if result.returncode != 0:
            return False, f"build_game_assets.py failed (exit {result.returncode}):\n{result.stdout}\n{result.stderr}"
        return True, result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "done"
    except Exception as e:
        return False, f"apply_game_assets raised: {e}"


def apply_party_console() -> tuple[bool, str]:
    """patch_party_console.py: the spells.2da row the Party Console item needs (a player's game has no row 132). Run on every Connect; it does nothing when the row is there."""
    try:
        result = subprocess.run([sys.executable, PATCH_PARTY_CONSOLE, f"--game-dir={GAME_DIR}"], capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            return False, f"patch_party_console.py failed (exit {result.returncode}):\n{result.stdout}\n{result.stderr}"
        return True, result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "done"
    except Exception as e:
        return False, f"apply_party_console raised: {e}"


def apply_droid_assets(restore: bool = False) -> tuple[bool, str]:
    """Same shape as apply_new_companion_assets(): generate_droid_assets.py reads starting_class, companion_class_mode and
    companion_droid_plan from SLOT_DATA_PATH itself and, on every Connect, either installs the droid models, appearance
    rows, melee-weapon opening, Battle Droid class tables and companion templates or takes all of them back out when this
    seed has no droid option. Override-only, idempotent (a manifest records what it wrote)."""
    try:
        cmd = [sys.executable, PATCH_DROID_ASSETS, f"--game-dir={GAME_DIR}"] + (["--restore"] if restore else [])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        if result.returncode != 0:
            return False, f"generate_droid_assets.py failed (exit {result.returncode}):\n{result.stdout}\n{result.stderr}"
        return True, result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "done"
    except Exception as e:
        return False, f"apply_droid_assets raised: {e}"


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


def apply_boss_datapads() -> tuple[bool, str]:
    """Same shape again, for patch_boss_datapads.py: writes the three boss datapad item templates
    and adds each datapad to every fighting version of Calo Nord, Darth Bandon and Saul Karath.
    Universal (the boss checks always exist) and idempotent -- it only rewrites a module file whose
    boss is missing its datapad. Runs after the other module-rim writers on Connect because those
    rebuild their rims from the pristine backup, which would drop an earlier datapad."""
    try:
        result = subprocess.run(
            [sys.executable, PATCH_BOSS_DATAPADS, f"--game-dir={GAME_DIR}"],
            capture_output=True, text=True, timeout=180,
        )
        if result.returncode != 0:
            return False, f"patch_boss_datapads.py failed (exit {result.returncode}):\n{result.stdout}\n{result.stderr}"
        return True, " | ".join(result.stdout.strip().splitlines()[-2:]) if result.stdout.strip() else "done"
    except Exception as e:
        return False, f"apply_boss_datapads raised: {e}"


def apply_player_id(save_id: str, slot: str) -> tuple[bool, str]:
    """Same shape again, for patch_player_id.py: writes this seed's Player ID item template (an item file in
    Override, no module edit). Runs on every Connect with the current seed's id; the script rewrites the file
    only when the name changed. A brand-new level-1 character gets the item at the Endar Spire entry."""
    try:
        result = subprocess.run(
            [sys.executable, PATCH_PLAYER_ID, f"--game-dir={GAME_DIR}", f"--save-id={save_id}", f"--slot={slot}"],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            return False, f"patch_player_id.py failed (exit {result.returncode}):\n{result.stdout}\n{result.stderr}"
        return True, result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "done"
    except Exception as e:
        return False, f"apply_player_id raised: {e}"


def apply_area_poll_hooks() -> tuple[bool, str]:
    """Same shape again, for patch_area_poll_hooks.py -- gives the area(s)
    whose module has no OnEnter script of their own (Tomb of Marka Ragnos)
    the poll hook, so polling restarts there instead of staying dead until
    the player enters a hooked area. Universal, not seed-gated, idempotent
    (an already-hooked module is skipped), one module RIM edited in place."""
    try:
        result = subprocess.run(
            [sys.executable, PATCH_AREA_POLL_HOOKS, f"--game-dir={GAME_DIR}"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            return False, f"patch_area_poll_hooks.py failed (exit {result.returncode}):\n{result.stdout}\n{result.stderr}"
        return True, result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "done"
    except Exception as e:
        return False, f"apply_area_poll_hooks raised: {e}"


def apply_shop_item_costs() -> tuple[bool, str]:
    """Same shape again, for patch_shop_item_costs.py -- fixes the 142
    real shop_randomize items with a genuine in-game UTI Cost of 0 (a
    0-cost purchase never drops credits, so patch_item_suppression.py's
    purchase-detection check can't tell a "just bought this" acquisition
    from a fresh pickup, wrongly suppressing/bonus-ifying/replacing it).
    Universal, not gated by any option -- unlike galactic_shop/
    new_companion above, there's no "restore vanilla when off" case, just
    always-apply. Purely additive (writes Override/<resref>.uti copies,
    never touches the read-only base game files) and idempotent (re-run
    finds 0 remaining zero-cost items), so safe to run on every Connect
    the same way."""
    try:
        result = subprocess.run(
            [sys.executable, PATCH_SHOP_ITEM_COSTS, f"--game-dir={GAME_DIR}"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            return False, f"patch_shop_item_costs.py failed (exit {result.returncode}):\n{result.stdout}\n{result.stderr}"
        return True, result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "done"
    except Exception as e:
        return False, f"apply_shop_item_costs raised: {e}"


def apply_ap_tracker_quest() -> tuple[bool, str]:
    """Same shape again, for build_ap_tracker_quest.py -- declares the
    "Archipelago Tracker" journal quest and appends its 7 dialog.tlk
    entries (quest name + 6 stage texts) if they aren't already present.
    Universal, not gated by any option, same as apply_shop_item_costs()
    above -- no "restore vanilla when off" case, the quest should just
    always exist. Must run against THIS install's own dialog.tlk rather
    than shipping a pre-baked global.jrl: _ensure_tlk_strings() picks up
    wherever this machine's dialog.tlk currently ends, which won't
    generally match the dev machine's own entry count. Idempotent
    (checks the tail of dialog.tlk for an exact match before appending
    again), so safe to run on every Connect the same way."""
    try:
        result = subprocess.run(
            [sys.executable, BUILD_AP_TRACKER_QUEST, f"--game-dir={GAME_DIR}"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            return False, f"build_ap_tracker_quest.py failed (exit {result.returncode}):\n{result.stdout}\n{result.stderr}"
        return True, result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "done"
    except Exception as e:
        return False, f"apply_ap_tracker_quest raised: {e}"


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
        Traps use trap:<type>[:<params>], e.g. /ap_apply trap:reduce_skill.
        Feat training is unlocked with give_item:ap_ft_<key>, e.g. /ap_apply give_item:ap_ft_juhani:1."""
        if not arm_name:
            self.output(f"Usage: /ap_apply <name>. Known names: {', '.join(KNOWN_ARM_NAMES)}, "
                        f"or give_item:<resref>[:<count>], or companion_class:<name>:<class>, "
                        f"or trap:<type>[:<params>]")
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
            # force_power:<spells.2da row id>: grants that Force Power to the PC (any vanilla FORCE_POWER_* row).
            # Admin-only, a testing tool.
            raw = arm_name.split(":", 1)[1]
            if not raw.isdigit():
                self.output("Usage: /ap_apply force_power:<spells.2da row id>, e.g. /ap_apply force_power:6")
                return False
            asyncio.create_task(self.ctx.extender.send_force_power(int(raw)))
            self.output(f"Admin: queued force_power {raw} directly (bypassing AP server) -- "
                        f"lands once the game is calm.")
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
        if is_heavy_arm(arm_name):
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

    def _cmd_ap_clear_queue(self) -> bool:
        """Admin: drops EVERY entry staged for the game but not yet applied (gear and item grants and traps included, not
        just the ones the reconciler re-derives). For testing, when a stale staged item keeps firing."""
        ok, msg = clear_staged_queue(everything=True)
        self.output(("OK: " if ok else "FAILED: ") + msg)
        if ok:
            self.output("Gear, traps and other grants that cannot be re-derived were journaled; /ap_restore_queue brings them back.")
        return ok

    def _cmd_ap_restore_queue(self) -> bool:
        """Admin: re-stages the entries the last /ap_clear_queue dropped that cannot be re-derived (item grants, traps, force
        powers, additional feats, plain arms). The reconciler's own corrections and DeathLink deaths are not restored."""
        ok, msg = restore_dropped_queue()
        self.output(("OK: " if ok else "FAILED: ") + msg)
        return ok

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
        with self.ctx._patching():
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
        with self.ctx._patching():
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

    def _cmd_ap_apply_droid_assets(self) -> bool:
        """Re-runs generate_droid_assets.py by hand (normally done automatically on Connect)."""
        self.output("Admin: re-applying the droid assets ...")
        ok, msg = apply_droid_assets()
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

    def _cmd_ap_apply_area_poll_hooks(self) -> bool:
        """Same again, for patch_area_poll_hooks.py (normally run on every
        Connect -- see on_package)."""
        self.output("Admin: re-applying the area poll hooks ...")
        ok, msg = apply_area_poll_hooks()
        self.output(("OK: " if ok else "FAILED: ") + msg)
        return ok

    def _cmd_ap_apply_shop_item_costs(self) -> bool:
        """Same again, for patch_shop_item_costs.py (normally run on every
        Connect -- see on_package)."""
        self.output("Admin: re-applying the shop item cost fix ...")
        ok, msg = apply_shop_item_costs()
        self.output(("OK: " if ok else "FAILED: ") + msg)
        return ok

    def _cmd_ap_apply_tracker_quest(self) -> bool:
        """Same again, for build_ap_tracker_quest.py (normally run on
        every Connect -- see on_package). Re-run is always safe: picks up
        the existing dialog.tlk entries if already present instead of
        appending duplicates."""
        self.output("Admin: re-applying the Archipelago Tracker journal quest ...")
        ok, msg = apply_ap_tracker_quest()
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
        """DEVELOPER-ONLY (needs the environment variable KOTOR_AP_DEV=1; refused otherwise):
        send a raw diagnostic command straight to the
        extender socket, e.g. /ap_raw DUMPMEM:16EBB958:64 (hex address, no
        0x prefix, decimal size). Also READBYTE:<hexaddr>, WRITEBYTE:<hexaddr>:<value>,
        SCANBYTES:<comma-separated-hex-bytes>, SNAPSHOT:<name> -- whatever
        ap_extender.c's ap_dispatch_command understands. Output (e.g. a
        DUMPMEM dump) goes to a file next to kse.log, NOT this console.
        Kept for the Force Powers memory-offset hunt this was built for."""
        if os.environ.get("KOTOR_AP_DEV") != "1":
            self.output("/ap_raw is a developer command and is switched off. "
                        "(Set the environment variable KOTOR_AP_DEV=1 before starting the client to use it.)")
            return False
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

    def _dispatch_dev_only(self) -> bool:
        if os.environ.get("KOTOR_AP_DEV") != "1":
            self.output("The /ap_dispatch commands are developer tests and are switched off. "
                        "(Set the environment variable KOTOR_AP_DEV=1 before starting the client to use them.)")
            return False
        return True

    def _cmd_ap_dispatch(self, *parts: str) -> bool:
        """DEVELOPER-ONLY (needs KOTOR_AP_DEV=1): sends one job to the
        game's dispatcher, which applies it at a calm moment, at most once. Actions: notify <text> (shown in a one-line dialog box),
        e.g. /ap_dispatch notify Hello there."""
        if not self._dispatch_dev_only():
            return False
        if not parts:
            self.output("Usage: /ap_dispatch notify <text>")
            return False
        body, _, message = " ".join(parts[1:]).partition("^^")
        self.ctx.dispatcher.submit(parts[0], body.strip(), message=message.strip())
        self.output(f"Dispatcher: queued {parts[0]!r}. Progress is logged as [dispatch] lines.")
        return True

    def _cmd_ap_dispatch_burst(self, count: str = "10") -> bool:
        """DEVELOPER-ONLY: queues <count> notify jobs back to back (sent one at a time) to test the queue."""
        if not self._dispatch_dev_only():
            return False
        n = max(1, min(int(count) if count.isdigit() else 10, 50))
        for i in range(1, n + 1):
            self.ctx.dispatcher.submit("notify", f"Burst job {i} of {n}")
        self.output(f"Dispatcher: queued {n} notify jobs.")
        return True

    def _cmd_ap_dispatch_replay(self) -> bool:
        """DEVELOPER-ONLY: sends the last applied job again with the same number, as a client would after a lost
        confirmation. The game must drop it as a repeat (the log shows 'already applied')."""
        if not self._dispatch_dev_only():
            return False
        last = self.ctx.dispatcher.last_applied
        if last is None:
            self.output("Nothing has been applied yet, so there is nothing to replay.")
            return False
        self.ctx.dispatcher.submit(last.action, last.args, replay_seq=last.seq, message=last.message)
        self.output(f"Dispatcher: replaying job {last.seq} ({last.text}); the game should drop it as already applied.")
        return True

    def _cmd_ap_dispatch_status(self) -> bool:
        """DEVELOPER-ONLY: the dispatcher's counters, the job in flight and the last few results."""
        if not self._dispatch_dev_only():
            return False
        for line in self.ctx.dispatcher.status_lines():
            self.output(line)
        return True

    def _cmd_ap_status(self) -> bool:
        """Show extender connection status and pending/recent deliveries."""
        ext = self.ctx.extender
        self.output(f"Extender: {'CONNECTED' if ext.is_connected else 'not connected'}")
        if self.ctx._character_confirmed is False:
            character = self.ctx.reconciler.current_character_name
            self.output(f"SAFEGUARD ACTIVE: character {character!r} (level {self.ctx.current_level}) unrecognized -- "
                        f"all deliveries/corrections paused. Run /ap_confirm_character if this is intentional.")
        text = self.ctx.dispatcher.window_text()
        for block in (text["waiting"], text["failed"], text["recent"]):
            for line in block.split("\n"):
                if line:
                    self.output(line)
        return True

    def _cmd_ap_autorelease(self, mode: str = "") -> bool:
        """/ap_autorelease [on|off] -- when your goal is complete, the client tells the server
        and sends !release for you (if the room's release permission is "goal" or "enabled"; for
        "auto" the server does it by itself). On by default. With no argument, shows the mode."""
        mode = mode.strip().lower()
        if mode in ("on", "off"):
            self.ctx.auto_release_on_goal = (mode == "on")
            self.output(f"Auto-release on goal: {mode}.")
            return True
        if mode:
            self.output("Usage: /ap_autorelease [on|off]")
            return False
        self.output(f"Auto-release on goal: {'on' if self.ctx.auto_release_on_goal else 'off'} "
                    f"(release permission: {self.ctx.permissions.get('release')}).")
        return True

    def _cmd_ap_roster_cleanup(self, mode: str = "") -> bool:
        """/ap_roster_cleanup [on|log|off] -- the reconciler's Star Forge pass and its fix for entitled companions who are
        listed but cannot be selected. on (default) acts; log only reports what it WOULD do; off disables them. The leak
        purge has its own switch (/ap_leak_purge). With no argument, shows the current mode."""
        tracker = self.ctx.reconciler
        mode = mode.strip().lower()
        if mode in ("on", "log", "off"):
            tracker.roster_cleanup_mode = mode
            self.output(f"Roster cleanup: {mode}.")
            return True
        if mode:
            self.output("Usage: /ap_roster_cleanup [on|log|off]")
            return False
        self.output(f"Roster cleanup: {tracker.roster_cleanup_mode} (in the Star Forge={tracker.roster_in_starforge}, "
                    f"entitlement markers={tracker.current_crew}).")
        return True

    def _cmd_ap_leak_purge(self, mode: str = "") -> bool:
        """/ap_leak_purge [auto|on|log|off] -- the reconciler's purge of a companion on the roster whose entitlement marker (the
        journal quest ap_ent_<key>) is missing or says "trapped off", after it has been seen across 2 area entries. auto
        (default) only reports who it WOULD purge until the Leviathan has been escaped and purges from then on; on always
        purges them; log always only reports; off disables it. With no argument, shows the current mode and who is currently
        a candidate."""
        tracker = self.ctx.reconciler
        mode = mode.strip().lower()
        if mode in ("auto", "on", "log", "off"):
            tracker.leak_purge_mode = mode
            self.output(f"Leak purge: {mode}.")
            return True
        if mode:
            self.output("Usage: /ap_leak_purge [auto|on|log|off]")
            return False
        self.output(f"Leak purge: {tracker.leak_purge_mode} (acting as {tracker.effective_leak_purge_mode()}, "
                    f"Leviathan escaped={tracker.roster_leviathan_done}, candidates={tracker._roster_extras()}, "
                    f"area entries seen={dict(tracker._leak_area_count)}, markers={tracker.current_crew}, "
                    f"story stage={tracker.roster_story_stage}, busy mask={tracker.roster_busy_mask}).")
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


def _load_prior_credit_history() -> typing.Tuple[typing.Dict[tuple, set], set]:
    """Reads DELIVERY_LOG_PATH once, at process start, for the credit accounting: ({(seed_name, slot): indices of the
    credits items already settled in earlier sessions}, {(seed_name, slot) that have any settled entry at all}).
    The reconciler needs it because credit items are replayed on every client start and rebuild its expected total from
    zero, while the credits already in the save include them. Missing/unreadable log = empty, same as _load_delivered_keys."""
    credit_indices: typing.Dict[tuple, set] = {}
    seed_slots: set = set()
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
                if entry.get("outcome") not in _SETTLED_OUTCOMES or "index" not in entry:
                    continue
                pair = (entry.get("seed_name"), entry.get("slot"))
                seed_slots.add(pair)
                if entry.get("arm") == "credits":
                    credit_indices.setdefault(pair, set()).add(entry["index"])
    except (FileNotFoundError, OSError):
        pass
    return credit_indices, seed_slots


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


def _load_trapped_off_companions() -> set:
    """Every (seed_name, slot, npc_key) a Trap: Remove a Companion has permanently removed. The
    trap is meant to be permanent, so this record has to survive a client restart and an item
    replay (the server resends every companion item on each connect, which would otherwise
    entitle the player to the companion again). Written to the delivery log as arm
    "trap_removed:<key>" when the trap lands. Read in log order: a LATER settled "sent" entry for
    that companion's own arm (a real grant or an admin /ap_apply, never a reconciler self-heal,
    which logs "reconciled") puts them back."""
    trapped: typing.Set[typing.Tuple[typing.Optional[str], typing.Optional[str], str]] = set()
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
                ident = (entry.get("seed_name"), entry.get("slot"))
                if arm.startswith("trap_removed:") and entry.get("outcome") in _SETTLED_OUTCOMES:
                    key = arm[len("trap_removed:"):]
                    if key in _REAL_COMPANION_KEYS:
                        trapped.add((*ident, key))
                elif (arm.startswith("companion_") and not arm.startswith("companion_class:")
                      and entry.get("outcome") == "sent"):
                    trapped.discard((*ident, arm[len("companion_"):]))
    except FileNotFoundError:
        pass
    return trapped


def _alignment_state_key(seed_name, slot) -> str:
    return f"{seed_name}|{slot}"


def _load_alignment_state(seed_name, slot):
    """This playthrough's saved alignment state, or None if there is none (or the file is unreadable)."""
    try:
        with open(ALIGNMENT_STATE_PATH, encoding="utf-8") as f:
            return json.load(f).get(_alignment_state_key(seed_name, slot))
    except Exception:
        return None


def _save_alignment_state(seed_name, slot, state: dict) -> None:
    """Writes one playthrough's state, leaving every other playthrough's entry alone. Atomic (temp file + replace), so a crash
    mid-write can't leave a half-written file that loses every playthrough's history."""
    try:
        try:
            with open(ALIGNMENT_STATE_PATH, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
        data[_alignment_state_key(seed_name, slot)] = state
        tmp = ALIGNMENT_STATE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, ALIGNMENT_STATE_PATH)
    except Exception as e:
        logger.warning(f"Could not save {ALIGNMENT_STATE_PATH}: {e}")


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
                    "pc_class_soldier", "pc_class_scout", "pc_class_scoundrel", "pc_droid",
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
        if outcome in ("failed_extender_offline", "failed_extender_rejected")
    }


def _load_pending_traps() -> dict:
    """Reconstructs which received trap: items
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
        # Job dispatcher (kotor_dispatcher.py): one job at a time to the poll, applied by the game at a calm moment. Every delivery goes
        # through it: the bridge's send_* methods are dispatcher jobs (kotor_extender_bridge.py, _submit_job).
        self.dispatcher = DispatchClient(self.extender)
        self.extender.dispatcher = self.dispatcher
        self.extender.on_dispatch_reply = self.dispatcher.on_reply
        self.dispatcher.on_failure = self._log_dispatch_failure
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
        # The Player ID hash the poll last reported for this character: None = not reported yet,
        # "" = the character has no Player ID item, else its 9-character hash. Passive: only recorded on
        # delivery-log lines and compared in _note_player_id(); nothing is paused on it.
        self.save_player_id: typing.Optional[str] = None
        self._player_id_verdict_logged: typing.Optional[str] = None
        self.reconciler = ReconciliationTracker(
            send_apply=self._guarded_send_apply,
            send_apply_value=self._guarded_send_apply_value,
            send_delevel=self._guarded_send_delevel,
            send_heavy=self._guarded_queue_heavy,
            on_death=self._on_local_death,
            is_awaiting_confirmation=self._is_arm_awaiting_confirmation,
            send_purge=self._guarded_send_purge_companion,
            send_unparty=self._guarded_send_unparty_companion,
            send_roster_remove=self._guarded_send_roster_remove_companion,
            send_select=self._guarded_send_select_companion,
        )
        self.location_tracker = LocationTracker()
        self._delivered_count = 0
        self.ui = None
        # 0=ap_gated, 1=normal, 2=none -- set from slot_data on Connect,
        # matching Options.py's CompanionMode default until then.
        self.companion_mode = 0
        # CompanionMode=ap_limited: one companion per 25 of the player's own checks, in a seeded order
        self.companion_unlock_order: typing.List[str] = []
        self._limited_requested: typing.Set[str] = set()
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
        # Archipelago Vendor option (slot_data "archipelago_vendor").
        self.archipelago_vendor = False
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
        # /ap_autorelease: send !release for the player once the goal is complete (see
        # _announce_goal). On by default.
        self.auto_release_on_goal = True
        # asyncio.create_task() returns a Task the event loop only holds a
        # WEAK reference to -- per Python's own docs, an unreferenced task
        # "may get garbage collected at any time, even before it's done."
        # _check_pending_traps() must
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
        # Patching the game files (at Connect, /ap_patch_all, /ap_restore_all) takes a minute or two and the game is usually not running
        # yet; the stale-game warning waits until it is done. A count, so overlapping patch runs nest.
        self._patching_depth = 0
        self._patching_lock = threading.Lock()
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
        self._prior_credit_indices, self._seed_slots_with_history = _load_prior_credit_history()
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
        # Companions a Trap: Remove a Companion has permanently removed (see
        # _load_trapped_off_companions): not entitled, never re-added by the reconciler.
        self._trapped_off_companions: typing.Set[typing.Tuple[typing.Optional[str], typing.Optional[str], str]] = \
            _load_trapped_off_companions()
        self._finalized_companion_classes: typing.Set[typing.Tuple[typing.Optional[str], typing.Optional[str], str]] = \
            _load_finalized_companion_classes()
        self._pc_class_settled: typing.Set[typing.Tuple[typing.Optional[str], typing.Optional[str]]] = \
            _load_pc_class_settled()
        # Area entries seen this session, and when each pending Remove a Companion trap started waiting (in area entries).
        self._area_entries = 0
        self._trap_wait_since: typing.Dict[typing.Tuple[str, str, int], int] = {}
        # The companion a Remove a Companion trap item already picked, so a retry after a missing acknowledgement repeats the same target
        # instead of picking (and removing) another one.
        self._trap_target: typing.Dict[typing.Tuple[str, str, int], str] = {}
        # {(seed_name, slot, index): (item_name, arm_name)} for every
        # received trap: item not yet resolved -- see _load_pending_traps
        # and _check_pending_traps. Every trap resolves on the very next poll cycle.
        self._pending_traps: typing.Dict[typing.Tuple[str, str, int], typing.Tuple[str, str]] = \
            _load_pending_traps()
        # Indices already automatically resent this PROCESS lifetime by
        # _resend_failed_offline_deliveries() -- see that method's own
        # docstring. Purely in-memory (not persisted): a genuinely new
        # process re-derives from the delivery log fresh, and correctly
        # retries again if still stuck; this set only prevents the same
        # index being resent twice within one run (e.g. two reconnects in
        # quick succession).
        self._resent_offline_indices: typing.Dict[int, float] = {}
        # Items the extender rejected: how many timed retries each has had, the keys already explained in the log, and
        # the indices whose automatic retries are paused until the next extender reconnect.
        self._rejected_attempts: typing.Dict[int, int] = {}
        self._rejection_announced: typing.Set[str] = set()
        self._rejected_gave_up: typing.Set[int] = set()
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
        # When the game last applied a death for an incoming DeathLink (0 = never): that death is not sent on as a new DeathLink.
        self._link_death_applied_at = 0.0
        # Same decrementing-synthetic-index trick as _admin_heavy_counter,
        # own counter so it can't collide with that one -- covers the
        # LIGHT reconciler correction paths (_guarded_send_apply/
        # _guarded_send_apply_value/
        # _guarded_send_delevel), which call the extender bridge directly
        # and never pass through _do_deliver, so they need their own
        # _log_delivery call rather than inheriting one.
        self._reconciler_light_counter = 0
        # Thinning of routine per-poll lines in the log (see _log_game_event).
        self._routine_last: typing.Dict[str, str] = {}
        self._routine_repeats: typing.Dict[str, int] = {}

    def _track_background_task(self, task: "asyncio.Task") -> None:
        """Pairs with self._background_tasks (see __init__) -- keeps the
        strong reference until done, THEN checks whether the task actually
        finished with an unhandled exception before discarding it.
        Without this, a real bug inside _resolve_trap() (unrelated to
        the GC issue that set exists to fix) would still vanish silently: asyncio's own default handler
        for an unretrieved task exception only logs through its OWN
        internal logger, not game_events_logger, so it may never actually
        surface in this console. Logs loudly instead, through the same
        channel every other visible [game]/[extender] line already uses."""
        self._background_tasks.discard(task)
        if not task.cancelled():
            exc = task.exception()
            if exc is not None:
                game_events_logger.error(f"[background task FAILED] {task.get_name()}: {exc!r}", exc_info=exc)

    def _log_dispatch_failure(self, job, reason: str) -> None:
        """A dispatcher job that failed for good (kotor_dispatcher.DispatchClient.on_failure): one delivery log line with the
        reason. Outcome "failed_dispatch" is not a settled outcome and is not retried by the offline/rejected resend."""
        character = getattr(self.reconciler, "current_character_name", "") or ""
        arm = f"dispatch:{job.action}" + (f":{job.args}" if job.args else "")
        self._log_delivery(character, job.index, job.item_name or arm, arm, "failed_dispatch", detail=reason)

    def _log_delivery(self, character: str, index: int, item_name: str, arm_name: str, outcome: str, detail: str = "") -> None:
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
        # (trap: arms) never set this in the first place
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
                if outcome == "sent":
                    # a real grant or an admin /ap_apply puts a trapped-off companion back
                    # (a reconciler self-heal logs "reconciled" and does not).
                    self._trapped_off_companions.discard((seed_name, slot, arm_name[len("companion_"):]))
            elif arm_name in ("pc_class_soldier", "pc_class_scout", "pc_class_scoundrel", "pc_droid"):
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
        if detail:
            entry["detail"] = detail
        if self.save_player_id is not None:
            # The Player ID hash the loaded character carries ("none" = no such item). Audit only.
            entry["save_id"] = self.save_player_id or "none"
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

    def _companion_present_now(self, npc_key: str) -> bool:
        """Additional Feats feature: is this companion in the party right now, by the game's own live reports -- on the roster, carrying
        the entitlement marker (10, not trapped off) and with no scene or transition busy? The recruited record
        (_is_companion_recruited) only says a join was once sent. False while either report is still missing."""
        recon = self.reconciler
        if recon.current_roster is None or recon.current_crew is None or recon.roster_busy:
            return False
        if npc_key in recon._trapped_keys():
            return False
        entitled = recon._entitled_keys()
        return bool(recon.current_roster.get(npc_key)) and entitled is not None and npc_key in entitled

    def _is_pc_class_finalized(self) -> bool:
        """Additional Feats feature: PC equivalent of
        _is_companion_class_finalized. StartingClass=random_class applies
        immediately/automatically at game start (not item-gated), so this
        is near-instantly true in practice -- tracked properly anyway
        rather than assumed."""
        if (self.seed_name, getattr(self, "username", None)) in self._pc_class_settled:
            return True
        return self.starting_class not in (3, 4)  # random_class, droid

    def _persist_alignment_state(self) -> None:
        """Writes the tracker's alignment state when it changed since the last write (readings arrive every poll, changes are rare)."""
        state = self.location_tracker.alignment_state()
        if state == getattr(self, "_saved_alignment_state", None):
            return
        slot = getattr(self, "username", None)
        if not self.seed_name or not slot:
            return
        self._saved_alignment_state = state
        _save_alignment_state(self.seed_name, slot, state)

    def _check_pending_traps(self) -> None:
        """Runs once per poll cycle (see _on_extender_event's SKILLREPORT
        hook). Every pending trap resolves on the VERY NEXT cycle after
        receipt -- there's no recruited/class-finalized gate to wait on; whatever state a given trap_type needs
        (current feats/powers/inventory/abilities/level/companions) is
        always current by the time a poll cycle has completed at least
        once. Cheap to run unconditionally every cycle: this dict is
        normally empty."""
        if not self._pending_traps:
            return
        for key in list(self._pending_traps.keys()):
            item_name, arm_name = self._pending_traps[key]
            trap_type = arm_name.split(":", 1)[1]
            if trap_type == "remove_companion" and not item_name.startswith("(admin)"):
                recorded = self._removable_companions(live_only=False)
                if recorded and not self._removable_companions(live_only=True):
                    # Recruited by the delivery record but not present by the live reports (or just given feats): wait, up to a limit.
                    since = self._trap_wait_since.setdefault(key, self._area_entries)
                    if self._area_entries - since < TRAP_COMPANION_WAIT_AREAS:
                        continue
            self._trap_wait_since.pop(key, None)
            del self._pending_traps[key]
            task = asyncio.create_task(self._resolve_trap(key, item_name, arm_name, trap_type))
            self._background_tasks.add(task)
            task.add_done_callback(self._track_background_task)

    def _complete_removed_companion_checks(self, npc_key: str) -> None:
        """A companion trapped off for good can never reach their personal Ebon Hawk checks again, and those checks may hold items
        (including a companion's own). Sends the ones that are still open, using the same record as every other check: the
        server's checked locations plus what this session has already sent."""
        if not self.server:
            return
        already = self.checked_locations | self.locations_checked
        loc_ids = [i for i in self.location_tracker.checks_for_removed_companion(npc_key, already)
                   if i in self.missing_locations]
        if not loc_ids:
            return
        self.locations_checked.update(loc_ids)
        for loc_id in loc_ids:
            logger.info(f"[check] {self.location_names[self.game].get(loc_id, str(loc_id))} "
                        f"(completed: {npc_key} was removed by the trap and can no longer reach it)")
        asyncio.create_task(self.send_msgs([{"cmd": "LocationChecks", "locations": loc_ids}]))

    def _removable_companions(self, live_only: bool) -> typing.List[str]:
        """Companions the Remove a Companion trap may pick, from the current seed's recruited record. With live_only, also
        required: present by the game's own reports (on the roster, entitlement marker 10, nothing busy) and not just given
        Additional Feats."""
        current_seed_slot = (self.seed_name, getattr(self, "username", None))
        already_trapped = self._trapped_off_keys()
        out = sorted(npc for (sn, sl, npc) in self._recruited_companions
                     if (sn, sl) == current_seed_slot and npc not in already_trapped)
        if live_only:
            out = [npc for npc in out
                   if self._companion_present_now(npc)]
        return out

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
        as the other deliveries."""
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
            # WHICH skill is still picked here from the cached eligibility
            # list (Python already has the full known-skill snapshot;
            # NWScript would need to query all 8 live to replicate this
            # selection, not worth it just for choosing a target). The
            # decrease AMOUNT is no longer computed here -- see
            # build_trap_block's own comment for the real bug this closes
            # (reconciler.current_skills is only as fresh as the last
            # SKILLREPORT poll and can be stale relative to the true live
            # rank). params is now just the chosen skill_key; NWScript
            # reads the live rank and computes/guards the decrease itself.
            # Eligibility is judged on the TRUE ranks when they've been
            # reported: current_skills holds GetSkillRank (rank + ability
            # modifier + effects), so a skill sitting at rank 0 can still read
            # above 0 and would be picked for a halving that has nothing to
            # halve. Falls back to current_skills only for an extender build
            # that predates SKILLBASEREPORT.
            rank_source = (reconciler.current_skill_bases
                           if any(v is not None for v in reconciler.current_skill_bases.values())
                           else reconciler.current_skills)
            eligible = [k for k, v in rank_source.items() if v is not None and v > 0]
            if not eligible:
                self._trap_noop(key, item_name, arm_name, "no skill above 0 to reduce")
                return
            skill_key = random.choice(eligible)
            sent = await self.extender.send_trap("reduce_skill", skill_key, message=item_name)

        elif trap_type == "remove_half_feats":
            # the full list (FEATFULL, about once a minute); FEATREPORT alone carries only the
            # reconciler's feats of interest
            held = list(reconciler.full_feats if reconciler.full_feats is not None
                        else reconciler.current_feats)
            if len(held) <= 1:
                self._trap_noop(key, item_name, arm_name, f"only {len(held)} known feat(s)")
                return
            chosen = random.sample(held, len(held) // 2)
            params = ",".join(str(i) for i in chosen)
            sent = await self.extender.send_trap("remove_half_feats", params, message=item_name)

        elif trap_type == "remove_half_powers":
            held = list(reconciler.current_powers)
            if len(held) <= 1:
                self._trap_noop(key, item_name, arm_name, f"only {len(held)} known force power(s)")
                return
            chosen = random.sample(held, len(held) // 2)
            params = ",".join(str(i) for i in chosen)
            sent = await self.extender.send_trap("remove_half_powers", params, message=item_name)

        elif trap_type == "cut_max_hp":
            # The CON-decrease search and the "already minimal" no-op check
            # both happen natively at delivery time, reading true live CON
            # and both class slots directly (see build_trap_block's own
            # comment) -- NOT from reconciler.current_abilities/
            # current_classes, which are only as fresh as the last
            # ABILITYREPORT/CLASSREPORT poll. No meaningful params needed;
            # "-" is a placeholder, same convention as reduce_str/etc. above.
            sent = await self.extender.send_trap("cut_max_hp", "-", message=item_name)

        elif trap_type == "remove_companion":
            # Filtered to the CURRENT (seed_name, slot), not the whole
            # _recruited_companions set -- otherwise a stale admin-test
            # entry from a different seed/slot could get "removed" from a
            # player who never actually had that companion. See
            # _load_recruited_companions' docstring.
            current_seed_slot = (self.seed_name, getattr(self, "username", None))
            target = self._trap_target.get(key)
            if target is None:
                candidates = self._removable_companions(live_only=not item_name.startswith("(admin)"))
                if not candidates:
                    self._trap_noop(key, item_name, arm_name, "no companion is recruited and present right now")
                    return
                target = random.choice(candidates)
                self._trap_target[key] = target
            # purge_companion, not remove_companion: the latter only calls RemoveAvailableNPC,
            # which ejects an ACTIVE party member from the roster but leaves the creature
            # object standing in the area. A game froze on the next transition after
            # that trap landed (and again on every reload of the save made in that state).
            # purge_companion also takes them out of the party and destroys the standing
            # objects -- the form the roster cleanup has used live without trouble.
            # trap_companion is that same removal plus the entitlement marker ap_ent_<key> written as 20
            # ("trapped off for good"), which the grant arms refuse and the reconciler treats as a leak.
            # remove_companion stays as the roster-only trap the Star Forge pass needs.
            first_send = (*current_seed_slot, target) not in self._trapped_off_companions
            sent = await self.extender.send_trap("trap_companion", target, message=item_name)
            if sent and first_send:
                # Untrack immediately, not just on confirmation -- the
                # companion arms' own untrack-on-confirm equivalent
                # doesn't exist (recruit tracking only ever ADDS, see
                # _load_recruited_companions), and leaving this stale
                # would incorrectly let a later Additional Feats/
                # companion_class action target a companion that was
                # just removed.
                self._recruited_companions.discard((*current_seed_slot, target))
                # PERMANENT: record it (delivery log, so it survives a restart and the item
                # replay on reconnect) and tell the reconciler, which otherwise treats the
                # companion as entitled (their item was received) and would add them back.
                self._trapped_off_companions.add((*current_seed_slot, target))
                self._reconciler_light_counter -= 1
                self._log_delivery(character, self._reconciler_light_counter,
                                   f"(trap) permanently removed {target}", f"trap_removed:{target}", "sent")
                self.reconciler.trapped_off_companions = self._trapped_off_keys()
                self._complete_removed_companion_checks(target)

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
            sent = await self.extender.send_trap("remove_half_inventory", "-", message=item_name)

        elif trap_type in ("reduce_str", "reduce_dex", "reduce_int", "reduce_wis", "reduce_cha"):
            # Decrease amount and the "already minimal" no-op check both
            # happen natively at delivery time, reading the true live base
            # score (see build_trap_block's own comment) -- NOT from
            # reconciler.current_abilities, which is only as fresh as the
            # last ABILITYREPORT poll and can be stale relative to the true
            # live score. No meaningful params needed; "-" is a placeholder
            # (ap_extender.c's APPLYVALUE: parser needs a non-empty token),
            # same convention as remove_half_inventory above.
            sent = await self.extender.send_trap(trap_type, "-", message=item_name)

        elif trap_type == "remove_credits":
            # A REAL item takes _deliver_item's direct shortcut and never
            # lands here; this branch exists for TrapLink, whose
            # locally-rolled trap can be any of the 12 and goes
            # through _pending_traps like everything else. Same
            # set_credits:0 send, same reconciler-clamp safety argument as
            # that shortcut's comment.
            sent = await self.extender.send_apply_value("set_credits", 0, message=item_name)

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
            if trap_type == "remove_companion":
                # The wire action is trap_companion (see that branch), so that is the key the extender acks under.
                # Waiting on the trap's own name, or on an older wire name, never matched: the send was treated as
                # failed and retried, and each retry removed another companion.
                staged_key = "trap:trap_companion"
            sent = await self.extender.wait_staged(staged_key)
        if sent:
            logger.info(f"[queued for game] {item_name} -> trap:{trap_type}")
            self._trap_target.pop(key, None)
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
                                    f"lands once the game is calm")
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
        self.save_player_id = None
        self._player_id_verdict_logged = None
        game_events_logger.info("[extender] reconnected -- reconciler live-state cleared, waiting for fresh reports.")
        try:
            asyncio.get_running_loop().run_in_executor(None, self._clear_staged_and_log)
        except RuntimeError:
            self._clear_staged_and_log()
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
        # A delivery is tried again on every extender reconnect, but not twice within 30 s (two reconnects in a row).
        now = time.time()
        stuck = {index: pair for index, pair in stuck.items() if now - self._resent_offline_indices.get(index, 0.0) > 30.0}
        if not stuck:
            return
        game_events_logger.info(
            f"[extender] retrying {len(stuck)} item(s) that did not reach the game earlier...")
        for index, (item_name, arm_name) in stuck.items():
            if not arm_name or arm_name == GOAL_MARKER_ARM:
                continue
            self._resent_offline_indices[index] = now
            self._rejected_attempts.pop(index, None)
            self._rejected_gave_up.discard(index)
            asyncio.create_task(self._deliver_item(item_name, arm_name, index))

    # Routine per-poll lines (the report lines, the journal/quest/plot/companion checks, alignment and
    # similar) repeat unchanged every 5 s. They are still handled in full below (the reconciler and
    # tracker see every one); only the LOG copy is thinned: a routine line is logged when its content
    # changes and then once per _ROUTINE_REPEAT_EVERY identical repeats, so the log still shows the
    # poll is alive (a silent death is a missing periodic line) without a thousand copies of the same
    # state. Event lines (AREA, APPLIED, SAFEGUARD, POLLRUN, ticks, ...) are never thinned.
    _ROUTINE_MSG_RE = re.compile(
        r'msg="(AP\|(?:CHECK\|(?:JOURNAL|QUEST|PLOT|COMPANION)\|[^|"]*|[A-Z]*REPORT|ALIGNMENT|PARTYLEVELS|DATAPAD|AREASVISITED|PLAYERID|BOUNTY\|COUNT)[^"]*)"')
    _ROUTINE_REPEAT_EVERY = 12

    def _log_game_event(self, event: str) -> None:
        m = self._ROUTINE_MSG_RE.search(event)
        if m is None:
            game_events_logger.info(f"[game] {event}")
            return
        msg = m.group(1)
        parts = msg.split("|")
        key = "|".join(parts[:3]) if parts[1] == "CHECK" else parts[1]
        last = self._routine_last.get(key)
        if last == msg:
            n = self._routine_repeats.get(key, 0) + 1
            self._routine_repeats[key] = n
            if n % self._ROUTINE_REPEAT_EVERY:
                return
        else:
            self._routine_last[key] = msg
            self._routine_repeats[key] = 0
        game_events_logger.info(f"[game] {event}")

    def _note_player_id(self, event: str) -> None:
        """Records the Player ID the poll reports for the loaded character and compares it with the connected
        seed and slot. PASSIVE: it only sets save_player_id (written on delivery-log lines) and logs the verdict
        once per change; nothing is paused or blocked, and the new-character safeguard is unchanged. A character
        with no Player ID item (a run started before it existed, or the item was removed) is normal."""
        m = _PLAYERID_RE.search(event)
        if m is None:
            return
        name = m.group(1).strip()
        # The shipped placeholder template (patch_player_id.py PLACEHOLDER_NAME) is what a new game is given
        # when it starts before any seed was ever connected: a real item, but not stamped with a seed.
        unstamped = name.endswith("no seed yet")
        found = "" if name == "NONE" else ("unstamped" if unstamped else name.rsplit(" ", 1)[-1])
        self.save_player_id = found
        slot = getattr(self, "username", None)
        if not self.seed_name or not slot:
            return
        if not found:
            verdict = "none"
        elif unstamped:
            verdict = "unstamped"
        elif found == save_id_for(self.seed_name, slot):
            verdict = "match"
        else:
            verdict = "mismatch"
        if verdict == self._player_id_verdict_logged:
            return
        self._player_id_verdict_logged = verdict
        if verdict == "match":
            game_events_logger.info(f"[PLAYERID] Player ID {found} matches the connected seed and slot.")
        elif verdict == "none":
            game_events_logger.info("[PLAYERID] This character has no Player ID item (started before it existed, "
                                    "or the item was removed). Passive check only: nothing is paused.")
        elif verdict == "unstamped":
            game_events_logger.info("[PLAYERID] This character's Player ID was created before any seed was connected, "
                                    "so it records no seed. Passive check only: nothing is paused.")
        else:
            game_events_logger.warning(
                f"[PLAYERID] This character carries Player ID {found}, but the connected seed and slot hash to "
                f"{save_id_for(self.seed_name, slot)}. It may belong to a different seed. Passive check only: "
                "nothing is paused (the character-name safeguard is the active guard).")

    def _on_extender_event(self, event: str) -> None:
        # Surface every AP| marker to its own "Heartbeat" GUI tab (not the
        # main "Archipelago" tab) -- this is the raw heartbeat/status-poll
        # firehose (XPREPORT, INVENTORY, CHECK|AREA, TRAMPOLINE_BATCH_FIRED,
        # etc.), useful for debugging but not part of the curated 4-item
        # summary (extender connecting, AP server connecting, checks found,
        # items sent) the main tab is scoped to.
        self._log_game_event(event)
        self.dispatcher.on_event(event)
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
        self._note_player_id(event)
        self._evaluate_character_safety()
        # Computed once per event (this runs on every single extender
        # event, a real hot path during gameplay) and reused below for
        # both location-check dedup and the ap_limited XP formula (own
        # checks completed x experience_limiter), which needs this
        # event's up-to-date count including any check THIS event itself
        # just added a moment earlier in this same method.
        already = self.checked_locations | self.locations_checked
        self.reconciler.checked_location_count = len(already)
        if self.companion_mode == 3:  # ap_limited
            self._grant_limited_companions(len(already))
        self.reconciler.handle_event(event)
        if "AP|CHECK|AREA|" in event:
            self._area_entries += 1

        if "AP|SKILLREPORT|" in event:
            # Same "poll cycle complete" marker ReconciliationTracker uses
            # (poll_shared's own LAST report each cycle). Traps: every pending
            # trap resolves on the very next cycle after receipt (the state
            # each trap_type needs is always available by the time a poll
            # cycle finishes).
            self._check_pending_traps()

        if self.server:
            # Usually 0 or 1 id, but an alignment jump can cross several
            # 10-point thresholds in one poll -- see kotor_location_tracker.py.
            loc_ids = self.location_tracker.check_event(event, already)
            # Only locations this slot has: the optional checks (quest items, Bazaar, bounty cards) are missing from slots that turned
            # them off, and the server does not accept an id outside the slot.
            if self.server_locations:
                loc_ids = [i for i in loc_ids if i in self.server_locations]
            if "AP|ALIGNMENT|" in event:
                self._persist_alignment_state()
            if loc_ids:
                self.locations_checked.update(loc_ids)
                # Checks completed because the Ebon Hawk left Taris (kotor_location_tracker.py): the player never reached them.
                released = set(loc_ids) & self.location_tracker.last_release_ids
                for loc_id in loc_ids:
                    name = self.location_names[self.game].get(loc_id, str(loc_id))
                    logger.info(f"[check] {name}" + (" (released on leaving Taris)" if loc_id in released else ""))
                asyncio.create_task(self.send_msgs([{"cmd": "LocationChecks", "locations": loc_ids}]))
                if released:
                    many = len(released) != 1
                    asyncio.create_task(self.extender.send_notify(
                        f"Leaving Taris: {len(released)} check{'s' if many else ''} you did not reach {'were' if many else 'was'} released."))

                # vanilla companion mode: the check still fires (for
                # tracking), but the companion is self-granted immediately
                # instead of waiting on a received AP item -- see
                # Options.py's CompanionMode docstring.
                # Not for a Juhani who died: her recruit check is completed because she can no longer be recruited, so
                # granting her here would bring back a companion the story killed.
                # Nor for a companion check released on leaving Taris: that companion was never recruited and cannot be now.
                if self.companion_mode == 1 and not JUHANI_KILLED_RE.search(event):
                    for loc_id in loc_ids:
                        if loc_id in released:
                            continue
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

    @contextlib.contextmanager
    def _patching(self):
        """Marks the game-file patching as running (it can be called from a worker thread). While it runs no stale-game warning is due; when the
        last patch run ends, the silence timer starts again from that moment, so a warning can only come after patching is finished."""
        with self._patching_lock:
            self._patching_depth += 1
        try:
            yield
        finally:
            with self._patching_lock:
                self._patching_depth -= 1
                if self._patching_depth == 0:
                    self._last_game_event_time = time.time()
                    self._staleness_warned = False

    def _staleness_due(self) -> typing.Optional[float]:
        """The seconds of silence from the game if a stale warning should be given now, else None."""
        if self._patching_depth > 0 or self._staleness_warned:
            return None
        idle = time.time() - self._last_game_event_time
        return idle if idle > 30 else None

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
            idle = self._staleness_due()
            if idle is not None:
                self._staleness_warned = True
                if not self.extender.is_connected:
                    game_events_logger.warning(
                        f"[STALE] No message from the game in {int(idle)}s, and this client is not connected to it. "
                        f"Most likely KOTOR is not running yet: start the game (items and checks only flow while it "
                        f"is open). If the game IS running and this stays, the mod is not loaded: close KOTOR, run "
                        f"Install.bat again, then start the game and keep this client open.")
                    continue
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
        reached = False
        if self.goal == 0:  # defeat_malak
            if _GOAL_MALAK_RE.search(event):
                game_events_logger.info("[goal] Malak defeated -- goal complete!")
                reached = True
        elif self.goal == 1:  # true_balance
            if self.location_tracker.true_balance_reached(self.checked_locations | self.locations_checked):
                game_events_logger.info("[goal] True Balance reached (both alignment extremes) -- goal complete!")
                reached = True
        elif self.goal == 2:  # max_level
            m = _LEVEL_RE.search(event)
            if m and int(m.group(1)) >= MAX_LEVEL:
                game_events_logger.info(f"[goal] Max level ({MAX_LEVEL}) reached -- goal complete!")
                reached = True
        elif self.goal == 3:  # reach_leviathan
            if _GOAL_LEVIATHAN_RE.search(event):
                game_events_logger.info("[goal] Reached the Leviathan -- goal complete!")
                reached = True
        if reached:
            self.finished_game = True
            task = asyncio.create_task(self._announce_goal())
            self._background_tasks.add(task)
            task.add_done_callback(self._track_background_task)

    async def _announce_goal(self) -> None:
        """Tells the server the goal is complete, then (if auto_release_on_goal) releases the
        rest of this world's items.

        Setting finished_game alone does NOT tell the server: CommonContext only reads it to
        resend the status after a RECONNECT (CommonClient.py's Connected handler). Until this was
        added a finished run sat at "playing" on the server (nothing released, no goal shown)
        until the client happened to reconnect.

        Release: with the room's release permission "goal" (manual after goal) the player has to
        type !release, which is what is sent here; "auto"/"auto_enabled" mean the server does it
        itself, "disabled" means it is not allowed, so nothing is sent for those. Also skipped
        when /ap_autorelease is off."""
        await self.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])
        game_events_logger.info("[goal] Goal status sent to the server.")
        if not self.auto_release_on_goal:
            return
        permission = str(self.permissions.get("release", "disabled"))
        if permission not in ("goal", "enabled"):
            game_events_logger.info(f"[goal] Release permission is {permission!r}: no !release sent "
                                    f"({'the server releases by itself' if permission.startswith('auto') else 'not allowed'}).")
            return
        await asyncio.sleep(3.0)  # let the server process the goal status first
        await self.send_msgs([{"cmd": "Say", "text": "!release"}])
        game_events_logger.info("[goal] Sent !release -- the remaining items are being released.")

    def _on_local_death(self) -> None:
        """Called by ReconciliationTracker once per death episode -- see its
        _cycle_saw_death/_was_dead dedup. Outgoing DeathLink half.

        A death this client itself caused for an incoming DeathLink is not sent on: otherwise two linked players would kill each other
        in turn for ever (see _apply_link_death)."""
        if time.time() - self._link_death_applied_at < LINK_DEATH_ECHO_SECONDS:
            self._link_death_applied_at = 0.0
            game_events_logger.info("[deathlink] this death was caused by an incoming DeathLink: not sent on.")
            return
        asyncio.create_task(self.send_death("died in the Star Wars galaxy."))

    def on_deathlink(self, data: dict) -> None:
        """Incoming DeathLink half -- another linked player died, kill this
        one too via the force_death arm (see extender/scripts_src and
        generate_trampoline_batch.py's APPLIES[32])."""
        super().on_deathlink(data)
        if not self.extender.is_connected:
            game_events_logger.warning("DeathLink received but extender isn't connected -- not applied.")
        else:
            # A dispatcher job: held until the game is calm (not for combat), applied once, and never replayed after a save is loaded
            # (kotor_dispatcher.DEATH_ARMS), so reloading from a death cannot kill the player again.
            asyncio.create_task(self._apply_link_death())

    async def _apply_link_death(self) -> None:
        """Sends the death job and, once the game has applied it, notes the time so the death the poll sees a moment later is
        recognised as caused by the link (see _on_local_death)."""
        if not await self.extender.send_apply("force_death"):
            return
        job = self.extender._jobs.get("force_death")
        if job is None:
            return
        await job.done.wait()
        if job.state == "applied":
            self._link_death_applied_at = time.time()

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
            problem = world_version_problem(args.get("slot_data") or {})
            if problem:
                if os.environ.get("KOTOR_AP_DEV") == "1":
                    game_events_logger.warning(f"[world version] {problem} (developer mode: continuing anyway)")
                else:
                    logger.error(f"[world version] {problem}")
                    asyncio.create_task(self.disconnect())
                    return
            # _delivered_count must be reset here, not just in __init__:
            # switching to a DIFFERENT slot without restarting this Python
            # process (a second slot after the first) otherwise
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
            # (expected_scalar/_skill_baseline/expected_companions,
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
                # Raw mode value (0=off/1=coupled/2=decoupled), not forced to
                # bool -- scripts/review_door_mapping.py needs to tell the
                # two on-modes apart. Every OTHER consumer of area_randomizer
                # in this file only ever needs on/off (self.area_randomizer
                # below, regenerate_poll_shared's CheckPlanetAvailability
                # gating) and stays a plain bool, cast where it's read.
                slot_data.get("area_randomizer", 0), slot_data.get("starting_class", 0),
                slot_data.get("additional_enemies_mode", 0), self.seed_name,
                bool(slot_data.get("progression_system", False)),
                bool(slot_data.get("galactic_shop", False)),
                slot_data.get("new_companion", 0),
                slot_data.get("door_mapping_repairs", []),
                bool(slot_data.get("archipelago_vendor", False)),
                slot_data.get("companion_class_mode", 0), slot_data.get("companion_droid_plan", {}),
                new_companion_classes=slot_data.get("new_companion_classes", {}),
                bazaar=bool(slot_data.get("bazaar", slot_data.get("bazaar_purchases", False) or slot_data.get("loot_exchange", False))))  # the old keys: a seed made before the options were merged
            self.archipelago_vendor = bool(slot_data.get("archipelago_vendor", False))
            self.companion_mode = slot_data.get("companion_mode", 0)
            self.companion_unlock_order = list(slot_data.get("companion_unlock_order", []))
            self._limited_requested = set()
            # Entitlement for any roster decision comes from the journal markers in the save (ap_ent_<key>), not from this client's
            # records; the trapped-off record below only stops the reconciler re-granting a companion the trap removed.
            self.reconciler.trapped_off_companions = self._trapped_off_keys()
            self.companion_class_rolls = slot_data.get("companion_class_rolls", {})
            self.companion_class_mode = slot_data.get("companion_class_mode", 0)
            # (runs inside _apply_module_rim_patches_in_order below, not as its own task)
            self.reconciler.experience_mode = slot_data.get("experience_mode", 0)
            self.reconciler.experience_limiter = slot_data.get("experience_limiter", 600)
            self.reconciler.experience_item = slot_data.get("experience_item", 4000)
            self.reconciler.credit_mode = slot_data.get("credit_mode", 0)
            self.reconciler.credit_limiter = slot_data.get("credit_limiter", 100)
            self.reconciler.credit_item = slot_data.get("credit_item", 5000)
            # What earlier client sessions already put into the save's credits (see _load_prior_credit_history).
            seed_slot = (self.seed_name, getattr(self, "username", None))
            self.reconciler.resume_credit_cap = len(self._prior_credit_indices.get(seed_slot, ())) * self.reconciler.credit_item
            self.reconciler.resume_credit_cap_from_current = seed_slot in self._seed_slots_with_history
            # Own copy on the tracker, same seed-config data as
            # self.companion_class_rolls above -- entitlement.py's
            # compute_entitlement() reads it off the tracker it's passed,
            # not off KotorContext, so it needs to live there too.
            self.reconciler.companion_class_rolls = slot_data.get("companion_class_rolls", {})
            current_slot = (self.seed_name, getattr(self, "username", None))
            # This playthrough's saved alignment history (the last value seen): restored here, once seed and slot are
            # known, so it carries across client restarts.
            self.location_tracker.restore_alignment_state(_load_alignment_state(*current_slot))
            self._saved_alignment_state = self.location_tracker.alignment_state()
            self.consumable_stack_count = slot_data.get("consumable_stack_count", 3)
            self.shop_item_count = slot_data.get("shop_item_count", 0)
            self.goal = slot_data.get("goal", 0)
            asyncio.create_task(self.update_death_link(bool(slot_data.get("death_link", False))))
            # TrapLink / Galactic Shop -- see fill_slot_data.
            self.trap_link = bool(slot_data.get("trap_link", False))
            self.traps_mode = int(slot_data.get("traps_mode", 0))
            asyncio.create_task(self.update_trap_link(self.trap_link))
            self.galactic_shop = bool(slot_data.get("galactic_shop", False))
            # (Galactic Shop's module edit also runs inside _apply_module_rim_patches_in_order)
            # Universal, not gated by any option -- see apply_shop_item_costs()'s
            # own docstring for why this always runs regardless of slot_data.
            asyncio.get_event_loop().run_in_executor(None, self._apply_shop_item_costs_and_log)
            # Also universal -- see apply_area_poll_hooks().
            # (runs inside _apply_module_rim_patches_in_order -- it edits a module file)
            # Also universal -- see apply_ap_tracker_quest()'s own docstring
            # for why this must run against THIS install's dialog.tlk on
            # every Connect rather than shipping a pre-baked global.jrl.
            asyncio.get_event_loop().run_in_executor(None, self._apply_ap_tracker_quest_and_log)
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

            lookup = self.location_names[self.game]
            n_locations = len([lid for lid in lookup if lid >= 0])
            # Feeds the journal-tracker reconciliation branch's percentage
            # calc (checked_location_count / total_location_count) -- the
            # other half already lands every event, see handle_event()'s
            # own checked_location_count assignment.
            self.reconciler.total_location_count = n_locations
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

    def _reseed_expected_state(self, arm_name: str) -> None:
        """Rebuilds the reconciler's "what should I have" memory from an item that was delivered in
        an earlier client session. The reconciler fills expected_companions, expected_pc_class,
        expected_progression_items and companion_class_items (a Jedi Training item's class) only through note_item_received(), which _deliver_item calls when
        it actually sends; after a client restart the server replays every item, each already-settled
        one returns early, and those three would stay empty -- so the missing-companion resend, the
        PC-class self-heal (all six class arms) and the progression-item re-grant would do nothing
        until a fresh item arrived. Only these groups are re-noted. Skills and abilities are
        NOT: their expected values are bootstrapped from the live game on the first poll, so
        re-adding every past grant would double count; xp and credits already have their own replay.
        Nothing is sent and none of the new-recruit follow-ups run -- this only restores memory.
        A companion removed by the Remove a Companion trap stays out (reconciler.trapped_off_companions)."""
        if arm_name.startswith("companion_") and not arm_name.startswith("companion_class:"):
            self.reconciler.note_item_received(arm_name)
        elif arm_name.startswith("companion_class:"):
            self.reconciler.note_item_received(arm_name)        # a Jedi Training item: the companion's expected class
        elif arm_name in ("class_guardian", "class_consular", "class_sentinel",
                          "pc_class_soldier", "pc_class_scout", "pc_class_scoundrel", "pc_droid"):
            self.reconciler.note_item_received(arm_name)
        elif arm_name.startswith("give_item:"):
            resref = arm_name.split(":")[1] if ":" in arm_name else ""
            if resref in PROGRESSION_ITEM_RESREFS.values():
                self.reconciler.note_item_received(arm_name)

    async def _deliver_item(self, item_name: str, arm_name: str, index: int) -> None:
        # Goal markers ("Reached Level 20", "Malak Defeated", ...) are real
        # items so the goal can be a generation-time completion condition,
        # but there is nothing to apply in game. Sending one to the extender
        # only produces "ERROR:unknown item", and while the extender is
        # offline it would be logged as an undelivered grant.
        if arm_name == GOAL_MARKER_ARM:
            game_events_logger.info(f"[goal marker] {item_name} -- progress marker, nothing to apply in game")
            return
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
            self._reseed_expected_state(arm_name)
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

        if arm_name == "trap:remove_credits":
            # The one trap that's a byte-for-byte reuse of an
            # already-existing action (set_credits) -- no new wire action,
            # no pending/resolution step needed, just fire it directly.
            # Zeroing credits is safe under credit_mode's reconciliation
            # clamp too: kotor_reconciliation.py's baseline tracking
            # (_credit_baseline) treats ANY drop in credits between polls
            # as legitimate and applies it straight to the baseline -- the
            # clamp won't try to "restore" this.
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
            # as every client-side decision -- _check_pending_traps (run every poll
            # cycle) computes the real specifics from currently-tracked
            # state and resolves it.
            #
            # _pending_heavy_indices.add() here closes a real bug: without
            # it, this "pending" outcome doesn't register in _delivered_keys
            # (only a terminal outcome does) AND wasn't registered in any
            # in-flight guard either, so a second _deliver_item() call for
            # this same index (e.g. two overlapping ReceivedItems dispatches
            # around connect/reconnect) would queue a SECOND, fully
            # independent resolution before the first one ever reaches
            # _log_delivery's "sent". Confirmed: a fresh save, one
            # real item, three full reduce_dex apply cycles at the same
            # instant. Ability/skill traps use EffectAbilityDecrease/
            # EffectSkillDecrease, which stack unconditionally on every
            # application -- there's no downstream idempotency to fall back
            # on, so the race has to be closed here instead. The existing
            # check at this function's top (`if (character, index) in
            # self._pending_heavy_indices`) already covers every arm type
            # generically; traps just never opted into setting it before.
            # _log_delivery's own unconditional discard() releases this
            # once a real terminal outcome (settled or noop-as-"sent")
            # gets logged, same as HEAVY_ARMS/companion_class already do.
            self._pending_heavy_indices.add((character, index))
            self._pending_traps[(self.seed_name, getattr(self, "username", None), index)] = (item_name, arm_name)
            self._log_delivery(character, index, item_name, arm_name, "pending")
            game_events_logger.info(f"[pending] {item_name} -> resolving next poll cycle")
            return

        if is_heavy_arm(arm_name):
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
            # never a HEAVY_ARMS set entry itself -- a colon-parameterized
            # string can't be. is_heavy_arm() covers it via its
            # startswith("companion_") check instead (see entitlement.py).
            self._pending_heavy_indices.add((character, index))
            # is_correction=False -- a real item is never a correction, see
            # _queue_heavy's own docstring for what that flag gates.
            await self._heavy_queue.put((item_name, arm_name, index, character, False))
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

    def _apply_seed_patch_if_new(self, key: str, gate_key: str | None, apply_fn, force: bool = False,
                                 verify=None) -> None:
        """Shared gate for the 5 heavier per-seed patch scripts (loot mode,
        item suppression, story gates, door randomization, additional
        enemies) -- see
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
        if not force and gate_key is not None and _load_patched_seed(key) == gate_key \
                and _patched_marker_is_current(key, verify):
            game_events_logger.info(f"[{key}] already applied for this option set -- skipping re-run.")
            return
        ok, msg = apply_fn()
        if ok:
            game_events_logger.info(f"[{key}] applied: {msg}")
            _save_patched_seed(key, gate_key)
        else:
            self._patch_failures = getattr(self, "_patch_failures", 0) + 1
            game_events_logger.warning(f"[{key}] APPLY FAILED: {msg}")

    def _apply_module_rim_patches_in_order(self, gate_key: str | None, force: bool = False) -> None:
        """Runs the patching (see _apply_module_rim_patches_in_order_body) with the stale-game warning held back until it is finished."""
        with self._patching():
            self._apply_module_rim_patches_in_order_body(gate_key, force)

    def _apply_module_rim_patches_in_order_body(self, gate_key: str | None, force: bool = False) -> None:
        """Runs the module-RIM-editing patch scripts (item_suppression,
        loot_disturb, story_gates, door_randomizer, additional_enemies) and
        then the always-on patches SEQUENTIALLY in one executor task, rather
        than as independent run_in_executor
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
        above. Same reasoning applies to a 5th writer.

        Galactic Shop, the New Companion assets and the area poll hooks used to be dispatched as
        their own unordered tasks at Connect. They write module files (Galactic Shop retargets
        ebo_m12aa's module, the poll hook edits korr_m38aa's) or read module resources while the four
        patches above are mid-write -- a live Connect failed with "Failed to determine the format of
        the GFF file" reading a resource another patch was rewriting. They now run here, after the
        four heavy patches have finished, so (a) nothing reads a half-written module and (b) a module
        edit that the loot patch rebuilt from its backup copy is applied again afterwards. The boss
        datapad patch stays after them so its items are the last thing written."""
        # First, not last: it is a one-file write that takes no time, and a new game started while the slower
        # patches below are still running must already be given this seed's Player ID, not the previous seed's.
        logger.info("[patching] Patching the game files for this seed. This can take a minute or two; start the game after the "
                    "'finished' message below (if it is already running, fully quit and relaunch it afterwards).")
        self._patch_failures = 0
        if not os.path.isfile(os.path.join(GAME_DIR, "swkotor.exe")):
            logger.error(
                f"[patching] Cannot find your KOTOR game folder, so nothing was patched. Looked in: {GAME_DIR} "
                "(swkotor.exe is not there). To fix it: (1) close this client; (2) run Install.bat again from "
                "the PlayerBundle folder and, when it asks, enter the folder that contains swkotor.exe (in Steam: "
                "right-click the game, Manage, Browse local files); (3) open the KOTOR Client from the Launcher "
                "and connect again.")
            return
        # Door redirects and additional enemies from an earlier seed are not taken out by the patches themselves.
        previous = [_load_patched_seed(k) for k in ("door_randomizer", "additional_enemies")]
        if gate_key is not None and any(p is not None and p != gate_key for p in previous):
            logger.warning("[patching] This install was last patched for a different seed or option set. Door changes and "
                           "extra enemies from that seed are not removed automatically: if doors or enemies look wrong, run "
                           "/ap_restore_all, then reconnect (or run /ap_patch_all) before playing.")
        self._apply_player_id_and_log()
        self._apply_game_assets_and_log()
        self._apply_loot_disturb_and_log(gate_key, force)
        self._apply_item_suppression_and_log(gate_key, force)
        self._apply_story_gates_and_log(gate_key, force)
        self._apply_door_randomizer_and_log(gate_key, force)
        self._apply_additional_enemies_and_log(gate_key, force)
        self._apply_bazaar_tokens_and_log(gate_key, force)
        self._apply_galactic_shop_and_log()
        self._apply_new_companion_assets_and_log()
        self._apply_party_console_and_log()
        self._apply_droid_assets_and_log()
        self._apply_area_poll_hooks_and_log()
        self._apply_boss_datapads_and_log()
        self._reset_trampolines_and_log()
        self._clear_staged_and_log()
        self._ensure_vendor_and_log()
        if self._patch_failures:
            logger.warning(f"[patching] Finished with {self._patch_failures} patch failure(s), so the game is NOT fully "
                           "set up for this seed. The 'APPLY FAILED' lines (Heartbeat tab) say which step failed and why. "
                           "To fix it: (1) close KOTOR if it is running; (2) type /ap_patch_all here to try again; (3) if "
                           "a line mentions a missing file or folder, run Install.bat again; (4) if it keeps failing, post "
                           "those 'APPLY FAILED' lines in your report.")
        else:
            logger.info("[patching] Finished. The game files are ready: start the game now. If it was already running, "
                        "fully quit and relaunch it so it loads the patched files.")

    def _ensure_vendor_and_log(self) -> None:
        """Regenerates the Hawk's trampoline so the Archipelago Vendor NPC is (or is no longer)
        spawned according to this seed's archipelago_vendor option -- the spawn lives in the
        trampoline, which is otherwise only rebuilt when an arm happens to be queued for that
        area. Also removes a vendor left over from a previous seed that had it on."""
        ok, msg = ensure_vendor_spawn()
        if ok:
            game_events_logger.info(f"[vendor] {msg}")
        else:
            game_events_logger.warning(f"[vendor] FAILED -- {msg}")

    def _clear_staged_and_log(self) -> None:
        """See clear_staged_queue(): drops everything an earlier version left in the old staged-arm queue. Every delivery is a dispatcher
        job now and nothing is staged that way, so a leftover could only fire at an area entry on top of the dispatcher (one authority
        per arm). Runs in an executor (a blocking subprocess)."""
        ok, msg = clear_staged_queue(everything=True)
        if ok:
            game_events_logger.info(f"[staged queue] {msg}")
        else:
            game_events_logger.warning(f"[staged queue] clear FAILED -- {msg}")

    def _apply_item_suppression_and_log(self, gate_key: str | None, force: bool = False) -> None:
        """Runs apply_item_suppression() (a blocking subprocess call,
        hence run_in_executor from on_package rather than awaited
        directly), gated by _apply_seed_patch_if_new. Also callable
        directly (force=True) from the manual admin-command fallback.
        Only drives Progression System's checkpoint wrappers now, see
        apply_item_suppression()'s own docstring."""
        self._apply_seed_patch_if_new("item_suppression", gate_key, apply_item_suppression, force)

    def _apply_story_gates_and_log(self, gate_key: str | None, force: bool = False) -> None:
        """Same shape as _apply_item_suppression_and_log, for apply_story_gates()."""
        self._apply_seed_patch_if_new("story_gates", gate_key, apply_story_gates, force, verify=_story_gate_files_present)

    def _apply_loot_disturb_and_log(self, gate_key: str | None, force: bool = False) -> None:
        """Same shape as _apply_item_suppression_and_log, for
        apply_loot_disturb() -- the real destroy/bonus/replace loot
        handling now lives here, not in item_suppression."""
        self._apply_seed_patch_if_new("loot_disturb", gate_key, apply_loot_disturb, force)

    def _apply_door_randomizer_and_log(self, gate_key: str | None, force: bool = False) -> None:
        """Same shape as _apply_item_suppression_and_log, for
        apply_door_randomizer()."""
        self._apply_seed_patch_if_new("door_randomizer", gate_key, apply_door_randomizer, force)

    def _apply_boss_datapads_and_log(self) -> None:
        """apply_boss_datapads() on every Connect (not seed-gated), last of the module-rim writers."""
        ok, msg = apply_boss_datapads()
        if ok:
            game_events_logger.info(f"[boss datapads] {msg}")
        else:
            game_events_logger.warning(f"[boss datapads] PATCH FAILED -- {msg}")

    def _apply_player_id_and_log(self) -> None:
        """apply_player_id() on every Connect: writes this seed's Player ID item template. Needs the seed name and
        slot, so it does nothing before they are known."""
        slot = getattr(self, "username", None)
        if not self.seed_name or not slot:
            return
        ok, msg = apply_player_id(save_id_for(self.seed_name, slot), slot)
        if ok:
            game_events_logger.info(f"[player id] {msg}")
        else:
            game_events_logger.warning(f"[player id] PATCH FAILED -- {msg}")

    def _apply_additional_enemies_and_log(self, gate_key: str | None, force: bool = False) -> None:
        """Same shape again, for apply_additional_enemies()."""
        self._apply_seed_patch_if_new("additional_enemies", gate_key, apply_additional_enemies, force)

    def _apply_bazaar_tokens_and_log(self, gate_key: str | None, force: bool = False) -> None:
        """Same shape again, for apply_bazaar_tokens(); after loot_disturb in the ordered runner."""
        self._apply_seed_patch_if_new("bazaar_tokens", gate_key, apply_bazaar_tokens, force)

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

    def _apply_game_assets_and_log(self) -> None:
        """apply_game_assets() on every Connect, first of the game-file patches: they and the generated wrappers use the files it makes."""
        ok, msg = apply_game_assets()
        if ok:
            game_events_logger.info(f"[game assets] {msg}")
        else:
            self._patch_failures += 1
            game_events_logger.warning(f"[game assets] FAILED -- {msg}\n"
                                       "  Some files made from your own copy of the game could not be built. Check that the KOTOR folder is "
                                       "correct and complete (Steam: Verify integrity of game files), close the game, and connect again.")

    def _apply_party_console_and_log(self) -> None:
        """apply_party_console() on every Connect (not seed-gated: it is one row, added once)."""
        ok, msg = apply_party_console()
        if ok:
            game_events_logger.info(f"[party console] {msg}")
        else:
            game_events_logger.warning(f"[party console] PATCH FAILED -- {msg}")

    def _apply_droid_assets_and_log(self) -> None:
        """apply_droid_assets() on every Connect (not seed-gated -- it must take the droid files back out the moment a
        later seed has no droid option). Runs in an executor like the other patch scripts."""
        ok, msg = apply_droid_assets()
        if ok:
            game_events_logger.info(f"[droid assets] {msg}")
        else:
            game_events_logger.warning(f"[droid assets] PATCH FAILED -- {msg}\n"
                                       f"  (run /ap_apply_droid_assets to retry once fixed)")

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

    def _apply_area_poll_hooks_and_log(self) -> None:
        """apply_area_poll_hooks() on every Connect -- universal, not
        seed-gated. Runs in an executor like the other patch scripts."""
        ok, msg = apply_area_poll_hooks()
        if ok:
            game_events_logger.info(f"[area poll hooks] {msg}")
        else:
            game_events_logger.warning(f"[area poll hooks] PATCH FAILED -- {msg}\n"
                                       f"  (run /ap_apply_area_poll_hooks to retry once fixed)")

    def _apply_shop_item_costs_and_log(self) -> None:
        """apply_shop_item_costs() on every Connect -- universal, not
        seed-gated (see that function's own docstring for why). Runs in
        an executor like the other patch scripts."""
        ok, msg = apply_shop_item_costs()
        if ok:
            game_events_logger.info(f"[shop item costs] {msg}")
        else:
            game_events_logger.warning(f"[shop item costs] PATCH FAILED -- {msg}\n"
                                       f"  (run /ap_apply_shop_item_costs to retry once fixed)")

    def _apply_ap_tracker_quest_and_log(self) -> None:
        """apply_ap_tracker_quest() on every Connect -- universal, not
        seed-gated (see that function's own docstring for why: it must
        run against THIS install's dialog.tlk, not a pre-baked copy).
        Runs in an executor like the other patch scripts."""
        ok, msg = apply_ap_tracker_quest()
        if ok:
            game_events_logger.info(f"[ap tracker quest] {msg}")
        else:
            game_events_logger.warning(f"[ap tracker quest] PATCH FAILED -- {msg}\n"
                                       f"  (run /ap_apply_tracker_quest to retry once fixed)")

    def _queue_heavy(self, arm_name: str, label: str, *, is_correction: bool = False) -> None:
        """The ONE place any heavy send not already going through
        _deliver_item's real-item path enters _heavy_queue -- used by the
        automatic no_jedi/randomize_all companion_class follow-up below,
        /ap_apply's admin bypass, and (via _guarded_queue_heavy) the
        reconciler's own self-heal corrections. A companion_class send
        that skips this queue can land in the same TRAMPOLINE_BATCH_FIRED
        batch as unrelated grants and crash the game -- the exact same
        crash class HEAVY_ARMS/_heavy_queue exists to prevent for
        class_guardian/companion_carth/etc.; companion_class: needs its
        own routing here since it's a colon-parameterized string, not a
        static HEAVY_ARMS entry. Rather than have every call site
        remember to check HEAVY_ARMS/route correctly (and risk a future
        call site forgetting to), every non-real-item heavy send funnels
        through here. item_name/character are cosmetic (log/delivery-log
        labels only) for an admin-or-automatic send with no real AP item
        behind it; index is a unique negative counter so it can never
        collide with a real item's index or with another admin send of
        the same arm in _delivered_keys.

        is_correction=True (the reconciler's only mode) marks this as a
        RE-AFFIRMATION of state already accounted for, not a new arrival
        -- passed through to _do_deliver via the queue tuple, which uses
        it to skip note_item_received()/_maybe_queue_companion_class().
        Real incident this prevents: the original Canderous crash was
        caused by a reconciler-triggered companion resend re-triggering
        _maybe_queue_companion_class's automatic follow-up, redundantly
        re-queuing an already-applied companion_class grant. Admin/auto
        callers below deliberately keep the default False -- both
        legitimately want the full real-arrival treatment (admin is
        explicitly testing the real end-to-end path; the auto follow-up
        IS reacting to a genuinely new recruit).

        Also gated on the new-character safeguard -- an admin/auto/
        reconciler heavy send is just as capable of mutating the wrong
        character's state as a real item delivery is, so it gets the same
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
            (label, arm_name, self._admin_heavy_counter, character, is_correction)))

    def _is_arm_awaiting_confirmation(self, arm_name: str) -> bool:
        """True while the normal delivery pipeline (_do_deliver, whether
        reached via _heavy_queue or sent immediately) has already staged
        this exact arm_name and is still waiting on its AP|APPLIED|
        confirmation. Passed into ReconciliationTracker as
        is_awaiting_confirmation so its own missing-companion deficit
        check (see _reconcile()'s companion branch) can defer to that
        in-flight send instead of firing a second, unsynchronized
        self._send_apply for the same companion.

        Real incident this fixes: companion_canderous, 2026-09-25 --
        note_item_received() adds a companion to expected_companions the
        moment the normal send is staged, well before the game confirms
        it (that only happens once the recruit arm's trampoline actually
        fires, which can take up to one area transition). The reconciler
        runs on every extender event, so if one lands in that gap it sees
        "expected but not yet seen" and treats it as a genuine deficit --
        during a calm session this window is usually too narrow for a
        poll to land inside it, but a burst of events (e.g. the module
        load-in flood right after a fresh launch) gives it many more
        chances to. Two independent, uncoordinated sends of the same
        one-shot companion-recruit script 3 seconds apart, during the
        single most overloaded moment of the session, is the likely
        reason neither one's KSE_Diag confirmation ever arrived.

        Bounded by the same HEAVY_SEND_CONFIRM_TIMEOUT_SECONDS the heavy
        queue itself gives up after -- once the normal pipeline has
        stopped waiting on this send too, the reconciler is the right
        thing to retry it, not blocked from ever doing so."""
        if arm_name.startswith("companion_class:"):
            # A class send is a dispatcher job, and its delivery record is keyed by the companion alone ("companion_class:<npc>"), so the lookup
            # below never matches this arm name. The same send is still pending while the job waits in the heavy queue or in the dispatcher.
            parts = arm_name.split(":", 2)
            if len(parts) == 3 and (self._heavy_queue_holds(arm_name) or self.dispatcher.has_unfinished("companion_class", f"{parts[1]}:{parts[2]}")):
                return True
        record = self.extender.deliveries.get(arm_name)
        if record is None or record.staged_at is None or record.applied_at is not None:
            return False
        return (time.time() - record.staged_at) < HEAVY_SEND_CONFIRM_TIMEOUT_SECONDS

    def _heavy_queue_holds(self, arm_name: str) -> bool:
        """True while an entry for this arm is waiting in the heavy queue (entries are (label, arm_name, index, character, is_correction))."""
        return any(len(entry) > 1 and entry[1] == arm_name for entry in list(getattr(self._heavy_queue, "_queue", ())))

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
        if arm_name.startswith("give_item:"):
            # A parameterized give_item goes through the give-item sender: sent as APPLY:<name> the extender only
            # knows fixed arm names and answers "unknown item", so the self-heal for lost progression items never worked.
            parts = arm_name.split(":")
            resref, count = parts[1], int(parts[2]) if len(parts) > 2 else 1
            if self.dispatcher.has_unfinished("give_item", f"{resref}:{count}"):
                # The real delivery is still waiting for a calm moment, so the item is not in the game yet; sending it again would give two.
                return False
            ok = await self.extender.send_apply_item(resref, count)
        else:
            ok = await self.extender.send_apply(arm_name)
        if ok:
            self._reconciler_light_counter -= 1
            self._log_delivery(self.reconciler.current_character_name, self._reconciler_light_counter,
                                f"(reconciler self-heal) {arm_name}", arm_name, "reconciled")
        return ok

    async def _guarded_send_apply_value(self, action: str, value: int) -> bool:
        """Same as _guarded_send_apply, for the APPLYVALUE half (set_xp/
        set_credits) -- see that method's docstring."""
        if self._character_confirmed is False:
            game_events_logger.warning(f"[SAFEGUARD] Skipping reconciliation send ({action}={value}) -- "
                            f"unrecognized character, run /ap_confirm_character first if this is intentional.")
            return False
        ok = await self.extender.send_apply_value(action, value)
        if ok:
            self._reconciler_light_counter -= 1
            self._log_delivery(self.reconciler.current_character_name, self._reconciler_light_counter,
                                f"(reconciler self-heal) {action}={value}", action, "reconciled")
        return ok

    def _trapped_off_keys(self) -> typing.Set[str]:
        """Companions a Trap: Remove a Companion has permanently removed, for the CURRENT
        (seed_name, slot)."""
        seed_slot = (self.seed_name, getattr(self, "username", None))
        return {npc for (sn, sl, npc) in self._trapped_off_companions if (sn, sl) == seed_slot}

    def _grant_limited_companions(self, checked_count: int) -> None:
        """CompanionMode=ap_limited: gives each newly earned companion, through the same heavy queue the other
        self-grants use. Runs on every extender event, so the cheap case (nothing new earned) returns first. A companion
        already in the delivery log for this seed and slot, or removed by the Remove a Companion trap, is not sent again;
        the reconciler is told to expect every earned companion either way, so it heals one that goes missing."""
        if self.reconciler.current_character_name is None or not self.companion_unlock_order:
            return
        earned = min(len(self.companion_unlock_order), checked_count // COMPANION_LIMITER_CHECKS)
        if earned <= len(self._limited_requested):
            return
        seed_slot = (self.seed_name, getattr(self, "username", None))
        trapped = self._trapped_off_keys()
        for key in self.companion_unlock_order[:earned]:
            if key in self._limited_requested:
                continue
            self._limited_requested.add(key)
            arm_name = f"companion_{key}"
            self.reconciler.note_item_received(arm_name)
            if key in trapped or (*seed_slot, key) in self._recruited_companions:
                continue
            name = key
            logger.info(f"[companion limiter] {checked_count} checks -> granting {name}")
            self._queue_heavy(arm_name, f"(companion limiter) {arm_name}")

    async def _guarded_send_purge_companion(self, npc_key: str) -> bool:
        """Wired to ReconciliationTracker as send_purge: removes a companion
        who is on the roster without being entitled to it (a temporary
        scene staging left behind, a vanilla leak). The purge_companion trap
        (generate_trampoline_batch.py) drops them from the roster and the
        active party and destroys their standing object. Same character
        guard as the other reconciler sends."""
        if self._character_confirmed is False:
            game_events_logger.warning(f"[SAFEGUARD] Skipping reconciliation send "
                            f"(purge_companion:{npc_key}) -- unrecognized character, "
                            f"run /ap_confirm_character first if this is intentional.")
            return False
        ok = await self.extender.send_trap("purge_companion", npc_key)
        if ok:
            self._reconciler_light_counter -= 1
            self._log_delivery(self.reconciler.current_character_name, self._reconciler_light_counter,
                                f"(reconciler) purge_companion {npc_key}", f"purge_companion:{npc_key}", "reconciled")
        return ok

    async def _guarded_send_unparty_companion(self, npc_key: str) -> bool:
        """Star Forge pass (ReconciliationTracker._starforge_actions): takes a companion out
        of the active party and destroys their standing objects, keeping the roster entry
        (the unparty_companion trap, generate_trampoline_batch.py)."""
        return await self._send_roster_trap("unparty_companion", npc_key)

    async def _guarded_send_roster_remove_companion(self, npc_key: str) -> bool:
        """Star Forge pass: roster-only removal (the existing remove_companion trap:
        RemoveAvailableNPC), for a non-entitled Bastila on the dark path after the game's
        own script has taken her out of the party; her object keeps standing."""
        return await self._send_roster_trap("remove_companion", npc_key)

    async def _guarded_send_select_companion(self, npc_key: str) -> bool:
        """Roster fix (ReconciliationTracker._unselectable_entitled): an entitled companion who is
        listed but cannot be picked on the party screen is made selectable (the select_companion
        trap, generate_trampoline_batch.py)."""
        return await self._send_roster_trap("select_companion", npc_key)

    async def _send_roster_trap(self, trap_type: str, npc_key: str) -> bool:
        if self._character_confirmed is False:
            game_events_logger.warning(f"[SAFEGUARD] Skipping reconciliation send "
                            f"({trap_type}:{npc_key}) -- unrecognized character, "
                            f"run /ap_confirm_character first if this is intentional.")
            return False
        ok = await self.extender.send_trap(trap_type, npc_key)
        if ok:
            self._reconciler_light_counter -= 1
            self._log_delivery(self.reconciler.current_character_name, self._reconciler_light_counter,
                                f"(reconciler) {trap_type} {npc_key}", f"{trap_type}:{npc_key}", "reconciled")
        return ok

    async def _guarded_send_delevel(self, new_level: int, new_xp: int, new_force: int) -> bool:
        """Same guard as _guarded_send_apply/_guarded_send_apply_value, for
        the delevel reconciler fix -- see ExtenderBridge.send_delevel's
        own docstring for what this actually does."""
        if self._character_confirmed is False:
            game_events_logger.warning(f"[SAFEGUARD] Skipping reconciliation send "
                            f"(delevel level={new_level} xp={new_xp} force={new_force}) -- "
                            f"unrecognized character, run /ap_confirm_character first if this is intentional.")
            return False
        ok = await self.extender.send_delevel(new_level, new_xp, new_force)
        if ok:
            self._reconciler_light_counter -= 1
            self._log_delivery(self.reconciler.current_character_name, self._reconciler_light_counter,
                                f"(reconciler self-heal) delevel level={new_level} xp={new_xp} force={new_force}",
                                "delevel", "reconciled")
        return ok

    def _guarded_queue_heavy(self, arm_name: str) -> None:
        """Wired to ReconciliationTracker as send_heavy -- the ONLY
        dispatch path for a correction naming a HEAVY_ARMS member or a
        companion_class: send (see entitlement.py's is_heavy_arm). Just
        forwards to _queue_heavy, the same single serializing entry point
        every other non-real-item heavy send (admin /ap_apply, the
        automatic companion_class follow-up) already uses -- see that
        method's own docstring. Before this was wired up, the reconciler
        called self.extender.send_apply directly for companion recruit/
        class corrections, completely bypassing _heavy_queue's
        serialization -- the exact crash class HEAVY_ARMS exists to
        prevent (two heavy sends landing in the same trampoline batch).

        is_correction=True is the whole reason this wrapper exists rather
        than every ReconciliationTracker construction site passing
        _queue_heavy directly -- see _queue_heavy's own docstring and
        _do_deliver's tail for what this actually prevents (a reconciler
        resend re-triggering _maybe_queue_companion_class's automatic
        follow-up, recreating the original Canderous incident's redundant-
        reroll shape even after the batching-crash risk was closed). No
        separate character-safety check needed here -- _queue_heavy
        already has its own."""
        self._queue_heavy(arm_name, f"(reconciler self-heal) {arm_name}", is_correction=True)

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
        game_events_logger.warning(f"[SAFEGUARD] The game is on character {character!r} (level {self.current_level}), "
                        f"which this client has not seen on this seed, and it is not a fresh level-1 start.")
        game_events_logger.warning("To protect your progress, ALL item deliveries are PAUSED until you choose below.")
        game_events_logger.warning(f"Characters already used on this seed: {known}")
        game_events_logger.warning("If you loaded the wrong save: load the correct save in the game, then reconnect "
                        "this client. Nothing is lost.")
        game_events_logger.warning("If this really is your character for this seed (for example you started over): "
                        "type /ap_confirm_character here and deliveries resume.")
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

    async def _do_deliver(self, item_name: str, arm_name: str, index: int, character: typing.Optional[str],
                           *, is_correction: bool = False) -> None:
        """The actual send -- shared by the immediate (light-arm) path in
        _deliver_item and the serialized consumer in _process_heavy_queue.

        is_correction=True (only ever set by the reconciler, via
        _guarded_queue_heavy -> _queue_heavy's queue tuple) marks this as
        a RE-AFFIRMATION of state already accounted for, not a new
        arrival -- see the tail below and _queue_heavy's own docstring for
        the real incident this distinction prevents (a reconciler resend
        re-triggering _maybe_queue_companion_class's automatic follow-up
        and redundantly re-queuing an already-applied grant)."""
        # What the player is told once the game applies it: the item's name. A reconciler re-affirmation, a self-heal and an admin test
        # (their labels start with "(") say nothing.
        receipt_message = "" if (is_correction or item_name.startswith("(")) else f"You received: {item_name}"
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
            sent = await self.extender.send_apply_item(resref, count, message=receipt_message)
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
                if not is_correction:
                    # Only the 8 tracked progression resrefs actually get
                    # recorded (see note_item_received's own give_item:
                    # branch) -- the general gear pool is intentionally a
                    # no-op here, same scope as PROGRESSION_ITEM_RESREFS.
                    self.reconciler.note_item_received(arm_name)
            else:
                self._on_unstaged_send(item_name, arm_name, index, character, f"give_item:{resref}", is_correction)
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
            if not is_correction:
                # The class this item names is the companion's expected class from now on, whether or not this send lands: the game refuses it
                # while he is not in the active party, and the reconciler applies it once he is (see companion_class_items).
                self.reconciler.note_item_received(arm_name)
            sent = await self.extender.send_companion_class(npc_key, class_name, message=receipt_message)
            if sent:
                # See give_item's own comment on wait_staged above -- same
                # real-vs-local-only confirmation gap closed the same way.
                sent = await self.extender.wait_staged(f"companion_class:{npc_key}")
            if sent:
                logger.info(f"[queued for game] {item_name} -> companion_class:{npc_key}:{class_name}")
                self._log_delivery(character, index, item_name, arm_name, "sent")
            else:
                self._on_unstaged_send(item_name, arm_name, index, character, f"companion_class:{npc_key}", is_correction)
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
        sent = await self.extender.send_apply(arm_name, message=receipt_message)
        if sent:
            # See give_item's own comment on wait_staged above -- same
            # real-vs-local-only confirmation gap closed the same way.
            sent = await self.extender.wait_staged(arm_name)
        if sent:
            # is_correction=True skips BOTH of these -- they represent
            # "this is newly-decided AP progress," which a reconciler
            # resend of already-accounted-for state is not.
            # note_item_received re-recording an unchanged value is
            # harmless, but _maybe_queue_companion_class is NOT: it
            # unconditionally re-decides "does this companion need a class
            # assignment" and would redundantly re-queue one regardless of
            # whether they already have it -- the exact shape that crashed
            # Canderous originally (a companion-recruit resend re-
            # triggering this follow-up on top of an already-applied
            # grant). See _queue_heavy's own docstring.
            if not is_correction:
                self.reconciler.note_item_received(arm_name)
                self._maybe_queue_companion_class(arm_name)
            logger.info(f"[queued for game] {item_name} -> {arm_name}")
            self._log_delivery(character, index, item_name, arm_name, "reconciled" if is_correction else "sent")
        else:
            self._on_unstaged_send(item_name, arm_name, index, character, arm_name, is_correction)

    # Seconds to wait before each automatic retry of an item the extender rejected; after the last one it waits for the
    # next extender reconnect (a relaunched game or an updated extender is the usual fix).
    _REJECTED_RETRY_DELAYS = (60, 180, 300, 600, 900)

    def _on_unstaged_send(self, item_name: str, arm_name: str, index: int, character: str, key: str,
                          is_correction: bool) -> None:
        """A send never reached STAGED. Two different causes, told apart by what the extender said: it answered ERROR
        (rejected: it does not know the command) or it said nothing because it is not connected (offline). Neither is
        logged as sent; both are retried later."""
        detail = self.extender.rejection(key)
        if detail is None:
            game_events_logger.warning(f"[NOT SENT -- extender offline] {item_name} -> {arm_name}. "
                            f"The game is not connected. It is saved and will be sent automatically once "
                            f"KOTOR is running and connected.")
            self._log_delivery(character, index, item_name, arm_name, "failed_extender_offline")
            return
        if key not in self._rejection_announced:
            self._rejection_announced.add(key)
            game_events_logger.warning(
                f"[NOT DELIVERED -- the game rejected it] {item_name} ({arm_name}). The extender in your KOTOR folder "
                f"answered: {detail}. It did not recognize this command, which usually means the extender (the "
                f"binkw32.dll the installer put in your KOTOR folder) is older than this client. To fix it: close "
                f"KOTOR, run Install.bat again from this client folder, then start the game. The item stays pending "
                f"and is retried automatically; if it keeps happening, post this line.")
        else:
            game_events_logger.info(f"[still rejected] {item_name} ({arm_name}); will retry.")
        self._log_delivery(character, index, item_name, arm_name, "failed_extender_rejected")
        if arm_name.startswith("give_item:") and not is_correction:
            # Recorded as received so the progression-item self-heal covers it too, whatever happens to this send.
            self.reconciler.note_item_received(arm_name)
        if not is_correction:
            self._schedule_rejected_retry(item_name, arm_name, index)

    def _schedule_rejected_retry(self, item_name: str, arm_name: str, index: int) -> None:
        attempt = self._rejected_attempts.get(index, 0)
        if attempt >= len(self._REJECTED_RETRY_DELAYS):
            if index not in self._rejected_gave_up:
                self._rejected_gave_up.add(index)
                game_events_logger.warning(
                    f"[retry paused] {item_name} ({arm_name}) was rejected {attempt + 1} times. It is retried again "
                    f"the next time the game connects; fix the cause above first.")
            return
        self._rejected_attempts[index] = attempt + 1
        task = asyncio.create_task(
            self._retry_rejected_after(self._REJECTED_RETRY_DELAYS[attempt], item_name, arm_name, index))
        self._background_tasks.add(task)
        task.add_done_callback(self._track_background_task)

    async def _retry_rejected_after(self, delay: float, item_name: str, arm_name: str, index: int) -> None:
        await asyncio.sleep(delay)
        if self.server is None:
            return
        await self._deliver_item(item_name, arm_name, index)

    async def _process_heavy_queue(self) -> None:
        """Consumes HEAVY_ARMS (and companion_class:) deliveries one at a
        time, waiting for each to confirm-applied (AP|APPLIED|<arm>|...)
        before sending the next -- see HEAVY_ARMS and the queuing comment
        in _deliver_item for why."""
        while True:
            item_name, arm_name, index, character, is_correction = await self._heavy_queue.get()
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

            await self._do_deliver(item_name, arm_name, index, character, is_correction=is_correction)

            # Wait for confirmation this specific send actually landed --
            # i.e. applied_at advanced past whatever it was before this
            # send (guards against reading a stale confirmation from an
            # EARLIER delivery of the same arm_name). Bounded so a lost
            # confirmation can't stall every later heavy item forever.
            for _ in range(HEAVY_SEND_CONFIRM_TIMEOUT_SECONDS):  # 1s/poll
                record = self.extender.deliveries.get(poll_key)
                if record is not None and record.applied_at is not None and record.applied_at != already_applied_at:
                    break
                if record is not None and record.rejected_at is not None:
                    break  # the extender refused it; nothing will confirm
                await asyncio.sleep(1.0)
            else:
                game_events_logger.warning(f"[heavy queue] no confirmation for {arm_name} after 10 minutes, "
                                f"proceeding to the next item anyway")
            self._heavy_queue.task_done()

    def run_gui(self):
        from kvui import GameManager
        from kivy.clock import Clock
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.scrollview import ScrollView
        from kivymd.uix.label import MDLabel

        def status_label(text):
            # Grows with its text, so a long queue wraps onto more lines instead of running into the label below it.
            return MDLabel(text=text, size_hint_y=None, adaptive_height=True)

        class KotorStatusView(BoxLayout):
            def __init__(self, ctx: "KotorContext", **kwargs):
                super().__init__(orientation="vertical", **kwargs)
                self.ctx = ctx
                # Every label lives in one scrolling column: with many queued, staged or settled items the page scrolls
                # instead of the lists overlapping each other.
                column = BoxLayout(orientation="vertical", padding=10, spacing=6, size_hint_y=None)
                column.bind(minimum_height=column.setter("height"))
                scroll = ScrollView(do_scroll_x=False)
                scroll.add_widget(column)
                self.connection_label = status_label("Extender: not connected")
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
                self.character_label = status_label("")
                self.checks_label = status_label("Checks: 0 / 0")
                self.pending_label = status_label("Deliveries waiting: none")
                self.failed_label = status_label("")
                self.recent_label = status_label("Recently delivered: none")
                for label in (self.connection_label, self.character_label, self.checks_label,
                              self.pending_label, self.failed_label, self.recent_label):
                    column.add_widget(label)
                self.add_widget(scroll)

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
                # This slot's own locations (the server's list), not the game's whole location table:
                # options such as new_companion remove some locations from a slot, which made a
                # finished run read 259 / 261.
                slot_locations = self.ctx.server_locations or set(lid for lid in self.ctx.location_names[self.ctx.game] if lid >= 0)
                total = len(slot_locations)
                self.checks_label.text = f"Checks: {checked} / {total}"

                # Every delivery is a dispatcher job: what is waiting and why, what failed, what was delivered lately.
                text = self.ctx.dispatcher.window_text()
                waiting = text["waiting"]
                if not ext.is_connected and waiting != "Deliveries waiting: none":
                    waiting += "\n  (the game is not connected: deliveries wait until it is)"
                self.pending_label.text = waiting
                self.failed_label.text = text["failed"]
                self.recent_label.text = text["recent"]

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
    parser.add_argument("--game-dir", default=None,
                         help="Path to the KOTOR install (the folder with swkotor.exe). Normally not needed: it is "
                              "read from the installer's record, or defaults to the standard Steam location. Read "
                              "via an early sys.argv scan (see GAME_DIR above), listed here so argparse recognizes it.")
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
