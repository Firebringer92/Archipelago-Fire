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

# NPC_* index (nwscript.nss) -> the arm that re-grants that companion.
# Order matches Locations.py's generator COMPANIONS list.
COMPANION_IDX_TO_ARM = [
    "companion_bastila", "companion_canderous", "companion_carth",
    "companion_hk47", "companion_jolee", "companion_juhani",
    "companion_mission", "companion_t3m4", "companion_zaalbar",
]

_ID_TO_LOCATION_DATA = {data.id: data for data in location_table.values()}

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
    "dump_statblock",  # TEMPORARY (2026-08-31): Force Powers offset research,
                       # see kotor_engine_constraints memory / PHASE14.md.
    "pc_class_soldier", "pc_class_scout", "pc_class_scoundrel",
    # Slots 37-41 backfilled 2026-09-03 -- existed in generate_trampoline_
    # batch.py's APPLIES table and in ap_extender.c's AP_ARM_NAMES (after
    # backfilling that too) but were missing here, so /ap_apply couldn't
    # reach them by name -- only raw numeric queuing could. TEMPORARY
    # research arms, same as dump_statblock above.
    "dump_statblock_carth", "dump_statblock_juhani",
    "carth_addmulticlass_hybrid_test", "juhani_addmulticlass_scoundrel_test",
    "juhani_grant_critical_strike_test",
    "test_credits_chain",  # TEMPORARY (2026-09-03): credits derivation
                           # chain confirmation -- see offsets.h's
                           # KSE_CREDITS_CHAIN_ID comment.
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
        loot_mode: int, door_mapping: dict | None, area_randomizer: bool, starting_class: int) -> None:
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
    does that)."""
    try:
        os.makedirs(os.path.dirname(SLOT_DATA_PATH), exist_ok=True)
        with open(SLOT_DATA_PATH, "w", encoding="utf-8") as f:
            json.dump({
                "loot_mode": loot_mode, "door_mapping": door_mapping,
                "area_randomizer": area_randomizer, "starting_class": starting_class,
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
        build_companion_class_block for the valid name/class values."""
        if not arm_name:
            self.output(f"Usage: !ap_apply <name>. Known names: {', '.join(KNOWN_ARM_NAMES)}, "
                        f"or give_item:<resref>[:<count>], or companion_class:<name>:<class>")
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
        self._session_id = int(time.time())
        # Loaded once at startup -- (character_name, item_index) pairs
        # already settled in a previous session. See DELIVERY_LOG_PATH.
        self._delivered_keys = _load_delivered_keys()
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

    def _log_delivery(self, character: str, index: int, item_name: str, arm_name: str, outcome: str) -> None:
        """Appends one line to DELIVERY_LOG_PATH and updates the in-memory
        settled-keys set for outcomes that should block reprocessing on a
        future reconnect. See DELIVERY_LOG_PATH's comment for the full
        design -- this is the primary reconnect-safety mechanism for
        everything except class switches, not just an audit trail."""
        if outcome in _SETTLED_OUTCOMES:
            self._delivered_keys.add((character, index))
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

    def _on_extender_event(self, event: str) -> None:
        # Surface every AP| marker to its own "Heartbeat" GUI tab (not the
        # main "Archipelago" tab) -- this is the raw heartbeat/status-poll
        # firehose (XPREPORT, INVENTORY, CHECK|AREA, TRAMPOLINE_BATCH_FIRED,
        # etc.), useful for debugging but not part of the curated 4-item
        # summary (extender connecting, AP server connecting, checks found,
        # items sent) the main tab is scoped to.
        game_events_logger.info(f"[game] {event}")
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
                bool(slot_data.get("area_randomizer", False)), slot_data.get("starting_class", 0))
            self.companion_mode = slot_data.get("companion_mode", 0)
            self.companion_class_rolls = slot_data.get("companion_class_rolls", {})
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

            self.area_randomizer = bool(slot_data.get("area_randomizer", False))
            asyncio.get_event_loop().run_in_executor(
                None, self._regenerate_poll_shared_and_log, self.area_randomizer)

            self.starting_class = slot_data.get("starting_class", 0)
            asyncio.get_event_loop().run_in_executor(
                None, self._regenerate_makejedi_suppressor_and_log, self.starting_class)

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
        _evaluate_character_safety()."""
        if self._character_confirmed is False:
            game_events_logger.warning(f"[SAFEGUARD] Skipping {arm_name!r} -- unrecognized character, "
                            f"run !ap_confirm_character first if this is intentional.")
            return
        self._admin_heavy_counter -= 1
        asyncio.create_task(self._heavy_queue.put(
            (label, arm_name, self._admin_heavy_counter, None)))

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
