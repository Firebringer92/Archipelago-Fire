"""Archipelago client for Star Wars: Knights of the Old Republic II (first draft).

It does five things:
  * connects to the Archipelago server and reads the seed's data (slot_data);
  * patches the game's Override folder with that data (k2_patch.py, k2_seed.py): connect, patch, then launch the game;
  * turns every received item into a dispatcher job (k2_dispatcher.py) that the game applies at a calm moment;
  * reads the game's report lines (k2_files.py) and sends the location checks they reach (k2_tracker.py);
  * records the run (k2_tracker.Recorder) so a playthrough can be analysed afterwards.
Run it from the Archipelago folder next to the world, or with the project's ap_core on the path (see tools/run_world_tests.py).
"""
import asyncio
import json
import logging
import os
import random
import sys
import threading
import time
import typing

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import Utils  # noqa: E402
from CommonClient import ClientCommandProcessor, CommonContext, get_base_parser, gui_enabled, logger, server_loop  # noqa: E402
from NetUtils import ClientStatus  # noqa: E402

from k2_dispatcher import DispatchClient, Job, RECEIPT_PREFIX  # noqa: E402
from k2_companions import CompanionPlanner, parse_cc
from k2_extras import build_droid_templates, build_templates, extra_for_item, k1_assets_in, look_lines, template_name
from k2_bazaar import build_files as build_bazaar_files
from k2_bazaar_tokens import token_files
from k2_assets import asset_files
from k2_journal import journal_files, tracker_stage
from k2_crafting import crafting_files, flag_lines, material_yields
from k2_dialogues import master_dialogue_files
from k2_doors import door_files
from k2_enemies import enemy_files
from k2_loot import loot_files
from k2_shop import shop_files
from k2_vendor import build_files as build_vendor_files
from k2_files import Link  # noqa: E402
from k2_patch import Patcher, find_game_dir, path_report, payload_files  # noqa: E402
from k2_seed import config_lines, seed_files  # noqa: E402
from k2_tracker import ItemLog, Recorder, Tracker  # noqa: E402

try:
    from worlds.kotor2.Items import ITEMS, TRAP_BY_KEY
except ImportError:      # the world is not installed next to the client: item names cannot be turned into jobs
    ITEMS = {}
    TRAP_BY_KEY = {}

GAME = "KotOR 2 TSL"
# how much a filler item gives when the seed does not say (the options experience_item and credit_item decide)
DEFAULT_AMOUNTS = {"xp": "8000", "credits": "5000"}
QUIET_ARMS = {"victory"}
# actions /k2_give may send (the simple ones; the arms that rewrite the seed's tables or classes need the real item)
TEST_GIVE_ACTIONS = {"notify", "credits", "xp", "set_xp", "skill", "ability", "token", "trap", "gear", "pass", "materials", "death"}
MODE_LIMITED, MODE_GATED = 1, 2
COMPANIONS_AP_LIMITED = 3
PRESTIGE_LEVEL = 15
# the twelve story companions in slot order (0-11); an item "Companion: <name>" makes that slot usable
BASE_COMPANIONS = ["Atton Rand", "Bao-Dur", "Mandalore", "G0-T0", "Handmaiden", "HK-47", "Kreia", "Mira", "T3-M4", "Visas Marr", "Hanharr", "Disciple"]
TOKEN_FAMILIES = ("telos", "nar", "dxn", "dan", "kor", "endgame")      # the ap_tk_<family> keys the gate scripts read


def companion_job(item_name: str) -> typing.Optional[typing.Tuple[str, str]]:
    """('companion', '<slot>') for a story companion's item; None for the extra and generated companions, which are not built yet."""
    name = item_name.partition(": ")[2]
    if item_name.startswith("Companion: ") and name in BASE_COMPANIONS:
        return "companion", str(BASE_COMPANIONS.index(name))
    return None


def arm_to_job(arm: str, amounts: typing.Optional[typing.Dict[str, str]] = None) -> typing.Tuple[str, str]:
    """'skill:computer_use' -> ('skill', 'computer_use'); 'xp' -> ('xp', '8000') using the seed's amounts."""
    action, _, args = arm.partition(":")
    return action, args or (amounts or DEFAULT_AMOUNTS).get(action, "")


