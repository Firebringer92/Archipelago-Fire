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
crossings + 3 history-based bonus checks), 200 locations total. !ap_check
is kept as a manual override/diagnostic, not the primary path anymore.

Admin commands (!ap_apply, !ap_status) call the exact same extender
protocol the AP-item path uses, so they're safe to use for direct testing
without touching the AP server at all -- a "safety valve" separate from
the real item-received flow.
"""
from __future__ import annotations

import asyncio
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

from kotor_extender_bridge import ExtenderBridge
from kotor_reconciliation import ReconciliationTracker, CLASS_ARM_TO_KEY
from kotor_location_tracker import LocationTracker
from worlds.kotor.Items import item_table
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

# AdditionalFeats (2026-09-07): the combined cross-class pool a granted
# item picks 3 from -- weapon profs (Blaster Rifle/Heavy Weapons/
# Lightsaber, excluding Pistol/Melee since every class already has those)
# + armor profs (Light/Medium/Heavy) + Implant Level 1 + each class's
# signature ability feat. Confirmed via feat.2da (2026-09-06), see
# GameMechanics.md for the full derivation and research/feats/
# class_feats.json for the raw per-class data. Deliberately NOT filtered
# by class here -- the client doesn't need to know a character's exact
# final class to pick from this (see KotorContext._is_pc_class_finalized's
# docstring: the class-delta fix already guarantees a finalized
# character's baseline is correct, and the generated NWScript wraps every
# grant in a live GetHasFeat guard as the actual "don't double-grant"
# safety net).
ADDITIONAL_FEATS_POOL = [
    40, 42, 43,        # Weapon Prof: Blaster Rifle / Heavy Weapons / Lightsaber
    4, 5, 6,           # Armor Prof: Heavy / Light / Medium
    14,                # Implant Level 1
    28, 29,            # Power Attack / Power Blast (Soldier signature)
    11, 30,            # Flurry / Rapid Shot (Scout signature)
    8, 31, 60, 104,    # Critical Strike / Sniper Shot / Sneak Attack I / Scoundrel's Luck
    101, 88, 98,       # Force Jump / Force Focus / Force Immunity: Fear (Jedi signature)
]

# Traps (2026-09-08, see Options.py's EnableTraps): classes.2da's own
# hitdie column, row order (confirmed via pykotor, not memory) --
# Soldier/Scout/Scoundrel/JediGuardian/JediConsular/JediSentinel/
# CombatDroid/ExpertDroid/Minion, matching real CLASS_TYPE_* constant
# values 0-8. Only needed for the Cut Max Health in Half trap's own
# Max-HP formula below -- KOTOR has no direct Max HP field at all
# (confirmed via direct memory diffing, see FutureDesign.md), so this
# project computes it client-side purely from already-tracked state
# (current_classes/current_abilities) rather than adding yet another
# poll report.
CLASS_HITDIE = {0: 10, 1: 8, 2: 6, 3: 10, 4: 6, 5: 8, 6: 12, 7: 8, 8: 10}


def _compute_max_hp(current_classes: dict, con: int) -> int:
    """MaxHP = sum(class_level * hitdie) + floor((CON-10)/2) * total_level
    -- the same formula confirmed live 2026-09-06 (a CON change
    correctly, exactly recomputes Max HP; see FutureDesign.md). Only the
    PC's own base class + Jedi class (if any) matter here (traps are
    PC-only)."""
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
    unreachable through Constitution alone (see Options.py's EnableTraps
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
_LEVEL_RE = re.compile(r"AP\|LEVELREPORT\|(\d+)")
MAX_LEVEL = 20  # KOTOR's real level cap, per exptable.2da

# Loaded once at import time -- same source of truth Items.py reads to build
# the give_item:<resref> item_table entries. Used here only to decide HOW
# MANY of a gear item to grant: equipment (has a real equipment_slot) always
# grants 1, consumables grant consumable_stack_count (from slot_data),
# capped by the item's own real stack_limit either way.
GEAR_ITEMS_PATH = os.path.join(os.path.dirname(__file__), "worlds", "kotor", "gear_items.json")

# Separate from the shared `logger` (CommonClient's "Client" logger, which
# backs the GUI's main "Archipelago" tab) -- 2026-08-29, at the user's
# explicit request to keep that tab down to just 4 things (extender
# connecting, AP server connecting, checks found, items sent). Everything
# else this client logs (the raw heartbeat/event firehose, delivery
# bookkeeping noise, startup warnings, banner text) goes here instead, on
# its own "Heartbeat" GUI tab (see KotorManager.logging_pairs below) --
# moved, not deleted, since it's still useful to have somewhere.
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
# -- confirmed live tonight: batching several of these together (even all
# first-time applications, no repeats involved) crashed the game twice.
# These get serialized client-side, one in flight at a time, instead of
# firing immediately like everything else -- see _process_heavy_queue().
# Deliberately NOT everything: skills/abilities/force_death don't touch
# multiclassing, the level-up GUI, or party membership, and have shown no
# crash risk even in much larger batches. see Items.py.)
HEAVY_ARMS = {
    "class_guardian", "class_consular", "class_sentinel",
    "companion_bastila", "companion_canderous", "companion_carth",
    "companion_hk47", "companion_jolee", "companion_juhani",
    "companion_mission", "companion_t3m4", "companion_zaalbar",
    # StartingClass=random_class's base-class roll (2026-09-02) -- a
    # KSE_SetCreatureField write on the PC, same heavy classification as
    # companion_class's write, same reasoning (see _queue_heavy).
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
    # dump_statblock/dump_statblock_carth/dump_statblock_juhani/
    # carth_addmulticlass_hybrid_test/juhani_addmulticlass_scoundrel_test/
    # juhani_grant_critical_strike_test/test_credits_chain/grant_implant_3/
    # test_set_max_hp/test_con_boost_effect/test_con_decrease_effect were
    # all TEMPORARY research arms, RETIRED 2026-09-06 once their research
    # concluded and shipped as real offsets/natives -- removed here (this
    # is just a /ap_apply validation list, no positional-ID constraint,
    # unlike AP_ARM_NAMES in ap_extender.c / APPLIES in
    # generate_trampoline_batch.py, where they're renamed-not-removed to
    # preserve arm-ID stability). Archived at extender/research_archive/.
    # test_hp_fp_natives/test_alignment_shift RETIRED 2026-09-06, same
    # night -- both LIVE-CONFIRMED working (kse.log results archived at
    # extender/research_archive/test_hp_fp_alignment_arms_2026-09-06.py.txt).
    # test_add_100_hp RETIRED 2026-09-06 -- confirmed write succeeds but
    # current HP appears clamped to Max HP once exceeded (expected, not a
    # bug). Archived at extender/research_archive/.
    # test_lower_hp RETIRED 2026-09-06 -- user-confirmed live: persisted
    # correctly on the character sheet. All current-HP native behavior
    # relevant to real features is now confirmed. Archived at
    # extender/research_archive/.
    "test_grant_active_feat",  # TEMPORARY (2026-09-06): grants Critical
                            # Strike (an ACTIVE feat) to the PC to check
                            # whether it's genuinely hotbar-usable, not
                            # just present. Retire once confirmed.
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

# 2026-08-31: same default every other setup script in this repo hardcodes
# (patch_item_suppression.py, patch_door_randomizer.py, setup_game.py,
# generate_poll_shared.py) -- this project doesn't have a shared config
# file for it yet, so this stays consistent with that convention rather
# than inventing a new one just for this call site.
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
    rather than assuming a fixed folder depth -- found broken live
    2026-09-04, twice, when a hardcoded dirname(dirname(__file__)) guess
    (correct ONLY for the dev machine's own layout, KotorClient.py nested
    one level inside an Archipelago\\ subfolder of the project root) was
    asked of a tester's real, differently-shaped setup and silently missed.
    Not something a tester should have to reason about folder-nesting
    depth to work around -- checks both layouts this project's docs and
    real troubleshooting have produced:
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
PATCH_DOOR_RANDOMIZER = os.path.join(REPO_ROOT, "scripts", "patch_door_randomizer.py")
PATCH_ADDITIONAL_ENEMIES = os.path.join(REPO_ROOT, "scripts", "patch_additional_enemies.py")

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


def _save_patched_seed(key: str, seed_name: str | None) -> None:
    try:
        os.makedirs(os.path.dirname(PATCHED_SEEDS_MARKER_PATH), exist_ok=True)
        try:
            with open(PATCHED_SEEDS_MARKER_PATH, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
        data[key] = seed_name
        with open(PATCHED_SEEDS_MARKER_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as e:
        logger.warning(f"Could not update {PATCHED_SEEDS_MARKER_PATH}: {e}")

# Found broken live (2026-09-04): patch_item_suppression.py/patch_door_randomizer.py
# used to read loot_mode/door_mapping straight out of a locally generated
# AP_<seed>.zip's embedded slot_data -- which only exists on whichever
# machine ran Generate.py. A player joining someone ELSE's hosted
# multiworld never has that file at all, so those two scripts had no way
# to work for them, ever. Both values are already part of the real
# slot_data THIS client receives over the network on every Connect (see
# on_package below) -- the actual fix is writing them out locally right
# here, so both patch scripts can read this file instead of hunting for
# a seed zip that may not exist. Also fixes a second bug the zip-reading
# approach had: it grabbed the FIRST slot in the whole multiworld with a
# matching field, not specifically this player's own slot -- this file
# only ever reflects the current connection's own real slot_data.
SLOT_DATA_PATH = os.path.join(REPO_ROOT, "extender", "area_trampolines", "_slot_data.json")


def write_slot_data_for_patch_scripts(
        loot_mode: int, door_mapping: dict | None, area_randomizer: bool, starting_class: int,
        additional_enemies_mode: int = 0, seed_name: str | None = None,
        progression_system: bool = False) -> None:
    """Called on every successful Connect -- see SLOT_DATA_PATH above for
    why this exists. A plain JSON write (not restricted_loads/pickle --
    this project controls both ends, unlike the raw .archipelago format),
    so patch_item_suppression.py/patch_door_randomizer.py no longer need
    to import Utils from a real Archipelago checkout at all for this.

    Also covers area_randomizer/starting_class (2026-09-04) -- swept for
    every other place reading seed data out of a locally generated zip
    after fixing the two patch scripts above, and found the exact same
    latent bug in generate_poll_shared.py/generate_makejedi_suppressor.py's
    OWN standalone-invocation fallback (never hit through this client,
    which always passes --area-randomizer/--starting-class explicitly,
    but both scripts' own Usage docstrings advertise running them by hand
    with neither flag as a real supported mode -- worth fixing rather
    than leaving a known-fragile fallback in place for whoever eventually
    does that).

    2026-09-08 addition: additional_enemies_mode (for the new
    patch_additional_enemies.py) and seed_name -- the latter lets that
    script derive a reproducible RNG seed from the real AP seed (same
    player always gets the same additive placements from the same seed)
    instead of a fresh random draw every time the script is re-run.

    2026-09-08, found live during testing: progression_system was NEVER
    written here at all, despite patch_item_suppression.py's
    _connected_progression_system() reading exactly this key (defaulting
    to False when absent) to decide whether to always-suppress Sith Armor/
    Shield Codes and deploy the 4 checkpoint wrappers via
    apply_progression_checkpoint_wrappers(). With the key missing, that
    whole read silently resolved to "off" every time regardless of the
    real option -- meaning the ENTIRE Progression System (not just one
    item) was inert on every real Connect, mode='bonus' or otherwise. This
    is the fix -- same shape as every other field here."""
    try:
        os.makedirs(os.path.dirname(SLOT_DATA_PATH), exist_ok=True)
        with open(SLOT_DATA_PATH, "w", encoding="utf-8") as f:
            json.dump({
                "loot_mode": loot_mode, "door_mapping": door_mapping,
                "area_randomizer": area_randomizer, "starting_class": starting_class,
                "additional_enemies_mode": additional_enemies_mode, "seed_name": seed_name,
                "progression_system": progression_system,
            }, f)
    except Exception as e:
        logger.warning(f"Could not write {SLOT_DATA_PATH} for the patch scripts: {e}")


def regenerate_poll_shared(area_randomizer: bool) -> tuple[bool, str]:
    """Regenerates, compiles, and deploys ap_poll_shared.ncs for the ACTUAL
    connected seed's area_randomizer, straight to GAME_DIR's live Override
    -- a pure local file operation (write .nss, compile via nwnnsscomp.exe,
    copy the .ncs), no extender/DLL round-trip needed.

    Real bug this replaces (2026-08-31): package_dist.py's prebuilt
    dist/Override bundle treats ap_poll_shared as "always-on, fully
    deterministic" and ships whatever area_randomizer happened to be true
    on the PACKAGER's machine at packaging time -- silently wrong for any
    tester whose own seed differs. Calling this on every Connected (see
    KotorContext.on_package) makes the deployed script always match the
    seed actually being played, no manual step required. Returns
    (success, message) rather than raising -- called from a background
    task on Connected, where an unhandled exception would be swallowed
    silently by asyncio anyway; a clear log line either way is more useful
    than a stack trace nobody sees.

    No loot_mode parameter any more (2026-08-31) -- bonus mode's grant
    logic moved out of ap_poll_shared entirely, into
    patch_item_suppression.py's event-driven HandleAcquiredItem() (see
    that file's build_handler_body() docstring), so this script no longer
    needs to know loot_mode at all."""
    try:
        result = subprocess.run(
            [sys.executable, GENERATE_POLL_SHARED,
             f"--game-dir={GAME_DIR}",
             f"--area-randomizer={1 if area_randomizer else 0}"],
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


def apply_item_suppression() -> tuple[bool, str]:
    """Runs patch_item_suppression.py against GAME_DIR for the ACTUAL
    connected seed -- same pure-subprocess shape as regenerate_poll_shared
    above. No mode/flags passed: the script itself reads loot_mode and
    progression_system straight from SLOT_DATA_PATH (write_slot_data_for_
    patch_scripts already wrote it before this is ever called -- see
    on_package). Also applies the Progression System's checkpoint
    wrappers as part of its own main(), when progression_system is on --
    one call covers both. Real per-module RIM edits (up to ~117 modules),
    not a cheap single-file operation like poll_shared/makejedi -- see
    PATCHED_SEEDS_MARKER_PATH above for why callers should gate this on
    the seed actually having changed, not call it unconditionally on
    every Connect."""
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


class KotorClientCommandProcessor(ClientCommandProcessor):
    def _cmd_ap_check(self, *location_name_parts: str) -> bool:
        """Report a location check by name, e.g. !ap_check Endar Spire: Escape Pod Reached"""
        if not self.ctx.server:
            self.output("Not connected to a server yet. Use /connect first.")
            return False

        location_name = " ".join(location_name_parts).strip()
        lookup = self.ctx.location_names[self.ctx.game]
        name_to_id = {name: loc_id for loc_id, name in lookup.items() if loc_id >= 0}

        if location_name not in name_to_id:
            self.output(f"Unknown location {location_name!r}. Use !ap_locations to list them.")
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
        call the real item-received path makes. e.g. !ap_apply credits
        Gear items use give_item:<resref>[:<count>], e.g.
        !ap_apply give_item:g1_w_lghtsbr01:1 -- count defaults to 1.
        Companion class randomization uses companion_class:<name>:<class>,
        e.g. !ap_apply companion_class:carth:guardian -- see Options.py's
        CompanionClass and generate_trampoline_batch.py's
        build_companion_class_block for the valid name/class values.
        Additional Feats uses additional_feats:<key>, e.g.
        !ap_apply additional_feats:pc -- valid keys: pc, bastila,
        canderous, carth, jolee, juhani, mission, zaalbar. Traps use
        trap:<type>[:<params>], e.g. !ap_apply trap:reduce_skill."""
        if not arm_name:
            self.output(f"Usage: !ap_apply <name>. Known names: {', '.join(KNOWN_ARM_NAMES)}, "
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
                self.output("Usage: !ap_apply give_item:<resref>[:<count>]")
                return False
            count = int(parts[2]) if len(parts) > 2 else 1
            asyncio.create_task(self.ctx.extender.send_apply_item(resref, count))
            self.output(f"Admin: queued give_item {resref!r} x{count} directly (bypassing AP server).")
            return True
        if arm_name.startswith("companion_class:"):
            parts = arm_name.split(":")
            if len(parts) != 3 or not parts[1] or not parts[2]:
                self.output("Usage: !ap_apply companion_class:<name>:<class>")
                return False
            # Routed through the heavy queue (2026-09-02, was a direct send
            # before) -- confirmed live this exact admin call landed in the
            # same trampoline batch as unrelated grants and crashed the
            # game, the same crash class HEAVY_ARMS exists to prevent for
            # class_guardian/companion_carth/etc. See _queue_heavy.
            self.ctx._queue_heavy(arm_name, f"(admin) companion_class:{parts[1]}:{parts[2]}")
            self.output(f"Admin: queued companion_class {parts[1]}:{parts[2]} (serialized, bypassing AP server).")
            return True
        if arm_name.startswith("additional_feats:"):
            # 2026-09-08, found live during Traps/Additional Feats testing:
            # this admin bypass had no additional_feats: handling at all
            # (unlike trap:/companion_class: above) -- typing it just fell
            # through to the "Unknown arm name" rejection below every time,
            # no typo required. Routes through the exact same
            # _pending_additional_feats + _resolve_additional_feats path a
            # real item receipt uses -- still gated on recruited+class-
            # finalized, so it may not apply instantly if that character
            # isn't ready yet.
            _valid_feat_keys = ("pc", "bastila", "canderous", "carth", "jolee",
                                 "juhani", "mission", "zaalbar")
            parts = arm_name.split(":", 1)
            npc_key = parts[1] if len(parts) > 1 else ""
            if npc_key not in _valid_feat_keys:
                self.output(f"Usage: !ap_apply additional_feats:<key>, valid keys: {', '.join(_valid_feat_keys)}")
                return False
            character = self.ctx.reconciler.current_character_name or "(unknown, admin-triggered)"
            self.ctx._admin_trap_counter = getattr(self.ctx, "_admin_trap_counter", 0) - 1
            key = (character, self.ctx._admin_trap_counter)
            self.ctx._pending_additional_feats[key] = (f"(admin) {arm_name}", arm_name)
            self.output(f"Admin: queued additional_feats {npc_key!r} -- resolves once recruited+class-finalized (bypassing AP server).")
            return True
        if arm_name.startswith("trap:"):
            # 2026-09-08, found live during Traps testing: this admin
            # bypass had no trap: handling at all, so it fell through to
            # the `arm_name not in KNOWN_ARM_NAMES` rejection below every
            # time (trap:<type> is a dynamically-parameterized action, not
            # a static registered name, same category as give_item:/
            # companion_class: above -- just missing this case). Routes
            # through the exact same _pending_traps + _resolve_trap path
            # a real trap item receipt uses -- resolves on the next poll
            # cycle, not instantly, matching the real behavior being
            # tested rather than a shortcut around it.
            parts = arm_name.split(":", 2)
            if len(parts) < 2 or not parts[1]:
                self.output("Usage: !ap_apply trap:<type>[:<params>], e.g. !ap_apply trap:cut_max_hp")
                return False
            # 2026-09-08, relaxed after live friction: this used to hard-block
            # if current_character_name was still None, but that name is
            # ONLY used for the delivery-log bookkeeping key below -- the
            # actual trap math always reads live reconciler state fresh at
            # RESOLUTION time (next poll cycle), not whatever was known at
            # queue time. Blocking the admin command on it added real
            # friction (had to wait for a confirmed poll, with no visible
            # way to check that beyond watching kse.log directly) for no
            # correctness benefit -- falls back to a placeholder instead.
            character = self.ctx.reconciler.current_character_name or "(unknown, admin-triggered)"
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
            # Found live 2026-09-08 testing two traps back-to-back: neither
            # applied, because the second `!ap_apply trap:X` overwrote the
            # first's entry before either got a chance to resolve.
            self.ctx._admin_trap_counter = getattr(self.ctx, "_admin_trap_counter", 0) - 1
            key = (character, self.ctx._admin_trap_counter)
            self.ctx._pending_traps[key] = (f"(admin) {arm_name}", arm_name)
            self.output(f"Admin: queued trap {arm_name!r} -- resolves on the next poll cycle (bypassing AP server).")
            return True
        if arm_name in ("xp", "credits"):
            # Mirrors _do_deliver's real-item handling for these two exactly
            # (2026-09-03 fix -- see FutureDesign.md): a real "xp"/"credits"
            # AP item is bookkeeping-only, note_item_received() bumps the
            # expected total and the reconciler's own bidirectional clamp
            # (set_xp/set_credits) does the actual grant on its next
            # transition/poll. The raw fixed-increment arm (GiveGoldToCreature
            # / GiveXPToCreature) is NEVER reached for a real item any more.
            # This admin command used to skip straight to that raw arm
            # instead -- confirmed live to desync the reconciler entirely
            # (the clamp doesn't know about a grant it didn't expect, and
            # corrects the "extra" straight back out). Routing through the
            # same note_item_received() call makes this a genuinely
            # representative test of the real path, not a different one.
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
            # AP-item path, never when triggered via !ap_apply.
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
                    f"area_randomizer={self.ctx.area_randomizer} ...")
        ok, msg = regenerate_poll_shared(self.ctx.area_randomizer)
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

    def _cmd_ap_apply_item_suppression(self) -> bool:
        """Manual fallback: force-reapply patch_item_suppression.py against
        the real Steam KOTOR install for this session's connected seed,
        regardless of the once-per-seed marker (normally done automatically
        once on Connect -- see on_package). Use this if the automatic run
        failed (check the log for an "[item_suppression] APPLY FAILED"
        line) or after manually editing/restoring the game install."""
        self.output("Admin: re-applying item suppression (full RIM sweep, may take a while) ...")
        ok, msg = apply_item_suppression()
        self.output(("OK: " if ok else "FAILED: ") + msg)
        return ok

    def _cmd_ap_apply_door_randomizer(self) -> bool:
        """Same as !ap_apply_item_suppression above, for
        patch_door_randomizer.py."""
        self.output("Admin: re-applying door randomization (full sweep, may take a while) ...")
        ok, msg = apply_door_randomizer()
        self.output(("OK: " if ok else "FAILED: ") + msg)
        return ok

    def _cmd_ap_apply_additional_enemies(self) -> bool:
        """Same again, for patch_additional_enemies.py."""
        self.output("Admin: re-applying additional enemies (full sweep, may take a while) ...")
        ok, msg = apply_additional_enemies()
        self.output(("OK: " if ok else "FAILED: ") + msg)
        return ok

    def _cmd_ap_raw(self, *parts: str) -> bool:
        """TEMPORARY/research: send a raw diagnostic command straight to the
        extender socket, e.g. !ap_raw DUMPMEM:16EBB958:64 (hex address, no
        0x prefix, decimal size). Also READBYTE:<hexaddr>, WRITEBYTE:<hexaddr>:<value>,
        SCANBYTES:<comma-separated-hex-bytes>, SNAPSHOT:<name> -- whatever
        ap_extender.c's ap_dispatch_command understands. Output (e.g. a
        DUMPMEM dump) goes to a file next to kse.log, NOT this console --
        see kotor_engine_constraints memory / FutureDesign.md for the Force
        Powers offset hunt this exists for."""
        command = " ".join(parts)
        if not command:
            self.output("Usage: !ap_raw <command>, e.g. !ap_raw DUMPMEM:16EBB958:64")
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
                        f"all deliveries/corrections paused. Run !ap_confirm_character if this is intentional.")
        pending = ext.pending_deliveries()
        if pending:
            self.output(f"Pending (queued, not yet confirmed applied): {[d.arm_name for d in pending]}")
        else:
            self.output("Pending: none")
        recent = ext.recent_deliveries(10)
        for d in recent:
            state = f"APPLIED ({d.detail})" if d.applied_at else "queued"
            self.output(f"  {d.arm_name}: {state}")
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
    (character_name, item_index) tuples already settled in a previous
    session. Missing/unreadable log = empty set, not an error -- a first
    run (or a deleted log) just means nothing's been delivered yet, which
    is the correct starting assumption."""
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
                if entry.get("outcome") in _SETTLED_OUTCOMES and "character" in entry and "index" in entry:
                    keys.add((entry["character"], entry["index"]))
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
    """Every (character, npc_key) pair whose actual join arm
    (companion_<key> -- the real CreateObject+AddPartyMember action) has a
    SETTLED delivery-log entry. Deliberately NOT the recruit-moment CHECK
    (AP|CHECK|COMPANION|N) -- under companion_mode=ap_gated the check
    fires before the real join (the companion only actually joins once
    their item is received), so the check alone is not proof they're in
    the party. Used by the Additional Feats feature's "is this character
    actually recruited yet" gate (2026-09-07). Missing/unreadable log =
    empty set, same reasoning as _load_delivered_keys above.

    2026-09-08 fix #1: a prefix-strip against ANY "companion_"-leading arm
    (excluding only "companion_class:") let a long-retired item's arm_name
    ("companion_jedi", from a since-removed "Companion: Jedi Conversion"
    item -- no longer in Items.py, but old sessions' log lines never get
    cleaned up) resurrect as a fake companion key "jedi", which then
    crashed the remove_companion trap's _COMPANION_NPC_CONST_ALL lookup.
    Whitelisting against the real 9 companion keys (matches
    _COMPANION_NPC_CONST_ALL in generate_trampoline_batch.py) closes this
    off for good instead of relying on excluding known-bad prefixes.

    2026-09-08 fix #2, found live: unlike _delivered_keys (keyed on
    (character, index), so a different character's history can never
    collide), this used to return a bare set of npc_key strings with NO
    character dimension -- ANY past admin !ap_apply test of
    companion_canderous etc., from a WHOLE DIFFERENT test session/
    character, permanently "recruited" that companion for every later
    character too. Confirmed live: remove_companion picked Canderous on a
    fresh character who never received him, traced to a stale admin-test
    log line from an earlier character. Now returns (character, npc_key)
    tuples -- callers filter by the CURRENT character (see
    _is_companion_recruited / _resolve_trap's remove_companion branch),
    the same protection (character, index) already gives _delivered_keys
    for free."""
    keys: typing.Set[typing.Tuple[typing.Optional[str], str]] = set()
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
                    keys.add((entry.get("character"), key))
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
    settled" gate (2026-09-07) -- see
    KotorContext._is_companion_class_finalized for the full check
    (a companion with NO class roll pending at all is also considered
    finalized, trivially, which this loader alone can't tell -- it only
    covers the "a roll existed and it landed" half).

    2026-09-08 fix, same bug class as _load_recruited_companions: this
    used to return bare npc_key strings, so a past admin
    !ap_apply companion_class:<key>:<class> test from a DIFFERENT
    character/session would permanently mark that companion's class
    "finalized" for every later character too. Now returns
    (character, npc_key) tuples -- see _is_companion_class_finalized for
    the current-character filter."""
    keys: typing.Set[typing.Tuple[typing.Optional[str], str]] = set()
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
                    keys.add((entry.get("character"), arm.split(":", 2)[1]))
    except FileNotFoundError:
        pass
    except OSError as e:
        game_events_logger.warning(f"[delivery log] failed to read finalized companion classes ({e})")
    return keys


def _load_pc_class_settled() -> bool:
    """True if a pc_class_soldier/scout/scoundrel arm (StartingClass=
    random_class's base-class write) has ever settled. Used by the
    Additional Feats feature's PC finalization gate (2026-09-07) -- see
    KotorContext._is_pc_class_finalized for the full check (StartingClass
    values other than random_class need no wait at all, which this
    loader alone can't tell)."""
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
                    return True
    except FileNotFoundError:
        pass
    except OSError as e:
        game_events_logger.warning(f"[delivery log] failed to read PC class settlement ({e})")
    return False


def _load_pending_additional_feats() -> dict:
    """Reconstructs which AdditionalFeats items are still awaiting their
    recruited+class-finalized gates, by finding the LATEST log entry for
    each (character, index) pair with an additional_feats: arm (the log
    is append-only in time order, so later lines simply overwrite earlier
    ones for the same key here) and keeping only the ones whose latest
    outcome is still "pending" -- i.e. never resolved to a real send
    outcome (sent/failed_extender_offline/etc.) since. Returns
    {(character, index): (item_name, arm_name)}. Missing/unreadable log =
    empty dict, same reasoning as _load_delivered_keys above."""
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
                key = (entry.get("character"), entry.get("index"))
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
    trap: arms instead -- reconstructs which received EnableTraps items
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
                key = (entry.get("character"), entry.get("index"))
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
        self.extender = ExtenderBridge(on_event=self._on_extender_event)
        self.extender_task: asyncio.Task | None = None
        # New-character safeguard (2026-09-02, explicit user request) --
        # see _evaluate_character_safety() for the full reasoning. Set
        # here, before ReconciliationTracker below, since its guarded
        # callbacks read these at call time.
        self.current_level: typing.Optional[int] = None
        self._known_characters: typing.Set[str] = _load_known_characters()
        # None = not yet evaluated (waiting on name+level), True = safe to
        # proceed, False = BLOCKED pending !ap_confirm_character.
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
        # area_randomizer's bool -- set from slot_data on Connect, used to
        # regenerate ap_poll_shared.ncs for the ACTUAL connected seed (see
        # regenerate_poll_shared() above and on_package's Connected handler).
        self.area_randomizer = False
        # Options.py's StartingClass value -- set from slot_data on Connect,
        # used to regenerate the Dantooine make-jedi suppression wrapper
        # for the ACTUAL connected seed (see
        # regenerate_makejedi_suppressor() above).
        self.starting_class = 0
        # 0=defeat_malak, 1=true_balance, 2=max_level -- matches Options.py's
        # Goal default until slot_data overrides it on Connect. See
        # _check_goal(): sets self.finished_game, which CommonClient's own
        # server loop turns into a real StatusUpdate(CLIENT_GOAL) send.
        self.goal = 0
        # 2026-09-08, found live during Traps testing: asyncio.create_task()
        # returns a Task the event loop only holds a WEAK reference to --
        # per Python's own docs, an unreferenced task "may get garbage
        # collected at any time, even before it's done." _check_pending_
        # traps()/_check_pending_additional_feats() fired create_task(...)
        # without keeping the return value at all, matching this exactly:
        # zero error, zero confirmation log line, the resolution simply
        # never happened. This set is the standard fix -- keep a strong
        # reference until the task finishes, then let it drop.
        self._background_tasks: set = set()
        self._session_id = int(time.time())
        # See _on_extender_event/_watch_for_staleness -- tracks whether the
        # extender's kse.log-tail relay is actually still alive. Real bug
        # found live 2026-09-08: that relay thread can freeze inside the
        # game process (game keeps polling fine, but nothing reaches this
        # client any more) with zero visible symptom beyond "commands stop
        # having any effect" -- this surfaces it as an explicit message
        # instead of silent confusion.
        self._last_game_event_time = time.time()
        self._staleness_warned = False
        self._staleness_task: typing.Optional[asyncio.Task] = None
        # Loaded once at startup -- (character_name, item_index) pairs
        # already settled in a previous session. See DELIVERY_LOG_PATH.
        self._delivered_keys = _load_delivered_keys()
        # Additional Feats feature (2026-09-07): client-side tracking of
        # which companions are actually recruited and which characters'
        # classes have settled -- see _load_recruited_companions/
        # _load_finalized_companion_classes/_load_pc_class_settled above
        # for what each one means, and _is_companion_recruited/
        # _is_companion_class_finalized/_is_pc_class_finalized below for
        # the full gating logic (a trivial "no class change applies at
        # all" case counts as finalized too, which these sets alone don't
        # capture). Loaded once at startup, updated live by _log_delivery.
        self._recruited_companions: typing.Set[typing.Tuple[typing.Optional[str], str]] = \
            _load_recruited_companions()
        self._finalized_companion_classes: typing.Set[typing.Tuple[typing.Optional[str], str]] = \
            _load_finalized_companion_classes()
        self._pc_class_settled: bool = _load_pc_class_settled()
        # {(character, index): (item_name, arm_name)} for every received
        # additional_feats: item still waiting on its gates -- see
        # _load_pending_additional_feats and _check_pending_additional_feats.
        self._pending_additional_feats: typing.Dict[typing.Tuple[str, int], typing.Tuple[str, str]] = \
            _load_pending_additional_feats()
        # {(character, index): (item_name, arm_name)} for every received
        # trap: item not yet resolved -- see _load_pending_traps and
        # _check_pending_traps. Same shape as _pending_additional_feats
        # above, but every trap resolves on the very next poll cycle (no
        # recruited/class-finalized gating concept).
        self._pending_traps: typing.Dict[typing.Tuple[str, int], typing.Tuple[str, str]] = \
            _load_pending_traps()
        # HEAVY_ARMS get pushed here instead of sent immediately -- see
        # _process_heavy_queue(), started from launch(). Only one heavy
        # item is ever in flight at a time, confirmed-applied before the
        # next one sends, so the orchestrator's pending queue can never
        # accumulate more than one multiclass/party-member operation for
        # a single trampoline firing to crash on.
        self._heavy_queue: asyncio.Queue = asyncio.Queue()
        # Decrementing counter for the (character, index) identity of a
        # heavy send that didn't come from a real AP item (an admin
        # !ap_apply, or the automatic no_jedi/randomize_all companion_class
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
        everything except class switches, not just an audit trail."""
        if outcome in _SETTLED_OUTCOMES:
            self._delivered_keys.add((character, index))
            # Additional Feats feature (2026-09-07): keep the recruited/
            # class-finalized tracking sets live, same data the startup
            # loaders derive from the log -- see those functions'
            # docstrings for why each prefix check is shaped this way.
            if arm_name.startswith("companion_class:"):
                self._finalized_companion_classes.add((character, arm_name.split(":", 2)[1]))
            elif arm_name.startswith("companion_"):
                self._recruited_companions.add((character, arm_name[len("companion_"):]))
            elif arm_name in ("pc_class_soldier", "pc_class_scout", "pc_class_scoundrel"):
                self._pc_class_settled = True
        entry = {
            "time": time.time(),
            "session": self._session_id,
            "slot": getattr(self, "username", None),
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
        """Additional Feats feature (2026-09-07): is this companion
        actually in the party yet? See _load_recruited_companions'
        docstring for why this is the join arm, not the recruit-moment
        check. Filtered to the CURRENT character (2026-09-08 fix) -- see
        _load_recruited_companions' docstring for why the set holds
        (character, npc_key) tuples now, not bare keys."""
        return (self.reconciler.current_character_name, npc_key) in self._recruited_companions

    def _is_companion_class_finalized(self, npc_key: str) -> bool:
        """Additional Feats feature (2026-09-07): has this companion's
        class settled -- either a real class-change action for them has
        already landed, or none was ever coming in the first place under
        the current CompanionClass mode. See Options.py's CompanionClass
        for what each mode value means. Filtered to the CURRENT character
        (2026-09-08 fix), same reasoning as _is_companion_recruited."""
        if (self.reconciler.current_character_name, npc_key) in self._finalized_companion_classes:
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
        """Additional Feats feature (2026-09-07): PC equivalent of
        _is_companion_class_finalized. StartingClass=random_class applies
        immediately/automatically at game start (not item-gated), so this
        is near-instantly true in practice -- tracked properly anyway
        rather than assumed."""
        if self._pc_class_settled:
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

        2026-09-08 fix, found live: the draw used to sample the full pool
        unfiltered, so it could (and did -- confirmed live, drew 3/3
        already-known feats in one admin test) land entirely on feats the
        character already has. The real grant NWScript already guards each
        one with GetHasFeat before granting, so an already-known draw was
        never harmful, just a wasted item with no observable effect.
        PC-only fix: current_feats (FEATREPORT) only ever tracks the PC,
        never companions (no per-companion feat poll exists), so a
        companion draw still can't be deduped against what they already
        know -- same as before this fix, not a regression.

        2026-09-08 fix #2: also exclude the 3 Jedi-signature feats
        (Force Jump/Force Focus/Force Immunity: Fear) whenever the target
        isn't currently Jedi -- those are dead weight on a character with
        no Force levels/Force Points to use them with. Unlike the
        already-known filter above, THIS check works for companions too:
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

    async def _resolve_additional_feats(self, key: typing.Tuple[str, int], item_name: str, arm_name: str,
                                         npc_key: str, feat_ids: typing.List[int]) -> None:
        """The actual send, once _check_pending_additional_feats decides a
        pending item's gates have cleared. On failure (extender offline),
        puts the item back into _pending_additional_feats so the next
        poll cycle retries automatically -- no separate terminal failure
        state needed, "pending" already correctly describes "not yet
        resolved" either way."""
        character, index = key
        sent = await self.extender.send_additional_feats(npc_key, feat_ids)
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

    def _trap_noop(self, key: typing.Tuple[str, int], item_name: str, arm_name: str, reason: str) -> None:
        """Marks a trap settled with no effect -- the "0 or 1 of
        something to halve" case Options.py's EnableTraps docstring
        promises is a safe no-op, not a retry-forever or an error."""
        character, index = key
        game_events_logger.info(f"[trap no-op] {item_name} -> {reason}, nothing to do")
        self._log_delivery(character, index, item_name, arm_name, "sent")

    async def _resolve_trap(self, key: typing.Tuple[str, int], item_name: str, arm_name: str, trap_type: str) -> None:
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
        character, index = key
        reconciler = self.reconciler
        sent = None  # tri-state: None = no-op path taken below (already logged), else bool

        if trap_type == "reduce_skill":
            # Retired cut_level's replacement (2026-09-08) -- SetXP can't
            # reduce XP below the current level's threshold once it's
            # already banked (confirmed live), so a level/XP trap can
            # never be made reliable. This reuses EffectSkillDecrease, the
            # same plain-effect approach already proven live for the 5
            # ability traps below, picking one random currently-known
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
            # 2026-09-08 fix, found live: this used to pick from the WHOLE
            # _recruited_companions set with no character filter, so a
            # stale admin-test entry from a completely different
            # character/session (e.g. an old companion_canderous test)
            # could get "removed" from a character who never actually had
            # them. See _load_recruited_companions' docstring.
            current_char = reconciler.current_character_name
            candidates = sorted(npc for (char, npc) in self._recruited_companions if char == current_char)
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
                self._recruited_companions.discard((current_char, target))

        elif trap_type == "remove_half_inventory":
            backpack = reconciler.current_inventory  # {tag: stacksize}, backpack-only already
            eligible = [tag for tag in backpack if not GEAR_ITEMS.get(tag, {}).get("quest_dependent")]
            if len(eligible) <= 1:
                self._trap_noop(key, item_name, arm_name, f"only {len(eligible)} non-quest backpack item(s)")
                return
            chosen = random.sample(eligible, len(eligible) // 2)
            params = ",".join(chosen)
            sent = await self.extender.send_trap("remove_half_inventory", params)

        elif trap_type in ("reduce_str", "reduce_dex", "reduce_int", "reduce_wis", "reduce_cha"):
            ability_key = trap_type[len("reduce_"):]  # "str"/"dex"/"int"/"wis"/"cha"
            current = reconciler.current_abilities.get(ability_key, 0)
            if current <= 1:
                self._trap_noop(key, item_name, arm_name, f"{ability_key} already minimal ({current})")
                return
            decrease = current - (current // 2)
            sent = await self.extender.send_trap(trap_type, str(decrease))

        else:
            game_events_logger.warning(f"[trap] unknown trap_type {trap_type!r} for {item_name} -- dropping.")
            self._log_delivery(character, index, item_name, arm_name, "sent")
            return

        if sent:
            logger.info(f"[queued for game] {item_name} -> trap:{trap_type}")
            self._log_delivery(character, index, item_name, arm_name, "sent")
        else:
            game_events_logger.warning(f"[NOT SENT -- extender offline] {item_name} -> trap:{trap_type}. "
                            f"Will retry next poll cycle.")
            self._pending_traps[key] = (item_name, arm_name)

    def _on_extender_event(self, event: str) -> None:
        # Surface every AP| marker to its own "Heartbeat" GUI tab (not the
        # main "Archipelago" tab) -- this is the raw heartbeat/status-poll
        # firehose (XPREPORT, INVENTORY, CHECK|AREA, TRAMPOLINE_BATCH_FIRED,
        # etc.), useful for debugging but not part of the curated 4-item
        # summary (extender connecting, AP server connecting, checks found,
        # items sent) the main tab is scoped to.
        game_events_logger.info(f"[game] {event}")
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
            # (poll_shared's own LAST report each cycle) -- AdditionalFeats
            # (2026-09-07) re-checks its pending items here rather than on
            # every single event, since recruited/class-finalized state
            # only meaningfully changes once per cycle at most.
            self._check_pending_additional_feats()
            # Traps (2026-09-08): same "poll cycle complete" hook -- every
            # pending trap resolves on the very next cycle after receipt
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
                            # Routed through _queue_heavy (2026-09-02, was a
                            # direct send before) -- companion_* arms are all
                            # in HEAVY_ARMS; this path sent straight through
                            # regardless, the same gap _cmd_ap_apply had.
                            self._queue_heavy(arm_name, f"(vanilla auto-grant) {arm_name}")
                            self._maybe_queue_companion_class(arm_name)

            self._check_goal(event)

        if self.ui is not None:
            self.ui.refresh_status()

    async def _watch_for_staleness(self) -> None:
        """Runs for the life of the connection, checking every 10s whether
        ANY line has been relayed from the extender in the last 30s. Found
        live 2026-09-08: the extender's kse.log-tail relay thread can
        freeze inside the game process (the game itself keeps polling
        fine -- confirmed via kse.log timestamps still advancing -- but
        nothing reaches this client any more) with no visible symptom
        beyond "nothing I do seems to have any effect," which is
        indistinguishable at a glance from the much more common, totally
        benign cause: the game window losing OS focus pauses ALL of its
        script/dispatcher activity, including polling, until refocused
        (confirmed multiple times live -- refocusing alone fixed it). This
        can't tell the two apart from here (both look identical: silence),
        so the message covers both rather than guessing which one it is.
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
                    f"activity while unfocused, and resumes the instant it's refocused (confirmed "
                    f"live, this is the common case). If it's already focused and this persists, "
                    f"the extender's own relay thread may have frozen inside the game process -- "
                    f"a client restart won't fix that, only a full close-and-relaunch of KOTOR "
                    f"itself will.")

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
            if self.location_tracker.true_balance_reached():
                game_events_logger.info("[goal] True Balance reached (both alignment extremes) -- goal complete!")
                self.finished_game = True
        elif self.goal == 2:  # max_level
            m = _LEVEL_RE.search(event)
            if m and int(m.group(1)) >= MAX_LEVEL:
                game_events_logger.info(f"[goal] Max level ({MAX_LEVEL}) reached -- goal complete!")
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
        if cmd == "Connected":
            slot_data = args.get("slot_data", {}) or {}
            write_slot_data_for_patch_scripts(
                slot_data.get("loot_mode", 0), slot_data.get("door_mapping"),
                bool(slot_data.get("area_randomizer", False)), slot_data.get("starting_class", 0),
                slot_data.get("additional_enemies_mode", 0), self.server_seed_name or self.seed_name,
                bool(slot_data.get("progression_system", False)))
            self.companion_mode = slot_data.get("companion_mode", 0)
            self.companion_class_rolls = slot_data.get("companion_class_rolls", {})
            self.companion_class_mode = slot_data.get("companion_class_mode", 0)
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

            if self._staleness_task is None or self._staleness_task.done():
                self._last_game_event_time = time.time()
                self._staleness_warned = False
                self._staleness_task = asyncio.create_task(self._watch_for_staleness())

            self.area_randomizer = bool(slot_data.get("area_randomizer", False))
            asyncio.get_event_loop().run_in_executor(
                None, self._regenerate_poll_shared_and_log, self.area_randomizer)

            self.starting_class = slot_data.get("starting_class", 0)
            asyncio.get_event_loop().run_in_executor(
                None, self._regenerate_makejedi_suppressor_and_log, self.starting_class)

            # 2026-09-08 (Option B, the "3-step install" plan): these 3 used
            # to be a separate manual README.md step a tester ran by hand
            # against --game-dir after connecting once. write_slot_data_for_
            # patch_scripts above already wrote this connection's real
            # loot_mode/door_mapping/additional_enemies_mode/seed_name
            # synchronously before this point, so it's safe to fire all 3
            # here the same way poll_shared/makejedi already do -- gated by
            # seed_name so a same-seed reconnect doesn't re-pay the full
            # RIM-sweep cost every launch (see PATCHED_SEEDS_MARKER_PATH).
            seed_name = self.server_seed_name or self.seed_name
            asyncio.get_event_loop().run_in_executor(
                None, self._apply_item_suppression_and_log, seed_name, False)
            asyncio.get_event_loop().run_in_executor(
                None, self._apply_door_randomizer_and_log, seed_name, False)
            asyncio.get_event_loop().run_in_executor(
                None, self._apply_additional_enemies_and_log, seed_name, False)

            # Always sent, even when every planet's list is empty (a
            # shop_randomizer=off seed) -- 2026-08-29, fixing a real bug:
            # _shop_stock.json persists on disk across sessions/seeds, and
            # skipping the send for an empty dict left a PREVIOUS seed's
            # stock in place indefinitely when reconnecting to one with
            # shop_randomizer off. __init__.py's _shop_stock() now always
            # returns real (possibly empty) lists for all 5 planets so
            # every fresh Connect unconditionally overwrites all of them
            # with the current seed's real answer.
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
            game_events_logger.info("see !ap_locations for the full list, or !ap_status for progress).")
            game_events_logger.info("")
            game_events_logger.info("Try: !ap_status      (extender connection + delivery status)")
            game_events_logger.info("Try: !ap_apply credits  (admin: apply directly, bypassing AP)")
            game_events_logger.info("Try: !ap_check <name>   (manual override -- normally checks fire automatically)")
        if cmd == "ReceivedItems":
            # NOT args["items"] -- that's only the full cumulative list on
            # the very first connect (index=0); every later push sends just
            # the delta with a nonzero index. self.items_received is
            # CommonContext's own list, already correctly assembled by
            # respecting that index (see CommonClient.py's ReceivedItems
            # handling, which runs before on_package). Slicing args["items"]
            # directly silently dropped every delivery after the first --
            # confirmed live: Credit Chit landed (it was delivery #1), both
            # Experience Points pickups afterward vanished with no trace.
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
        catalog per planet, not a single universal list (2026-08-29)."""
        while not self.extender.is_connected:
            await asyncio.sleep(1.0)
        await self.extender.send_shop_stock(planet_stock)

    async def _deliver_item(self, item_name: str, arm_name: str, index: int) -> None:
        # Wait for the first NAMEREPORT -- the delivery-log gate below needs
        # a character name to key on, and there's no sound fallback if we
        # don't have one (a bounded timeout here previously "failed open"
        # by processing with character=None, which can never match a real
        # name later and silently defeated the whole dedup for anything
        # that arrived before the game had actually launched -- confirmed
        # live: connecting the AP client before the game is up is a normal
        # sequence, not an edge case, so this can't be a short wait).
        # Unbounded is fine -- this is one lightweight sleeping task per
        # item, not something blocking anything else, and it resolves
        # naturally the moment the player launches the game.
        while self.reconciler.current_character_name is None:
            await asyncio.sleep(0.5)
        character = self.reconciler.current_character_name

        # New-character safeguard (2026-09-02) -- wait for a level too
        # (needed to evaluate safety, see _evaluate_character_safety), and
        # if the character turns out to be unrecognized and not a fresh
        # level-1 start, keep waiting here rather than proceeding -- this
        # item's delivery is paused, not dropped, until a human runs
        # !ap_confirm_character (or reconnects with the right save,
        # meaning current_character_name changes and gets re-evaluated
        # from scratch). Same "normal sequence, not an edge case" reasoning
        # as the NAMEREPORT wait above -- unbounded is fine, this is one
        # lightweight sleeping task per item.
        while self.current_level is None:
            await asyncio.sleep(0.5)
        while self._character_confirmed is False:
            await asyncio.sleep(2.0)

        if arm_name in ("xp", "credits"):
            # MUST run every session regardless of the delivery-log gate --
            # confirmed live, and dangerously so: expected_scalar is pure
            # in-memory accounting with no persistence of its own, rebuilt
            # from note_item_received() calls. Gating this the same way as
            # real one-time arm sends left expected_scalar["xp"] at 0 on a
            # fresh process even though 6000 XP had legitimately been
            # earned, and since both xp AND credits clamps are now
            # BIDIRECTIONAL (2026-09-03), the very next area transition/
            # poll queued a corrective set_xp/set_credits down to the
            # stale expected value -- a real, immediate risk of wiping out
            # already-earned XP or credits, not just a bookkeeping quirk.
            # Safe to always replay: this has no real one-time side effect,
            # just updates a counter.
            self.reconciler.note_item_received(arm_name)
            game_events_logger.info(f"[queued for game] {item_name} -> {arm_name} (applied via reconciliation)")
            self._log_delivery(character, index, item_name, arm_name, "reconciled")
            return

        # Primary reconnect-safety gate for everything except class
        # switches: if this exact (character, index) was already settled
        # in a previous session, don't reprocess it at all -- no expected-
        # total update, no send. A fresh character (never in the log) still
        # gets everything; reconnecting to the same one doesn't replay it.
        if (character, index) in self._delivered_keys:
            game_events_logger.info(f"[already delivered] {item_name} -> {arm_name} (character {character!r}, item #{index})")
            return

        if arm_name.startswith("additional_feats:"):
            # AdditionalFeats (2026-09-07): doesn't send anything to the
            # game yet -- the item is just a marker. Record it as pending
            # (a NON-settled outcome, so a reconnect before its gates clear
            # correctly re-establishes this same wait rather than being
            # treated as a brand new item OR as already-delivered) and let
            # _check_pending_additional_feats (run every poll cycle, see
            # _on_extender_event's SKILLREPORT hook) pick it up once the
            # target character is both recruited and their class has
            # settled.
            self._pending_additional_feats[(character, index)] = (item_name, arm_name)
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
            outcome = "sent" if sent else "failed_extender_offline"
            self._log_delivery(character, index, item_name, arm_name, outcome)
            game_events_logger.info(f"[queued for game] {item_name} -> set_credits:0 (trap:remove_credits)")
            return

        if arm_name.startswith("trap:"):
            # Every other trap (Options.py's EnableTraps): the item is
            # just a marker, same "decided client-side at delivery" shape
            # as additional_feats -- _check_pending_traps (run every poll
            # cycle) computes the real specifics from currently-tracked
            # state and resolves it, no gating needed (unlike
            # additional_feats' recruited/class-finalized wait).
            self._pending_traps[(character, index)] = (item_name, arm_name)
            self._log_delivery(character, index, item_name, arm_name, "pending")
            game_events_logger.info(f"[pending] {item_name} -> resolving next poll cycle")
            return

        if arm_name in HEAVY_ARMS or arm_name.startswith("companion_class:"):
            # Multiclassing/level-up-GUI/party-member arms don't send
            # immediately -- confirmed live: batching several of these
            # together (even all first-time applications, no repeats
            # involved) crashed the game twice tonight. Queued instead;
            # _process_heavy_queue() sends one at a time, waiting for each
            # to actually confirm-applied before the next one goes out, so
            # the pending queue can never accumulate more than one of these
            # for a single trampoline firing to crash on.
            #
            # companion_class: added 2026-09-02 -- confirmed live it hit
            # the EXACT same crash (a real jedi_companion item's
            # companion_class:carth:guardian landed in a 12-item batch
            # alongside unrelated grants and crashed the game) despite
            # doing an equally heavy SetCreatureField+4-feat-array write.
            # It was never in HEAVY_ARMS at all -- a plain `in HEAVY_ARMS`
            # check can never match a colon-parameterized string, so this
            # needs its own explicit prefix check, not just a set entry.
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

    def _regenerate_poll_shared_and_log(self, area_randomizer: bool) -> None:
        """Runs regenerate_poll_shared() (a blocking subprocess call, hence
        this being invoked via run_in_executor from on_package rather than
        awaited directly) and logs the outcome either way -- see
        regenerate_poll_shared()'s own docstring for why this exists.
        Also callable directly from _cmd_ap_regen_poll as the manual
        fallback, using whatever area_randomizer this context currently
        has cached from the last Connected."""
        ok, msg = regenerate_poll_shared(area_randomizer)
        if ok:
            game_events_logger.info(f"[poll_shared] regenerated for area_randomizer={area_randomizer}: {msg}")
        else:
            game_events_logger.warning(f"[poll_shared] regeneration FAILED (area_randomizer={area_randomizer}): {msg}")

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

    def _apply_seed_patch_if_new(self, key: str, seed_name: str | None, apply_fn, force: bool = False) -> None:
        """Shared gate for the 3 heavier per-seed patch scripts (item
        suppression, door randomization, additional enemies) -- see
        PATCHED_SEEDS_MARKER_PATH's docstring for why these are gated on
        the seed actually changing rather than always re-run like
        poll_shared/makejedi. `force=True` (the manual admin-command
        fallback) bypasses the marker check entirely -- always re-applies
        regardless of what's recorded, then updates the marker same as a
        normal run. A missing/unknown seed_name (shouldn't happen by the
        time Connected fires, but matches this project's general
        "log and continue rather than raise from a background task" style
        for anything running via run_in_executor) still applies once and
        records whatever was given, rather than silently skipping forever."""
        if not force and seed_name is not None and _load_patched_seed(key) == seed_name:
            game_events_logger.info(f"[{key}] already applied for seed {seed_name!r} -- skipping re-run.")
            return
        ok, msg = apply_fn()
        if ok:
            game_events_logger.info(f"[{key}] applied for seed {seed_name!r}: {msg}")
            _save_patched_seed(key, seed_name)
        else:
            game_events_logger.warning(f"[{key}] APPLY FAILED for seed {seed_name!r}: {msg}")

    def _apply_item_suppression_and_log(self, seed_name: str | None, force: bool = False) -> None:
        """Runs apply_item_suppression() (a blocking subprocess call,
        hence run_in_executor from on_package rather than awaited
        directly), gated by _apply_seed_patch_if_new. Also callable
        directly (force=True) from the manual admin-command fallback."""
        self._apply_seed_patch_if_new("item_suppression", seed_name, apply_item_suppression, force)

    def _apply_door_randomizer_and_log(self, seed_name: str | None, force: bool = False) -> None:
        """Same shape as _apply_item_suppression_and_log, for
        apply_door_randomizer()."""
        self._apply_seed_patch_if_new("door_randomizer", seed_name, apply_door_randomizer, force)

    def _apply_additional_enemies_and_log(self, seed_name: str | None, force: bool = False) -> None:
        """Same shape again, for apply_additional_enemies()."""
        self._apply_seed_patch_if_new("additional_enemies", seed_name, apply_additional_enemies, force)

    def _queue_heavy(self, arm_name: str, label: str) -> None:
        """The ONE place any heavy send not already going through
        _deliver_item's real-item path enters _heavy_queue -- used by the
        automatic no_jedi/randomize_all companion_class follow-up below and
        by !ap_apply's admin bypass. Confirmed live (2026-09-02): a
        companion_class send that skips this queue can land in the same
        TRAMPOLINE_BATCH_FIRED batch as unrelated grants and crash the
        game -- the exact same crash class HEAVY_ARMS/_heavy_queue already
        exists to prevent for class_guardian/companion_carth/etc., just not
        yet extended to companion_class when that action was added later.
        Rather than have three separate call sites each remember to check
        HEAVY_ARMS/route correctly (and risk a fourth future call site
        forgetting to), every non-real-item heavy send funnels through
        here. item_name/character are cosmetic (log/delivery-log labels
        only) for an admin-or-automatic send with no real AP item behind
        it; index is a unique negative counter so it can never collide
        with a real item's index or with another admin send of the same
        arm in _delivered_keys.

        Also gated on the new-character safeguard (2026-09-02) -- an
        admin/auto heavy send is just as capable of mutating the wrong
        character's state as a real item delivery is, so it gets the
        same pause-until-confirmed treatment. See
        _evaluate_character_safety().

        2026-09-08 fix, found live: this used to hardcode character=None
        in the queued tuple regardless of who's actually playing, so
        _log_delivery's live-update recorded every companion join/class
        change routed through here (admin !ap_apply AND the automatic
        no_jedi/randomize_all follow-up) under character=None -- not the
        real current character. Harmless before _recruited_companions/
        _finalized_companion_classes became character-scoped (2026-09-08,
        see _load_recruited_companions), but now that they are, it broke
        _is_companion_recruited/_is_companion_class_finalized for every
        arm routed through here: confirmed live, a companion admin-joined
        via !ap_apply companion_mission then failed the
        (current_character, npc_key) lookup because it was actually
        stored as (None, npc_key). Now records the real current character
        (or None if genuinely not known yet -- an honest gap, not a
        wrong guess)."""
        if self._character_confirmed is False:
            game_events_logger.warning(f"[SAFEGUARD] Skipping {arm_name!r} -- unrecognized character, "
                            f"run !ap_confirm_character first if this is intentional.")
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
                            f"unrecognized character, run !ap_confirm_character first if this is intentional.")
            return False
        return await self.extender.send_apply(arm_name)

    async def _guarded_send_apply_value(self, action: str, value: int) -> bool:
        """Same as _guarded_send_apply, for the APPLYVALUE half (set_xp/
        set_credits) -- see that method's docstring."""
        if self._character_confirmed is False:
            game_events_logger.warning(f"[SAFEGUARD] Skipping reconciliation send ({action}={value}) -- "
                            f"unrecognized character, run !ap_confirm_character first if this is intentional.")
            return False
        return await self.extender.send_apply_value(action, value)

    def _evaluate_character_safety(self) -> None:
        """Safeguard added 2026-09-02, per explicit user request: if the
        currently-connected character's name has NEVER appeared in the
        delivery log before, AND they're not a fresh level-1 start, pause
        every delivery/reconciliation action until a human confirms this
        is intentional (!ap_confirm_character).

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
                        "!ap_confirm_character to proceed. Otherwise, load the correct "
                        "character/save and reconnect.")
        game_events_logger.warning("=" * 70)

    def _maybe_queue_companion_class(self, arm_name: str) -> None:
        """CompanionClass=no_jedi/randomize_all: right after a companion
        recruit arm is sent (either path -- the ap_gated real-item flow via
        _do_deliver below, or the CompanionMode=normal self-grant branch in
        on_package above), also queue their assigned class if one exists.
        A no-op for jedi_companion/off (self.companion_class_rolls empty) and
        for HK-47/T3-M4 (droids, never given an assignment). Routed through
        _queue_heavy (2026-09-02, was a direct send before) -- same crash
        class as any other companion_class send, see that method's
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
            resref = arm_name[len("give_item:"):]
            count = self._gear_item_count(resref)
            sent = await self.extender.send_apply_item(resref, count)
            if sent:
                logger.info(f"[queued for game] {item_name} -> give_item:{resref} x{count}")
                self._log_delivery(character, index, item_name, arm_name, "sent")
            else:
                game_events_logger.warning(f"[NOT SENT -- extender offline] {item_name} -> give_item:{resref}. "
                                f"Will need !ap_apply manually once the game is up, "
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
                logger.info(f"[queued for game] {item_name} -> companion_class:{npc_key}:{class_name}")
                self._log_delivery(character, index, item_name, arm_name, "sent")
            else:
                game_events_logger.warning(f"[NOT SENT -- extender offline] {item_name} -> companion_class:{npc_key}:{class_name}. "
                                f"Will need !ap_apply manually once the game is up, "
                                f"or a resend mechanism (not yet built).")
                self._log_delivery(character, index, item_name, arm_name, "failed_extender_offline")
            return
        if arm_name in CLASS_ARM_TO_KEY:
            # Class switches are one-shot (AddMultiClass + ShowLevelUpGUI)
            # and NOT safe to re-fire -- confirmed live: a reconnect resent
            # class_sentinel to an already-multiclassed character as part
            # of a 10-item batch and the game crashed. The delivery log
            # above already blocks most reconnect replays, but this is a
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
            self.reconciler.note_item_received(arm_name)
            logger.info(f"[queued for game] {item_name} -> {arm_name}")
            self._log_delivery(character, index, item_name, arm_name, "sent")
            self._maybe_queue_companion_class(arm_name)
        else:
            game_events_logger.warning(f"[NOT SENT -- extender offline] {item_name} -> {arm_name}. "
                            f"Will need !ap_apply {arm_name} manually once the game is up, "
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
                self.checks_label = MDLabel(text="Checks: 0 / 0", size_hint_y=None, height=30)
                self.pending_label = MDLabel(text="Pending delivery: none", size_hint_y=None, height=60)
                self.recent_label = MDLabel(text="Recent items: none")
                self.add_widget(self.connection_label)
                self.add_widget(self.checks_label)
                self.add_widget(self.pending_label)
                self.add_widget(self.recent_label)

            def refresh(self):
                ext = self.ctx.extender
                self.connection_label.text = f"Extender: {'CONNECTED' if ext.is_connected else 'NOT CONNECTED'}"
                checked = len(self.ctx.checked_locations)
                total = len([lid for lid in self.ctx.location_names[self.ctx.game] if lid >= 0])
                self.checks_label.text = f"Checks: {checked} / {total}"

                pending = ext.pending_deliveries()
                if pending:
                    names = ", ".join(d.arm_name for d in pending)
                    self.pending_label.text = (
                        f"Pending delivery ({len(pending)} queued, not yet confirmed applied):\n{names}\n"
                        f"(these apply on your next area entry, not instantly)"
                    )
                else:
                    self.pending_label.text = "Pending delivery: none"

                recent = ext.recent_deliveries(8)
                if recent:
                    lines = []
                    for d in recent:
                        state = f"applied ({d.detail})" if d.applied_at else "queued"
                        lines.append(f"  {d.arm_name}: {state}")
                    self.recent_label.text = "Recent items:\n" + "\n".join(lines)
                else:
                    self.recent_label.text = "Recent items: none"

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