class KotorTwoCommandProcessor(ClientCommandProcessor):
    def _cmd_k2_status(self) -> bool:
        """Show the delivery state: the game's job number, the job in flight, what is waiting."""
        ctx: "KotorTwoContext" = self.ctx
        d = ctx.dispatcher
        cur = d.current.text if d.current else "none"
        self.output("game job number: %s; in flight: %s; waiting: %d; applied this session: %d; failed: %d; replayed: %d" % (
            d.counter, cur, len(d._queue), d.stats["applied"], d.stats["failed"], d.stats["replayed"]))
        self.output("checked locations: %d of %d" % (len(ctx.tracker.checked) if ctx.tracker else 0, len(ctx.tracker.locations) if ctx.tracker else 0))
        return True

    def _cmd_k2_patch(self, game_dir: str = "") -> bool:
        """Write this seed's files into the game's Override folder again (optionally name the game folder). Close the game first if it reports new files."""
        ctx: "KotorTwoContext" = self.ctx
        if game_dir.strip():
            ctx.game_dir_arg = game_dir.strip().strip('"')
        self.output("Writing the seed's files into the game ... (this can take about a minute; the window stays usable)")
        future = asyncio.get_event_loop().run_in_executor(None, lambda: ctx.patch_game(force=True))
        future.add_done_callback(lambda f: self.output(f.result() if not f.exception() else "The patch failed: %s" % f.exception()))
        return True

    def _cmd_k2_unpatch(self) -> bool:
        """Remove everything the client put into the game's Override folder and restore the files it replaced."""
        ctx: "KotorTwoContext" = self.ctx
        patcher = ctx.make_patcher()
        if patcher is None:
            self.output("The game folder was not found. Use /k2_patch <folder> once, or start the client with --game-dir.")
            return False
        self.output(patcher.revert().summary())
        return True

    # ---- testing commands: not part of a normal playthrough (they are removed before a release, docs/TEST_QUEUE.md) ------------------------------
    def _cmd_k2_paths(self) -> bool:
        """Show every folder and file the client depends on and whether it is in order: game folder, extender, Override, config, payload, job folder."""
        ctx: "KotorTwoContext" = self.ctx
        for text in ctx.path_lines():
            self.output(text)
        return True

    def _cmd_k2_prepare(self, k1_dir: str = "") -> bool:
        """Build the payload (compiled scripts and area files made from your own game files) into the payload folder. Takes about half a minute; then type /k2_patch."""
        ctx: "KotorTwoContext" = self.ctx
        tools = os.path.join(HERE, "..", "tools")
        if not os.path.isfile(os.path.join(tools, "build_payload.py")):
            self.output("The payload builder (tools/build_payload.py) is not in this install, so it cannot be built from here.")
            return False
        patcher = ctx.make_patcher()
        if patcher is None:
            self.output("The game folder was not found. Use /k2_patch <folder> once, or start the client with --game-dir.")
            return False
        self.output("Building the payload from %s ... (about half a minute; the game need not be closed)" % patcher.game_dir)
        game, out, k1 = patcher.game_dir, ctx.payload_dir, k1_dir.strip().strip('"') or None

        def work() -> str:
            sys.path.insert(0, os.path.normpath(tools))
            import build_payload
            report = build_payload.build(game, out, k1)
            text = "Payload: %d files in %s." % (len(report["files"]), out)
            if report["problems"]:
                text += " PROBLEMS: " + " | ".join(p[:200] for p in report["problems"])
            else:
                text += " Now type /k2_patch to write them into the game."
            return text

        future = asyncio.get_event_loop().run_in_executor(None, work)
        future.add_done_callback(lambda f: self.output(f.result() if not f.exception() else "The payload could not be built: %s" % f.exception()))
        return True

    def _cmd_k2_give(self, *words: str) -> bool:
        """TESTING ONLY. Give yourself an item as if it had arrived from the multiworld, without telling the server: /k2_give <item name or arm> [count]
        (for example /k2_give Telos Progression 3, /k2_give skill:stealth, /k2_give gear:g_a_class4001, /k2_give vendorpass:skill, /k2_give xp)."""
        ctx: "KotorTwoContext" = self.ctx
        args = list(words)
        count = 1
        if len(args) > 1 and args[-1].isdigit():
            count = max(1, min(50, int(args.pop())))
        text = " ".join(args).strip()
        if not text:
            self.output("Name an item or an arm, for example /k2_give Telos Progression 3 or /k2_give skill:stealth")
            return False
        by_name = {n.lower(): d for n, d in ITEMS.items()}
        data = by_name.get(text.lower())
        arm = data.arm if data is not None else text
        action, args_text = arm_to_job(arm, ctx.amounts)
        if arm.startswith("vendorpass:"):
            action, args_text = "pass", arm[len("vendorpass:"):]
        if action not in TEST_GIVE_ACTIONS:
            self.output("%r cannot be given this way (it needs the real item: crafting types, class and companion items change the seed's tables)." % text)
            return False
        for _ in range(count):
            ctx.dispatcher.submit(action, args_text, message=RECEIPT_PREFIX + "Test: " + text, item_name="test")
        ctx.recorder and ctx.recorder.write("testgive", text=text, action=action, args=args_text, count=count)
        self.output("Sent %d x %s (%s %s) to the game." % (count, text, action, args_text))
        return True

    def _cmd_release(self, gate: str = "") -> bool:
        """Release a story gate that holds you up (for example /release NAR3). It is logged so the gate can be fixed."""
        ctx: "KotorTwoContext" = self.ctx
        gate = gate.strip().upper()
        if not gate:
            self.output("Name the gate, for example /release NAR3")
            return False
        ctx.recorder and ctx.recorder.write("release", gate=gate)
        ctx.dispatcher.submit("release", gate, message="Gate %s released." % gate)
        self.output("Gate %s released (sent to the game)." % gate)
        return True


class KotorTwoContext(CommonContext):
    command_processor = KotorTwoCommandProcessor
    game = GAME
    items_handling = 0b111       # the client delivers everything itself, including our own items

    def __init__(self, server_address, password, link_dir: typing.Optional[str] = None, game_dir: typing.Optional[str] = None,
                 payload_dir: typing.Optional[str] = None, config_path: typing.Optional[str] = None):
        super().__init__(server_address, password)
        self.link = Link(link_dir) if link_dir else Link()
        self.game_dir_arg = game_dir
        self.config_path = config_path
        self.payload_dir = payload_dir if payload_dir is not None else os.path.join(HERE, "payload")
        self.last_patch: typing.Optional[str] = None
        self._patch_files: typing.Optional[typing.Dict[str, bytes]] = None     # what the last patch wrote into Override (crafting rewrites its table in it)
        self._outbox_started = False                         # the outbox history (what the game wrote before this client started) has been read
        self._failed: typing.List[dict] = []                 # jobs the game never answered: sent again when it reports its state (kept across restarts)
        self._dispatch_restored = False                      # the dispatcher's ledger and pending jobs were taken back from the state file (once per run of the client)
        self._patch_lock = threading.Lock()
        self._patch_task: typing.Optional[asyncio.Task] = None
        self._look_lines: typing.List[str] = []                                # ap_look_<slot>=<row> lines of the extras that get a disguise
        self._craft_applied: typing.Optional[tuple] = None                     # (types unlocked, gear items received) the written table and flags were built for
        self._yields: typing.Optional[typing.Dict[str, int]] = None            # Components each gear item gives in crafting mode (read from the game once)
        self._last_trap_link_sent = 0.0
        self.game_xp: typing.Optional[int] = None      # the last XP total the game reported
        self._xp_recheck = False
        self.item_log: typing.Optional[ItemLog] = None
        self.current_module = ""
        self.dispatcher = DispatchClient(self.link)
        self.dispatcher.on_failure = self._on_job_failure
        self.dispatcher.on_applied = self._on_job_applied
        self.tracker: typing.Optional[Tracker] = None
        self.recorder: typing.Optional[Recorder] = None
        self.slot_data: dict = {}
        self.delivered = 0                   # items handed to the dispatcher so far (kept across restarts)
        self.paid_checks = 0                 # checks already paid out as XP / credits in the ap_limited modes (kept across restarts)
        self.unlocked = 0                    # companions already unlocked in the ap_limited companion mode (kept across restarts)
        self.tracker_sent = 0                # the Archipelago Tracker stage already ordered (0 = none yet; kept across restarts)
        self.start_class_sent = False       # the starting class conversion was ordered (kept across restarts)
        self.start_stats_sent = False        # the starting stats were ordered (kept across restarts)
        self.extras_given: typing.Set[int] = set()        # slots of the extra and generated companions already handed over (kept across restarts)
        self.prestige_pending = False        # a Prestige Class item arrived before the player reached level 15 (kept across restarts)
        self.game_level = 0                  # the last character level the game reported
        self.game_alignment = 50             # the last alignment the game reported (0 dark, 100 light)
        self.party_info: typing.Dict[int, tuple] = {}      # CC report: slot -> (class 1, level 1, class 2, level 2) of the companions in the party
        self.planner: typing.Optional[CompanionPlanner] = None
        self._comp_attempts: typing.Dict[int, tuple] = {}
        self.amounts = dict(DEFAULT_AMOUNTS)
        self._outbox_task: typing.Optional[asyncio.Task] = None
        self._state_path: typing.Optional[str] = None

    # ---- connection ------------------------------------------------------------------------------------------------
    def make_gui(self):
        ui = super().make_gui()
        ui.base_title = "KOTOR 2 Archipelago Client"
        return ui

    def on_package(self, cmd: str, args: dict):
        if cmd == "Connected":
            self._on_connected(args)
        elif cmd == "ReceivedItems":
            asyncio.ensure_future(self._deliver_new_items())
        elif cmd == "Bounced" and "TrapLink" in args.get("tags", []):
            self._on_trap_link(args.get("data", {}))

    # ---- DeathLink and TrapLink ----------------------------------------------------------------------------------------------
    # DeathLink: a death in the game (the poll's "DL|death" line) is sent; one that arrives makes the dispatcher kill the player, and that death is not
    # reported back (the game marks it). TrapLink: a trap ITEM that was applied is sent as a Bounce; a received one rolls one of OUR trap types and goes
    # through the dispatcher like an item. A linked trap is never sent on, so two players cannot bounce it forever.
    async def update_trap_link(self, enabled: bool) -> None:
        old = self.tags.copy()
        if enabled:
            self.tags.add("TrapLink")
        else:
            self.tags -= {"TrapLink"}
        if old != self.tags and self.server and not self.server.socket.closed:
            await self.send_msgs([{"cmd": "ConnectUpdate", "tags": self.tags}])

    def on_deathlink(self, data: dict) -> None:
        super().on_deathlink(data)
        who = data.get("source", "another player")
        self.recorder and self.recorder.write("deathlink_in", source=who, cause=data.get("cause", ""))
        self.dispatcher.submit("death", "", message="DeathLink: %s died." % who, item_name="DeathLink")

    def trap_candidates(self) -> typing.List[str]:
        """The trap arms this seed allows ('trap:credits', ...), from the trap_types option."""
        keys = self.slot_data.get("options", {}).get("trap_types") or list(TRAP_BY_KEY)
        return [ITEMS[TRAP_BY_KEY[k]].arm for k in keys if k in TRAP_BY_KEY and TRAP_BY_KEY[k] in ITEMS]

    def _on_trap_link(self, data: dict) -> None:
        if "TrapLink" not in self.tags or not self.slot_data:
            return
        source = data.get("source", "")
        if source == self.player_names.get(self.slot, None) or data.get("time") == self._last_trap_link_sent:
            return                                                    # our own bounce coming back
        candidates = self.trap_candidates()
        if not candidates:
            return
        arm = random.choice(candidates)
        action, args = arm_to_job(arm)
        self.recorder and self.recorder.write("traplink_in", source=source, trap=data.get("trap_name", ""), rolled=arm)
        self.dispatcher.submit(action, args, message="TrapLink from %s: %s" % (source or "another player", args), item_name="TrapLink")

    async def _send_trap_link(self, trap_name: str) -> None:
        if "TrapLink" not in self.tags or not self.server or self.slot is None:
            return
        self._last_trap_link_sent = time.time()
        await self.send_msgs([{"cmd": "Bounce", "tags": ["TrapLink"],
                               "data": {"time": self._last_trap_link_sent, "source": self.player_names[self.slot], "trap_name": trap_name}}])

    def _on_connected(self, args: dict) -> None:
        self.slot_data = args.get("slot_data", {})
        locations = self.slot_data.get("locations", {})
        options = self.slot_data.get("options", {})
        self.tracker = Tracker(locations, self.checked_locations, self.slot_data.get("goal"))
        self.amounts = {"xp": str(options.get("experience_item", DEFAULT_AMOUNTS["xp"])),
                        "credits": str(options.get("credit_item", DEFAULT_AMOUNTS["credits"]))}
        self.dispatcher.guard = int(self.slot_data.get("seed_guard", 0))
        name = "%s_%s" % (self.seed_name or "seed", self.slot or 0)
        self.recorder = Recorder(os.path.join(self.link.directory, "recorder"), name)
        self._state_path = os.path.join(self.link.directory, "client_%s.json" % name)
        try:
            with open(self._state_path) as f:
                saved = json.load(f)
            self.delivered = int(saved.get("delivered", 0))
            self.paid_checks = int(saved.get("paid_checks", 0))
            self.unlocked = int(saved.get("unlocked", 0))
            self.tracker_sent = int(saved.get("tracker_sent", 0))
            self.start_class_sent = bool(saved.get("start_class_sent", False))
            self.start_stats_sent = bool(saved.get("start_stats_sent", False))
            self.extras_given = set(int(x) for x in saved.get("extras_given", []))
            self.prestige_pending = bool(saved.get("prestige_pending", False))
            if int(saved.get("state_version", 1)) < 2:
                self.delivered = 0              # a state file from before the client kept its jobs: it counted items as delivered when it queued them, so deliver them all again
            elif not self._dispatch_restored:
                self._dispatch_restored = True
                again = self.dispatcher.import_state(saved.get("dispatcher", {})) + list(saved.get("failed", []))
                for job in again:
                    self.dispatcher.submit(job["action"], job["args"], message=job.get("message", ""), index=int(job.get("index", -1)), item_name=job.get("item_name", ""))
                if again:
                    logger.info("KOTOR 2: %d job(s) from the last run had not reached the game: they are sent now." % len(again))
        except (OSError, ValueError, KeyError, TypeError):
            self.delivered = self.paid_checks = self.unlocked = self.tracker_sent = 0
            self.start_class_sent = False
        self.planner = CompanionPlanner(self.slot_data, self._prestige_slots())
        self.recorder.write("connected", seed=self.seed_name, slot=self.slot, locations=len(locations), delivered=self.delivered,
                            options=self.slot_data.get("options"))
        logger.info("KOTOR 2: connected; %d locations in this seed, %d items already delivered." % (len(locations), self.delivered))
        asyncio.ensure_future(self.update_death_link(bool(options.get("death_link"))))
        asyncio.ensure_future(self.update_trap_link(bool(options.get("trap_link"))))
        self.start_patch()
        self._apply_start_stats()
        self._apply_start_class()
        self._apply_progress()
        if self._outbox_task is None or self._outbox_task.done():
            self._outbox_task = asyncio.ensure_future(self._outbox_loop())

    # ---- the game's files ----------------------------------------------------------------------------------------------
    def path_lines(self) -> typing.List[str]:
        """The /k2_paths report: where everything is and whether it is in order."""
        saved = os.path.join(self.link.directory, "game_dir.txt")
        game = find_game_dir(self.game_dir_arg, saved)
        config = self.config_path or os.path.join(os.path.dirname(os.path.abspath(self.link.directory)), "config.txt")
        return path_report(game, self.link.directory, config, self.payload_dir)

    def make_patcher(self) -> typing.Optional[Patcher]:
        saved = os.path.join(self.link.directory, "game_dir.txt")
        found = find_game_dir(self.game_dir_arg, saved)
        if found is None:
            return None
        try:
            with open(saved, "w") as f:
                f.write(found)
        except OSError:
            pass
        return Patcher(found, self.link.directory, config_path=self.config_path)

    def _config(self, plan: typing.Optional[dict], unlocked: typing.Set[str]) -> typing.List[str]:
        """The marked block of config.txt: the seed's switches, the crafting flags and the extras' disguise rows."""
        return config_lines(self.slot_data) + flag_lines(plan, unlocked) + list(self._look_lines)

    def start_patch(self) -> None:
        """Run the patch in a worker thread: it reads and rewrites dozens of game files and takes about a minute, and the window must stay usable meanwhile."""
        logger.info("KOTOR 2: patching the game files; this takes about a minute the first time, the window stays usable.")
        self._patch_task = asyncio.ensure_future(self._patch_in_thread())

    async def _patch_in_thread(self) -> None:
        try:
            await asyncio.get_event_loop().run_in_executor(None, self.patch_game)           # patch_game reports its own result
        except Exception:
            logger.exception("KOTOR 2: the patch failed")

    async def wait_patch(self) -> None:
        """Wait for a patch that is running (items are delivered, and crafting rewritten, only after it)."""
        task = self._patch_task
        if task is not None and not task.done():
            await asyncio.shield(task)

    def patch_game(self, force: bool = False) -> str:
        """Write the seed's data files and the shipped payload into Override. Returns the line to show the player. One patch at a time (a reconnect waits).
        While the game is running nothing is changed unless `force` (the /k2_patch command): the game's module files must not be rewritten under it."""
        with self._patch_lock:
            return self._patch_game(force)

    def _patch_game(self, force: bool = False) -> str:
        patcher = self.make_patcher()
        started = time.time()
        if patcher is None:
            text = ("KOTOR 2: the game folder was not found, so the seed's files were NOT written. Type /k2_patch <game folder> "
                    "(the folder that contains swkotor2.exe).")
        elif not force and patcher._running():
            text = ("KOTOR 2: the game is running, so its files were NOT changed (rewriting them while it runs can crash it). If you have patched this seed before "
                    "you can play on. For a new seed, close the game and type /k2_patch.")
        else:
            files = payload_files(self.payload_dir)
            files.update(seed_files(self.slot_data))
            try:
                files.update(asset_files(console=bool(self.slot_data.get("crafting_plan"))))         # the message box and, with crafting, the Crafting Console
            except Exception as e:
                logger.warning("KOTOR 2: the game assets could not be built: %s" % e)
            problems: typing.List[str] = []
            try:
                # the journal quests the gates and the tracker use: texts in dialog.tlk (backed up first) and the journal file for Override
                built, journal_problems = journal_files(patcher.game_dir, os.path.dirname(patcher.manifest_path), patcher.backup, patcher._running())
                files.update(built)
                problems += journal_problems
            except Exception as e:
                problems.append("the Archipelago journal could not be built: %s" % e)
            extras = self.slot_data.get("extras") or []
            self._look_lines = look_lines(extras, lambda e: k1_assets_in(patcher.override, e))        # the disguises the dispatcher's tick applies to the extras
            if extras:
                try:
                    built, problems = build_templates(patcher.game_dir, extras, lambda e: k1_assets_in(patcher.override, e))
                    files.update(built)
                except Exception as e:                                  # pykotor missing or the game files unreadable: the rest of the patch still goes ahead
                    problems = ["the extra companions' creature templates could not be built: %s" % e]
            droids = {k: v for k, v in (self.slot_data.get("companion_classes") or {}).items() if v.get("look")}
            if droids:
                try:
                    built, droid_problems = build_droid_templates(patcher.game_dir, droids)
                    files.update(built)
                    problems += droid_problems
                except Exception as e:
                    problems.append("the droid companions' templates could not be built: %s" % e)
            # module files first go back to the game's own, then this seed's edits are made (a module is never edited twice, a seed never inherits another's)
            restored, left_alone = patcher.restore_modules()
            problems += ["a module file was changed by something else since the last patch and was left alone: %s" % name for name in left_alone]
            if self.slot_data.get("loot_plan"):                          # before the Bazaar tokens: their container copies are made from the templates as they are then
                try:
                    changed, loot_problems = loot_files(patcher.module_store(), self.slot_data["loot_plan"])
                    problems += loot_problems
                    logger.info("KOTOR 2: the loot randomizer changed %d container and creature templates." % changed)
                except Exception as e:
                    problems.append("the loot randomizer could not change the game's loot: %s" % e)
            if self.slot_data.get("options", {}).get("story_gates", True):
                try:
                    active = {"NAR3", "DXN3", "DAN2"} - set(self.slot_data.get("disabled_gates", []))
                    nodes, dlg_problems = master_dialogue_files(patcher.module_store(), active)
                    problems += dlg_problems
                    logger.info("KOTOR 2: the Master gates changed %d dialogue nodes." % nodes)
                except Exception as e:
                    problems.append("the Master gates could not patch the Masters' conversations: %s" % e)
            if self.slot_data.get("door_plan"):
                try:
                    written, door_problems = door_files(patcher.module_store(), self.slot_data["door_plan"])
                    problems += door_problems
                    logger.info("KOTOR 2: the area randomizer re-linked %d doors." % written)
                except Exception as e:
                    problems.append("the area randomizer could not re-link the game's doors: %s" % e)
            if self.slot_data.get("enemy_plan"):
                try:
                    built, added, enemy_problems = enemy_files(patcher.game_dir, patcher.module_store(), self.slot_data["enemy_plan"])
                    files.update(built)
                    problems += enemy_problems
                    logger.info("KOTOR 2: the enemy randomizer added %d creatures." % added)
                except Exception as e:
                    problems.append("the enemy randomizer could not add creatures to the game's areas: %s" % e)
            if self.slot_data.get("options", {}).get("bazaar"):
                try:
                    built, bz_problems = build_bazaar_files(patcher.game_dir)
                    files.update(built)
                    problems += bz_problems
                except Exception as e:
                    problems.append("the Bazaar's files could not be built: %s" % e)
                try:
                    built, bz_problems = token_files(patcher.game_dir, patcher.module_store(), str(self.seed_name or "seed"))
                    files.update(built)
                    problems += bz_problems
                except Exception as e:
                    problems.append("the Bazaar tokens could not be placed in the game's modules: %s" % e)
            if self.slot_data.get("options", {}).get("archipelago_vendor"):
                try:
                    built, vendor_problems = build_vendor_files(patcher.game_dir)
                    files.update(built)
                    problems += vendor_problems
                except Exception as e:
                    problems.append("the Archipelago Vendor's files could not be built: %s" % e)
            if self.slot_data.get("shop_plan"):
                try:
                    built, shop_problems = shop_files(patcher.module_store(), self.slot_data["shop_plan"])
                    files.update(built)
                    problems += shop_problems
                except Exception as e:
                    problems.append("the shop randomizer could not change the game's stores: %s" % e)
            plan = self.slot_data.get("crafting_plan")
            unlocked = self._craft_unlocked()
            received = self._gear_received()
            if plan:
                try:
                    built, craft_problems = crafting_files(patcher.game_dir, plan, unlocked, received)
                    files.update(built)
                    problems += craft_problems
                except Exception as e:
                    problems.append("crafting mode could not build its recipe table: %s" % e)
            self._craft_applied = self._craft_state(plan, unlocked, received)
            self._patch_files = dict(files)
            for problem in problems:
                logger.warning("KOTOR 2: %s" % problem)
            result = patcher.apply(files, config=self._config(plan, unlocked))
            text = result.summary()
            self.recorder and self.recorder.write("patch", created=result.created, changed=result.changed, removed=result.removed,
                                                  errors=result.errors)
            if result.errors or problems:
                text += " FINISHED WITH PROBLEMS (%d): see the warnings above." % (len(result.errors) + len(problems))
            else:
                text += " Finished in %d seconds: the game files are ready, you can start the game now." % round(time.time() - started)
        self.last_patch = text
        logger.info(text)
        return text

    async def server_auth(self, password_requested: bool = False):
        if password_requested and not self.password:
            await super().server_auth(password_requested)
        await self.get_username()
        await self.send_connect()

    # ---- items to jobs -------------------------------------------------------------------------------------------------
    def _save_state(self) -> None:
        if not self._state_path:
            return
        try:
            with open(self._state_path, "w") as f:
                json.dump({"state_version": 2, "delivered": self.delivered, "paid_checks": self.paid_checks, "unlocked": self.unlocked, "tracker_sent": self.tracker_sent,
                           "start_class_sent": self.start_class_sent, "start_stats_sent": self.start_stats_sent, "extras_given": sorted(self.extras_given),
                           "prestige_pending": self.prestige_pending, "dispatcher": self.dispatcher.export_state(), "failed": self._failed}, f)
        except OSError:
            pass

    # ---- crafting unlocks ------------------------------------------------------------------------------------------------------
    def _craft_unlocked(self) -> typing.Set[str]:
        """The crafting types whose item has been received ("Crafting: Armor and Robes" and so on), counting items from before a restart."""
        out: typing.Set[str] = set()
        for item in self.items_received:
            data = ITEMS.get(self.item_names.lookup_in_game(item.item, self.game))
            if data is not None and data.arm.startswith("craft:"):
                out.add(data.arm[len("craft:"):])
        return out

    def _gear_received(self) -> typing.Set[str]:
        """The gear items received, by template name."""
        out: typing.Set[str] = set()
        for item in self.items_received:
            data = ITEMS.get(self.item_names.lookup_in_game(item.item, self.game))
            if data is not None and data.arm.startswith("gear:"):
                out.add(data.arm[len("gear:"):])
        return out

    @staticmethod
    def _craft_state(plan: dict, unlocked: typing.Set[str], received: typing.Set[str]) -> tuple:
        """What the written table depends on: the unlocked types if the seed gates them, the gear items received if recipes arrive with their items."""
        return (frozenset(unlocked) if plan and plan.get("gated") else frozenset(), frozenset(received) if plan and plan.get("gear_gated") else frozenset())

    def _refresh_crafting(self) -> None:
        """Rewrites the recipe table and the console's switches when what they depend on has changed (a crafting type unlocked, a gear recipe arrived)."""
        plan = self.slot_data.get("crafting_plan")
        if not plan or not (plan.get("gated") or plan.get("gear_gated")) or self._patch_files is None:
            return
        unlocked, received = self._craft_unlocked(), self._gear_received()
        state = self._craft_state(plan, unlocked, received)
        if state == self._craft_applied:
            return
        patcher = self.make_patcher()
        if patcher is None:
            return
        try:
            built, problems = crafting_files(patcher.game_dir, plan, unlocked, received)
        except Exception as e:
            logger.warning("KOTOR 2: the recipe table could not be rebuilt: %s" % e)
            return
        for problem in problems:
            logger.warning("KOTOR 2: %s" % problem)
        self._patch_files.update(built)
        result = patcher.apply(self._patch_files, config=self._config(plan, unlocked))
        self._craft_applied = state
        self.recorder and self.recorder.write("crafting", unlocked=sorted(unlocked), recipes=len(received), errors=result.errors)
        logger.info("KOTOR 2: crafting unlocked: %s" % (", ".join(sorted(unlocked)) or "nothing"))

    def _material_yield(self, resref: str) -> int:
        """Components a gear item gives in crafting mode, read once from the game's templates (1 if they cannot be read)."""
        if self._yields is None:
            self._yields = {}
            patcher = self.make_patcher()
            plan = self.slot_data.get("crafting_plan")
            if patcher is not None and plan:
                try:
                    self._yields = material_yields(patcher.game_dir, plan)
                except Exception as e:
                    logger.warning("KOTOR 2: the Components for gear items could not be worked out: %s" % e)
        return max(1, int(self._yields.get(resref, 1)))

    def _refresh_held(self) -> None:
        """Tell the tracker what companion items we hold (the cult_leader goal counts them), including items from before a restart."""
        if self.tracker is None:
            return
        self.tracker.held = {}
        for item in self.items_received:
            name = self.item_names.lookup_in_game(item.item, self.game)
            if name.startswith(("Companion: ", "AP Companion")):
                self.tracker.held[name] = self.tracker.held.get(name, 0) + 1
        self.tracker._check_goal()

    async def _deliver_new_items(self) -> None:
        await self.wait_patch()
        self._refresh_held()
        self._refresh_crafting()
        await self._report_goal()
        while self.delivered < len(self.items_received):
            item = self.items_received[self.delivered]
            name = self.item_names.lookup_in_game(item.item, self.game)
            data = ITEMS.get(name)
            index = self.delivered
            self.delivered += 1
            if data is None:
                logger.warning("KOTOR 2: no delivery known for item %r" % name)
                continue
            if data.arm in QUIET_ARMS:
                continue
            action, args = arm_to_job(data.arm, self.amounts)
            if data.arm.startswith("vendorpass:"):
                action, args = "pass", data.arm[len("vendorpass:"):]               # a plot item that shows the menu of that name on the Vendor
            if data.arm.startswith("companionprestige:"):
                # the item only marks the companion; the class order follows from the CC report once they are level 15
                if self.planner is not None:
                    self.planner.prestige_slots = self._prestige_slots()
                self.recorder and self.recorder.write("item", index=index, name=name, arm=data.arm)
                self._plan_companions()
                continue
            if data.arm.startswith("craft:"):
                # the table and the switches were rewritten above from the items held; the game only shows the player a message
                self.recorder and self.recorder.write("item", index=index, name=name, arm=data.arm)
                self.dispatcher.submit("notify", "", message=RECEIPT_PREFIX + name, index=index, item_name=name)
                continue
            if data.arm.startswith("gear:"):
                resref = data.arm[len("gear:"):]
                self.recorder and self.recorder.write("item", index=index, name=name, arm=data.arm)
                plan = self.slot_data.get("crafting_plan")
                if plan and plan.get("mode"):
                    # crafting mode: the recipe was added to the table above; the item gives Components worth a tenth of its build cost
                    amount = self._material_yield(resref)
                    self.dispatcher.submit("materials", str(amount), message=RECEIPT_PREFIX + "%s (recipe unlocked, %d Components)" % (name, amount),
                                           index=index, item_name=name)
                else:
                    self.dispatcher.submit("gear", resref, message=RECEIPT_PREFIX + name, index=index, item_name=name)
                continue
            if data.arm.startswith(("companion:", "extracompanion:", "apcompanion")):
                job = self._companion_item_job(name)
                if job is None:
                    logger.warning("KOTOR 2: %s cannot be delivered: it is not in this seed's plan." % name)
                    continue
                action, args = job
            if action == "prestige":
                # the vanilla prestige offer needs level 15; the item waits for it (a class added earlier would also lift the XP to the next level)
                if self.game_level < PRESTIGE_LEVEL:
                    self.prestige_pending = True
                    self.recorder and self.recorder.write("prestige_waiting", level=self.game_level)
                    continue
                args = self._prestige_args()
            if action == "xp" and self.xp_clamp_active():
                action, args = "set_xp", str(self.expected_xp())          # absolute: the total the seed entitles, counting this item
            self.recorder and self.recorder.write("item", index=index, name=name, arm=data.arm)
            self.dispatcher.submit(action, args, message=RECEIPT_PREFIX + name, index=index, item_name=name)
        self._save_state()

    # ---- the experience clamp ------------------------------------------------------------------------------------------------
    # With experience_mode ap_limited or ap_gated the XP a player has is exactly what the seed entitles: the limiter times the checks done, or the
    # amount times the Experience Points items received. The client sets that total in the game (an absolute value, so replays and repeats cannot
    # add up) whenever it grows, and again at every area change when the game's own total has drifted (kills and quests give XP of their own).
    def xp_clamp_active(self) -> bool:
        return int(self.slot_data.get("options", {}).get("experience_mode", 0)) in (MODE_LIMITED, MODE_GATED)

    def expected_xp(self) -> int:
        options = self.slot_data.get("options", {})
        if int(options.get("experience_mode", 0)) == MODE_LIMITED:
            return self.paid_checks * int(options.get("experience_limiter", 1000))
        count = 0
        for item in self.items_received[:self.delivered]:
            data = ITEMS.get(self.item_names.lookup_in_game(item.item, self.game))
            if data is not None and data.arm == "xp":
                count += 1
        return count * int(options.get("experience_item", DEFAULT_AMOUNTS["xp"]))

    def _on_area_entered(self) -> None:
        """At an area change: put the game's XP back to the entitled total when it has drifted and nothing is still on its way to the game."""
        if not self.xp_clamp_active() or self.game_xp is None:
            return
        if self.dispatcher._queue or self.dispatcher.current:
            self._xp_recheck = True                  # still delivering: look again when the dispatcher is idle
            return
        want = self.expected_xp()
        if self.game_xp != want:
            self.recorder and self.recorder.write("xp_clamp", game=self.game_xp, expected=want)
            self.dispatcher.submit("set_xp", str(want), message="")
            self.game_xp = want

    def _companion_item_job(self, item_name: str) -> typing.Optional[typing.Tuple[str, str]]:
        """The dispatcher job for a companion item: a story companion's slot, or an extra companion's slot and template (from the seed's plan)."""
        job = companion_job(item_name)
        if job is not None:
            return job
        entry = extra_for_item(self.slot_data.get("extras") or [], item_name, self.extras_given)
        if entry is None:
            return None
        self.extras_given.add(entry["slot"])
        return "extracompanion", "%d:%s" % (entry["slot"], template_name(entry["slot"]))

    def _prestige_slots(self) -> typing.Set[int]:
        """Slots whose Companion Prestige item has arrived (from every item received, so right after a restart too)."""
        out = set()
        for item in self.items_received:
            name = self.item_names.lookup_in_game(item.item, self.game)
            if name.startswith("Companion Prestige: "):
                who = name.partition(": ")[2]
                if who in BASE_COMPANIONS:
                    out.add(BASE_COMPANIONS.index(who))
        return out

    def _plan_companions(self) -> None:
        """Order the class changes the plan wants for the companions in the party (client/k2_companions.py). One order per slot and state: an order that did
        not change what the game reports is tried once more and then left."""
        if self.planner is None or not self.planner.active() or not self.party_info or self.game_level <= 0:
            return
        queued = {(j.action, j.args) for j in list(self.dispatcher._queue) + ([self.dispatcher.current] if self.dispatcher.current else [])}
        for slot, args in self.planner.orders(self.party_info, self.game_level, self.game_alignment):
            if ("compclass", args) in queued:
                continue
            info = self.party_info[slot]
            last = self._comp_attempts.get(slot)
            tries = last[2] + 1 if last and last[0] == info and last[1] == args else 1
            if tries > 2:
                continue
            self._comp_attempts[slot] = (info, args, tries)
            self.recorder and self.recorder.write("compclass_order", slot=slot, args=args, tries=tries, info=list(info))
            self.dispatcher.submit("compclass", args, message="", item_name="CompanionClass")

    def _prestige_args(self) -> str:
        return "%d:%d" % tuple(self.slot_data.get("prestige_pair") or (11, 14))        # [light, dark]; the game picks the side from the alignment

    def _release_prestige(self) -> None:
        if self.prestige_pending and self.game_level >= PRESTIGE_LEVEL:
            self.prestige_pending = False
            self.recorder and self.recorder.write("prestige_released", level=self.game_level)
            self.dispatcher.submit("prestige", self._prestige_args(), message=RECEIPT_PREFIX + "Prestige Class", item_name="Prestige Class")
            self._save_state()

    def _apply_start_stats(self) -> None:
        """Orders the random starting stats once per seed, before the class (the class rebuild reads the constitution for the hit points)."""
        stats = self.slot_data.get("start_stats")
        if not stats or self.start_stats_sent:
            return
        self.start_stats_sent = True
        self.recorder and self.recorder.write("start_stats", stats=stats)
        self.dispatcher.submit("stats", ":".join(str(int(v)) for v in stats), message="Your abilities and skills have been set.", item_name="StartStats")
        self._save_state()

    def _apply_start_class(self) -> None:
        """Orders the starting class conversion once per seed (the game runs the class rebuild at a calm moment, on the character as it is then)."""
        start = self.slot_data.get("start_class")
        if not start or self.start_class_sent:
            return
        self.start_class_sent = True
        self.recorder and self.recorder.write("start_class", **start)
        # kind 0 = convert the class in position 0; level 0 = the level it has now
        args = "0:%d:0:0:%d:%d:%d" % (start["class"], start["mode"], start.get("race", 0), start.get("look", 0))
        self.dispatcher.submit("class", args, message="Your class is being rebuilt.", item_name="StartClass")
        self._save_state()

    def _apply_progress(self) -> None:
        """The ap_limited modes: XP and credits per completed check, and companions unlocked by the share of checks done."""
        if self.tracker is None:
            return
        options = self.slot_data.get("options", {})
        total = len(self.tracker.checked)
        stage = tracker_stage(total, len(self.tracker.locations))
        if stage > self.tracker_sent:
            # the Archipelago Tracker quest in the journal; the stage only moves forward, so a repeat does no harm
            self.tracker_sent = stage
            self.recorder and self.recorder.write("tracker", stage=stage, checked=total)
            self.dispatcher.submit("tracker", str(stage), message="")
        delta = total - self.paid_checks
        if delta > 0:
            self.paid_checks = total
            if options.get("experience_mode") == MODE_LIMITED:
                self.dispatcher.submit("set_xp", str(self.expected_xp()), message="Experience for %d new checks" % delta)
            if options.get("credit_mode") == MODE_LIMITED:
                amount = delta * int(options.get("credit_limiter", 100))
                self.dispatcher.submit("credits", str(amount), message="Credits for %d new checks" % delta)
        order = self.slot_data.get("companion_unlock_order") or []
        if order and options.get("companions") == COMPANIONS_AP_LIMITED and self.tracker.locations:
            percent = 100.0 * total / len(self.tracker.locations)
            due = min(len(order), int(percent // max(1, int(options.get("companion_unlock_step", 5)))))
            while self.unlocked < due:
                name = order[self.unlocked]
                data = ITEMS.get(name)
                self.unlocked += 1
                if data is None:
                    continue
                action, args = arm_to_job(data.arm, self.amounts)
                job = self._companion_item_job(name)
                if job is None:
                    continue
                action, args = job
                self.recorder and self.recorder.write("unlock", index=self.unlocked, name=name, arm=data.arm)
                self.dispatcher.submit(action, args, message="Companion unlocked: " + name.partition(": ")[2], item_name=name)
        self._save_state()

    async def _send_death(self) -> None:
        if "DeathLink" not in self.tags:
            return
        self.recorder and self.recorder.write("deathlink_out")
        await self.send_death("%s died in KOTOR 2." % (self.player_names.get(self.slot, "A player"),))

    async def _report_goal(self) -> None:
        if self.tracker is not None and self.tracker.victory and not self.finished_game:
            self.finished_game = True
            self.recorder and self.recorder.write("victory")
            await self.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])

    def _on_job_applied(self, job: Job) -> None:
        self.recorder and self.recorder.write("applied", seq=job.seq, action=job.action, args=job.args, item=job.item_name)
        self._save_state()                                  # the ledger and the list of jobs still to do change with every applied job
        if job.action == "trap" and (job.item_name or "").startswith("Trap: "):          # a real trap item; linked traps are named "TrapLink"
            asyncio.ensure_future(self._send_trap_link(job.item_name))

    def _on_job_failure(self, job: Job, reason: str) -> None:
        logger.warning("KOTOR 2: could not deliver %s: %s" % (job.item_name or job.text, reason))
        self.recorder and self.recorder.write("failed", action=job.action, args=job.args, item=job.item_name, reason=reason)
        if job.action == "tracker":
            self.tracker_sent = 0                      # the stage never reached the game: the next check sends it again
        else:
            self._failed.append({"action": job.action, "args": job.args, "message": job.message_full, "index": job.index, "item_name": job.item_name})
        self._save_state()

    def _requeue_failed(self) -> None:
        """The game has just reported its state, so it is running: the jobs it did not answer earlier (it was closed or had crashed) are sent now, in their order."""
        again, self._failed = self._failed, []
        for job in again:
            self.dispatcher.submit(job["action"], job["args"], message=job.get("message", ""), index=int(job.get("index", -1)), item_name=job.get("item_name", ""))
        if again:
            logger.info("KOTOR 2: the game is back: %d job(s) it had not answered are sent again." % len(again))
            self._save_state()

    # ---- game lines to checks ------------------------------------------------------------------------------------------------
    async def _outbox_loop(self) -> None:
        while not self.exit_event.is_set():
            try:
                await self._process_outbox()
            except Exception:
                logger.exception("KOTOR 2: error while reading the game's report")
            if self._xp_recheck and not (self.dispatcher._queue or self.dispatcher.current):
                self._xp_recheck = False
                self._on_area_entered()
            await asyncio.sleep(0.5)

    async def _process_outbox(self) -> None:
        # The outbox keeps what the game wrote before this client started. That history is read for the state it reports (levels, quests, areas: the checks reached while
        # the client was away), but it must not drive the dispatcher or the deaths: an old "D|1" would complete a job that was sent again and has not been applied, and an old
        # "DL|death" would kill the player again. Of the history only the last job-number report (T) goes to the dispatcher, so it knows where the game stood.
        history = not self._outbox_started
        self._outbox_started = True
        last_report = None
        for line in self.link.read_new():
            if not history:
                self.recorder and self.recorder.write("game", line=line)
                self.dispatcher.on_event(line)
            elif line.startswith("T|"):
                last_report = line
            if line == "DL|death":
                if not history:
                    await self._send_death()
                continue
            if line.startswith(("WT|", "GB|", "GP|")) and not history:
                logger.info("KOTOR 2 wrapper: %s" % line)          # what the game-side wrappers did (gates, skips, the locker guard)
            if line.startswith("T|") and self._failed and not history:
                self._requeue_failed()
            if line.startswith("V|"):
                self.current_module = line[2:].strip().upper()
            if line.startswith("IT|"):
                if self.item_log is None:
                    self.item_log = ItemLog(os.path.join(self.link.directory, "items_seen.csv"))
                self.item_log.update(ItemLog.parse(line[3:]), self.current_module)
                continue
            if line.startswith("CC|"):
                self.party_info = parse_cc(line[3:])
                self._plan_companions()
            if line.startswith("A|"):
                try:
                    self.game_alignment = int(line[2:])
                except ValueError:
                    pass
            if line.startswith("L|"):
                try:
                    self.game_level = int(line[2:])
                except ValueError:
                    pass
                self._release_prestige()
                self._plan_companions()
            if line.startswith("XP|"):
                try:
                    self.game_xp = int(line[3:])
                except ValueError:
                    pass
                continue
            if line.startswith("V|"):
                self._on_area_entered()
            if self.tracker is None:
                continue
            new = self.tracker.handle(line)
            if new:
                names = [self.tracker.locations[i]["name"] for i in sorted(new)]
                self.recorder and self.recorder.write("checks", locations=names)
                logger.info("KOTOR 2: new checks: %s" % ", ".join(names))
                await self.send_msgs([{"cmd": "LocationChecks", "locations": sorted(new)}])
                self._apply_progress()
            await self._report_goal()
        if last_report is not None:
            self.dispatcher.on_event(last_report)


def launch():
    import colorama

    async def main(args):
        ctx = KotorTwoContext(args.connect, args.password, game_dir=args.game_dir, payload_dir=args.payload_dir)
        if args.name:
            ctx.username = args.name
        ctx.server_task = asyncio.create_task(server_loop(ctx), name="server loop")
        if gui_enabled:
            ctx.run_gui()
        ctx.run_cli()
        await ctx.exit_event.wait()
        ctx.server_address = None
        await ctx.shutdown()

    parser = get_base_parser(description="KOTOR 2 Archipelago client (draft).")
    parser.add_argument("--name", default=None, help="Slot name to connect as.")
    parser.add_argument("--game-dir", default=None, help="The KOTOR 2 folder (the one with swkotor2.exe). Found automatically when omitted.")
    parser.add_argument("--payload-dir", default=None, help="Folder of shipped game files to install with the seed's files (default: payload next to the client).")
    args, _rest = parser.parse_known_args()
    colorama.init()
    asyncio.run(main(args))
    colorama.deinit()


if __name__ == "__main__":
    launch()
