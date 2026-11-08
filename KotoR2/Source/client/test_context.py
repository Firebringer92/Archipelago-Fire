"""Smoke test of the whole client with a fake server and a fake game.
Run through tools/run_client_tests.py (it puts the scratch Archipelago core, with the K2 world, on the path)."""
import asyncio
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from NetUtils import NetworkItem  # noqa: E402
from fake_game import FakeGame  # noqa: E402
from k2_dispatcher import Job  # noqa: E402
import KotorTwoClient as K  # noqa: E402
from worlds.kotor2.Items import ITEMS, ITEM_NAME_TO_ID  # noqa: E402

DATA = json.load(open(os.path.join(HERE, "..", "data", "locations.json")))
LOCS = {str(l["id"]): {k: v for k, v in l.items() if k not in ("id", "requires", "progression", "only_if_option")} for l in DATA["locations"]}
BY_NAME = {l["name"]: l["id"] for l in DATA["locations"]}


class Names:
    def lookup_in_game(self, code, game=None):
        return {v: k for k, v in ITEM_NAME_TO_ID.items()}[code]


class TestContext(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def quiet_patcher(ctx):
        real = ctx.make_patcher

        def make():
            patcher = real()
            if patcher is not None:
                patcher._running = lambda: False
            return patcher
        return make

    async def asyncSetUp(self):
        self.dir = tempfile.mkdtemp()
        self.game_dir = os.path.join(self.dir, "game")        # a stand-in game folder: the tests must never write into the real one
        os.makedirs(self.game_dir)
        open(os.path.join(self.game_dir, "swkotor2.exe"), "wb").close()
        self.ctx = K.KotorTwoContext(None, None, link_dir=self.dir, game_dir=self.game_dir, payload_dir=os.path.join(self.dir, "none"),
                                  config_path=os.path.join(self.dir, "config.txt"))
        self.ctx.seed_name, self.ctx.slot = "seedx", 1
        self.ctx.item_names = Names()
        self.ctx.make_patcher = self.quiet_patcher(self.ctx)        # whether the real game is running on this machine must not change the tests
        self.sent = []

        async def fake_send(msgs):
            self.sent.extend(msgs)
        self.ctx.send_msgs = fake_send
        self.ctx.dispatcher.RESEND_AFTER = 0.5
        self.ctx.dispatcher.LEARN_WAIT = 1.0
        self.game = FakeGame(self.ctx.link)
        self.stop = False
        self.task = asyncio.ensure_future(self.run_game())
        self.ctx._on_connected({"slot_data": {"locations": LOCS, "seed_guard": 7, "options": {}}})
        await self.ctx.wait_patch()

    async def asyncTearDown(self):
        await self.ctx.wait_patch()
        self.stop = True
        await self.task
        self.ctx.exit_event.set()
        await asyncio.sleep(0.6)
        shutil.rmtree(self.dir, ignore_errors=True)

    async def run_game(self):
        while not self.stop:
            self.game.poll()
            await asyncio.sleep(0.03)

    async def test_items_become_jobs_and_checks_are_sent(self):
        names = ["Republic Credits", "Skill: Stealth", "Trap: Lose Credits", "Experience Points"]
        for n in names:
            self.ctx.items_received.append(NetworkItem(ITEM_NAME_TO_ID[n], 0, 1, 0))
        await self.ctx._deliver_new_items()
        await self.wait_effects(4)
        self.assertEqual([e[1] for e in self.game.effects], ["credits", "skill", "trap", "xp"])
        self.assertEqual(self.game.effects[1][2], "stealth")
        self.assertEqual(self.ctx.delivered, 4)
        # game reports: entering 102PER and reaching level 3
        self.game._put("V|102PER")
        self.game._put("L|3")
        for _ in range(40):
            await asyncio.sleep(0.1)
            if self.sent:
                break
        locs = set()
        for m in self.sent:
            if m["cmd"] == "LocationChecks":
                locs |= set(m["locations"])
        self.assertIn(BY_NAME["Visited: Peragus - Mining Tunnels"], locs)
        self.assertIn(BY_NAME["Level 3"], locs)

    async def test_victory_sends_goal(self):
        self.game._put("X|victory")
        for _ in range(40):
            await asyncio.sleep(0.1)
            if any(m["cmd"] == "StatusUpdate" for m in self.sent):
                break
        self.assertTrue(any(m["cmd"] == "StatusUpdate" for m in self.sent))

    async def test_limited_modes_pay_per_check_and_unlock_companions(self):
        slot = {"locations": LOCS, "seed_guard": 7,
                "options": {"experience_mode": 1, "experience_limiter": 700, "credit_mode": 1, "credit_limiter": 50, "companions": 3,
                            "companion_unlock_step": 1},
                "companion_unlock_order": ["Companion: Atton Rand", "Companion: Bao-Dur"]}
        self.ctx.paid_checks = self.ctx.unlocked = 0
        self.ctx._on_connected({"slot_data": slot})
        self.game._put("V|102PER")
        self.game._put("L|4")                      # four checks: the area and levels 2, 3 and 4
        for _ in range(60):
            await asyncio.sleep(0.1)
            if self.ctx.unlocked == 1 and self.ctx.paid_checks == 4:
                break
        self.assertEqual(self.ctx.paid_checks, 4)
        self.assertEqual(self.ctx.unlocked, 1)     # 4 of about 309 checks is 1.3 percent: one unlock at a 1 percent step
        total = lambda action: sum(int(e[2]) for e in self.game.effects if e[1] == action)   # the checks may arrive in one or two reports
        last_xp = lambda: [int(e[2]) for e in self.game.effects if e[1] == "set_xp"][-1:]
        for _ in range(60):
            await asyncio.sleep(0.1)
            if last_xp() == [2800] and total("credits") >= 200:
                break
        self.assertEqual(last_xp(), [2800])          # absolute totals: 700 per check, four checks
        self.assertEqual(total("credits"), 200)
        self.assertEqual(total("xp"), 0)             # no additive XP job in the clamped modes

    async def test_delivery_state_survives_restart(self):
        self.ctx.items_received.append(NetworkItem(ITEM_NAME_TO_ID["Republic Credits"], 0, 1, 0))
        await self.ctx._deliver_new_items()
        again = K.KotorTwoContext(None, None, link_dir=self.dir, game_dir=self.game_dir, payload_dir=os.path.join(self.dir, "none"),
                                  config_path=os.path.join(self.dir, "config.txt"))
        again.seed_name, again.slot = "seedx", 1
        again._on_connected({"slot_data": {"locations": LOCS, "seed_guard": 7}})
        self.assertEqual(again.delivered, 1)
        again.exit_event.set()

    async def wait_effects(self, n):
        for _ in range(100):
            await asyncio.sleep(0.1)
            if len(self.game.effects) >= n:
                break

    async def test_gated_experience_is_an_absolute_total_and_drift_is_corrected_at_area_changes(self):
        self.ctx.slot_data["options"] = {"experience_mode": 2, "experience_item": 8000}
        self.ctx.amounts["xp"] = "8000"
        for _ in range(2):
            self.ctx.items_received.append(NetworkItem(ITEM_NAME_TO_ID["Experience Points"], 0, 1, 0))
        await self.ctx._deliver_new_items()
        await self.wait_effects(2)
        self.assertEqual([(e[1], e[2]) for e in self.game.effects], [("set_xp", "8000"), ("set_xp", "16000")])
        # the game reports more XP than the seed entitles (kills and quests), then the player enters an area
        self.game._put("XP|21000")
        self.game._put("V|201TEL")
        await self.wait_effects(3)
        self.assertEqual(self.game.effects[-1][1:], ("set_xp", "16000"))
        # the same total: nothing more is sent
        self.game._put("XP|16000")
        self.game._put("V|202TEL")
        await asyncio.sleep(1.0)
        self.assertEqual(len(self.game.effects), 3)

    async def test_the_item_log_is_written_from_the_games_item_reports(self):
        self.game._put("V|101PER")
        self.game._put("IT|Comlink~Comlink,c1_key~Apartment C1 Passkey")
        path = os.path.join(self.dir, "items_seen.csv")
        for _ in range(40):
            await asyncio.sleep(0.1)
            if os.path.exists(path):
                break
        with open(path) as f:
            text = f.read()
        self.assertIn("Comlink,Comlink,101PER", text)
        self.assertIn("c1_key,Apartment C1 Passkey,101PER", text)

    async def test_the_starting_class_is_ordered_once(self):
        slot = {"locations": LOCS, "seed_guard": 7, "options": {}, "start_class": {"class": 1, "mode": 1}}
        self.ctx._on_connected({"slot_data": slot})
        await self.wait_effects(1)
        self.assertEqual([(e[1], e[2]) for e in self.game.effects], [("class", "0:1:0:0:1:0:0")])
        self.assertTrue(self.ctx.start_class_sent)
        self.ctx._on_connected({"slot_data": slot})              # a reconnect does not order it again
        await asyncio.sleep(1.0)
        self.assertEqual(len(self.game.effects), 1)

    async def test_a_droid_start_carries_the_race(self):
        slot = {"locations": LOCS, "seed_guard": 7, "options": {}, "start_class": {"class": 6, "mode": 1, "race": 5, "look": 66}}
        self.ctx._on_connected({"slot_data": slot})
        await self.wait_effects(1)
        self.assertEqual([(e[1], e[2]) for e in self.game.effects], [("class", "0:6:0:0:1:5:66")])

    async def test_random_starting_stats_are_ordered_once_before_the_class(self):
        stats = [12, 14, 8, 10, 19, 3, 1, 2, 3, 4, 5, 6, 7, 20]
        slot = {"locations": LOCS, "seed_guard": 7, "options": {}, "start_stats": stats, "start_class": {"class": 0, "mode": 1}}
        self.ctx._on_connected({"slot_data": slot})
        await self.wait_effects(2)
        self.assertEqual([(e[1], e[2]) for e in self.game.effects],
                         [("stats", "12:14:8:10:19:3:1:2:3:4:5:6:7:20"), ("class", "0:0:0:0:1:0:0")])
        self.assertTrue(self.ctx.start_stats_sent)

    async def test_a_companion_item_unlocks_the_slot_and_extras_are_skipped(self):
        for n in ("Companion: Kreia", "Companion: Bastila Shan", "Companion: Bao-Dur"):
            self.ctx.items_received.append(NetworkItem(ITEM_NAME_TO_ID[n], 0, 1, 0))
        await self.ctx._deliver_new_items()
        await self.wait_effects(2)
        await asyncio.sleep(0.5)
        self.assertEqual([(e[1], e[2]) for e in self.game.effects], [("companion", "6"), ("companion", "1")])     # the extra companion is not built: no job
        self.assertEqual(self.ctx.delivered, 3)

    async def test_the_cc_report_leads_to_a_companion_class_order(self):
        slot = {"locations": LOCS, "seed_guard": 7, "options": {}, "companion_classes": {"0": {"class": 3, "mode": 0}}}
        self.ctx._on_connected({"slot_data": slot})
        self.game._put("L|12")
        self.game._put("CC|0:0:2:255:0")
        await self.wait_effects(1)
        self.assertEqual([(e[1], e[2]) for e in self.game.effects], [("compclass", "0:0:3:12:0:0:0")])
        # the same report again does not order it twice while the first order is the same state: at most one retry
        self.game._put("CC|0:3:12:255:0")
        await asyncio.sleep(1.0)
        self.assertEqual(len(self.game.effects), 1)               # the game reports the class as right: nothing more

    async def test_a_companion_prestige_item_marks_the_slot_and_the_order_follows_at_fifteen(self):
        slot = {"locations": LOCS, "seed_guard": 7, "options": {}, "companion_prestige_pairs": {"6": [13, 16]}}
        self.ctx._on_connected({"slot_data": slot})
        self.ctx.items_received.append(NetworkItem(ITEM_NAME_TO_ID["Companion Prestige: Kreia"], 0, 1, 0))
        self.game._put("A|90")
        self.game._put("L|16")
        self.game._put("CC|6:4:16:255:0")
        await asyncio.sleep(0.8)
        self.assertEqual(self.game.effects, [])                  # no item processed yet
        await self.ctx._deliver_new_items()
        await self.wait_effects(1)
        self.assertEqual([(e[1], e[2]) for e in self.game.effects], [("compclass", "6:1:13:1:0:0:0")])

    def extras_slot(self):
        plan = [{"slot": 12, "name": "Bastila Shan", "kind": "k1", "item": "Companion: Bastila Shan", "appearance": 4,
                 "portrait": 33, "gender": 1, "class": 5, "fallback_appearance": 30, "fallback_portrait": 1, "look_method": "disguise"},
                {"slot": 13, "name": "Exile", "kind": "ap", "item": "AP Companion", "appearance": 48, "portrait": 18,
                 "gender": 0, "class": 0, "fallback_appearance": 48, "fallback_portrait": 18, "look_method": "disguise"},
                {"slot": 14, "name": "Bob", "kind": "ap", "item": "AP Companion", "appearance": 47, "portrait": 1,
                 "gender": 1, "class": 1, "fallback_appearance": 47, "fallback_portrait": 1, "look_method": "template"}]
        return {"locations": LOCS, "seed_guard": 7, "options": {}, "extras": plan}

    async def test_extra_and_generated_companion_items_go_to_their_slots(self):
        self.ctx._on_connected({"slot_data": self.extras_slot()})
        for n in ("Companion: Bastila Shan", "AP Companion", "AP Companion", "Companion: Juhani"):
            self.ctx.items_received.append(NetworkItem(ITEM_NAME_TO_ID[n], 0, 1, 0))
        await self.ctx._deliver_new_items()
        await self.wait_effects(3)
        await asyncio.sleep(0.5)
        self.assertEqual([(e[1], e[2]) for e in self.game.effects],
                         [("extracompanion", "12:apxc12"), ("extracompanion", "13:apxc13"), ("extracompanion", "14:apxc14")])     # Juhani is not in the plan: no job
        self.assertEqual(self.ctx.extras_given, {12, 13, 14})

    async def test_a_slow_patch_does_not_block_the_event_loop_and_items_wait_for_it(self):
        import threading
        import time
        release = threading.Event()
        started = threading.Event()

        def slow():
            started.set()
            release.wait(10)
            return "slow patch done"
        self.ctx.patch_game = slow
        self.ctx.start_patch()
        for _ in range(100):
            if started.is_set():
                break
            await asyncio.sleep(0.02)
        self.assertTrue(started.is_set())
        ticks = 0
        end = time.time() + 0.5
        while time.time() < end:                       # the loop keeps running while the patch is stuck in its thread
            await asyncio.sleep(0.02)
            ticks += 1
        self.assertGreater(ticks, 10)
        self.ctx.items_received.append(NetworkItem(ITEM_NAME_TO_ID["Republic Credits"], 0, 1, 0))
        delivery = asyncio.ensure_future(self.ctx._deliver_new_items())
        await asyncio.sleep(0.5)
        self.assertFalse(delivery.done())              # items are delivered after the patch (crafting is rewritten from it)
        self.assertEqual(self.ctx.delivered, 0)
        release.set()
        await delivery
        self.assertEqual(self.ctx.delivered, 1)

    def another_client(self):
        again = K.KotorTwoContext(None, None, link_dir=self.dir, game_dir=self.game_dir, payload_dir=os.path.join(self.dir, "none"),
                                  config_path=os.path.join(self.dir, "config.txt"))
        again.seed_name, again.slot = "seedx", 1
        again.item_names = Names()
        again.make_patcher = self.quiet_patcher(again)
        again.dispatcher.RESEND_AFTER = 0.5
        again.dispatcher.LEARN_WAIT = 1.0

        async def fake_send(msgs):
            self.sent.extend(msgs)
        again.send_msgs = fake_send
        return again

    async def test_jobs_the_game_did_not_apply_survive_a_restart_of_the_client(self):
        self.game.calm = False                                   # the game is busy (or has crashed): nothing is applied
        for n in ("Republic Credits", "Skill: Stealth"):
            self.ctx.items_received.append(NetworkItem(ITEM_NAME_TO_ID[n], 0, 1, 0))
        await self.ctx._deliver_new_items()
        await asyncio.sleep(0.4)
        self.assertEqual(self.game.effects, [])
        self.assertEqual(self.ctx.delivered, 2)                  # counted as handed to the dispatcher, but not delivered
        self.ctx._save_state()
        self.ctx.exit_event.set()
        if self.ctx.dispatcher._task:
            self.ctx.dispatcher._task.cancel()                   # the client is gone
        self.game.calm = True
        again = self.another_client()
        again._on_connected({"slot_data": {"locations": LOCS, "seed_guard": 7, "options": {}}})
        await again.wait_patch()
        await self.wait_effects(2)
        self.assertEqual([(e[1]) for e in self.game.effects], ["credits", "skill"])           # sent again by the new client, once each
        await asyncio.sleep(0.6)
        self.assertEqual(len(self.game.effects), 2)
        again.exit_event.set()

    async def test_the_ledger_survives_a_restart_so_an_older_save_gets_its_items_back(self):
        for n in ("Republic Credits", "Skill: Stealth"):
            self.ctx.items_received.append(NetworkItem(ITEM_NAME_TO_ID[n], 0, 1, 0))
        await self.ctx._deliver_new_items()
        await self.wait_effects(2)
        self.game.save("early")                                  # a save made before the first item
        self.game.counter, self.game.effects = 0, []
        self.game.save("old")
        self.game.load("old")
        self.game.counter, self.game.effects = 0, []
        await asyncio.sleep(0.3)
        self.ctx.exit_event.set()
        if self.ctx.dispatcher._task:
            self.ctx.dispatcher._task.cancel()
        again = self.another_client()                            # a new run of the client; the game has an OLD save loaded (job number 0)
        again._on_connected({"slot_data": {"locations": LOCS, "seed_guard": 7, "options": {}}})
        await again.wait_patch()
        self.game.restart_process()
        self.game._last_state = None
        await self.wait_effects(2)
        self.assertEqual([e[1] for e in self.game.effects], ["credits", "skill"])             # replayed from the saved ledger
        again.exit_event.set()

    async def test_jobs_the_game_never_answered_are_sent_again_when_it_reports_its_state(self):
        self.ctx._on_job_failure(Job("credits", "100", "You received: Republic Credits", None), "no answer from the game after 30 sends")
        self.ctx._on_job_failure(Job("tracker", "40", "", None), "no answer")
        self.assertEqual([j["action"] for j in self.ctx._failed], ["credits"])                # the tracker is resent by the next check, not from here
        self.ctx._save_state()
        self.game._put("T|0|0")
        await self.wait_effects(1)
        self.assertEqual([(e[1], e[2]) for e in self.game.effects], [("credits", "100")])
        self.assertEqual(self.ctx._failed, [])

    async def test_a_state_file_from_before_the_jobs_were_kept_delivers_everything_again(self):
        with open(os.path.join(self.dir, "client_seedx_1.json"), "w") as f:
            json.dump({"delivered": 5, "paid_checks": 3, "unlocked": 0}, f)
        again = self.another_client()
        again._on_connected({"slot_data": {"locations": LOCS, "seed_guard": 7, "options": {}}})
        self.assertEqual((again.delivered, again.paid_checks), (0, 3))
        again.exit_event.set()
        await again.wait_patch()

    async def test_a_running_game_is_left_alone_unless_the_player_asks(self):
        real = self.ctx.make_patcher

        def running_patcher():
            patcher = real()
            patcher._running = lambda: True
            return patcher
        self.ctx.make_patcher = running_patcher
        override = os.path.join(self.game_dir, "Override")
        before = sorted(os.listdir(override)) if os.path.isdir(override) else []
        text = self.ctx.patch_game()
        self.assertIn("NOT changed", text)
        self.assertIn("/k2_patch", text)
        self.assertEqual(sorted(os.listdir(override)) if os.path.isdir(override) else [], before)       # a reconnect in the middle of a game touches nothing
        self.ctx.patch_game(force=True)                                                                  # the /k2_patch command does
        self.assertTrue(os.path.isfile(os.path.join(override, "k2se_msg.dlg")))

    async def test_a_finished_patch_says_so_and_a_patch_with_problems_says_that(self):
        text = self.ctx.patch_game()                      # the stand-in game folder has no dialog.tlk and no game archives: problems are reported, not hidden
        self.assertIn("FINISHED WITH PROBLEMS", text)
        self.assertNotIn("you can start the game now", text)
        self.ctx.slot_data.setdefault("options", {})["story_gates"] = 0
        old = K.journal_files
        K.journal_files = lambda *a: ({}, [])
        self.addCleanup(setattr, K, "journal_files", old)
        text = self.ctx.patch_game()
        self.assertIn("Finished in", text)
        self.assertIn("you can start the game now", text)

    async def test_two_patches_never_run_at_the_same_time(self):
        import threading
        import time
        active, worst = [0], [0]
        lock = threading.Lock()
        real = self.ctx._patch_game

        def counted(force=False):
            with lock:
                active[0] += 1
                worst[0] = max(worst[0], active[0])
            time.sleep(0.2)
            with lock:
                active[0] -= 1
            return "ok"
        self.ctx._patch_game = counted
        self.ctx.start_patch()
        self.ctx.start_patch()
        await asyncio.sleep(0.1)
        await self.ctx.wait_patch()
        await asyncio.sleep(0.6)
        self.assertEqual(worst[0], 1)
        self.ctx._patch_game = real

    async def test_the_disguised_extras_get_their_look_rows_in_the_seed_block(self):
        self.ctx._on_connected({"slot_data": self.extras_slot()})
        await self.ctx.wait_patch()
        config = open(os.path.join(self.dir, "config.txt")).read()
        self.assertIn("ap_look_12=30", config)             # no KotOR 1 models in the stand-in game folder: Bastila's generic look
        self.assertIn("ap_look_13=48", config)
        self.assertNotIn("ap_look_14", config)             # that one is written into its template instead

    async def test_an_extra_in_the_party_is_raised_to_the_players_level(self):
        self.ctx._on_connected({"slot_data": self.extras_slot()})
        self.game._put("L|9")
        self.game._put("CC|12:5:1:255:0")
        await self.wait_effects(1)
        self.assertEqual([(e[1], e[2]) for e in self.game.effects], [("compclass", "12:0:5:9:0:0:0")])

    async def test_crafting_items_unlock_types_and_rewrite_the_table_and_switches(self):
        plan = {"mode": 1, "seed": 5, "gated": True, "types": ["armor", "ranged", "melee", "lightsaber", "other", "parts", "lab"], "gear": []}
        self.ctx.slot_data["crafting_plan"] = plan
        calls = []

        def fake_files(game_dir, p, unlocked, received=None):
            calls.append(sorted(unlocked))
            return {"k2se_recipes.2da": ("table for " + ",".join(sorted(unlocked))).encode()}, []
        old = K.crafting_files
        K.crafting_files = fake_files
        self.addCleanup(setattr, K, "crafting_files", old)
        self.ctx.patch_game()
        self.assertEqual(calls, [[]])
        config = open(os.path.join(self.dir, "config.txt")).read()
        self.assertIn("ap_craft_bench=0", config)
        self.assertIn("ap_craft_up=0", config)
        self.assertIn("ap_craft_lab=0", config)
        for n in ("Crafting: Upgrade Parts", "Crafting: Melee Weapons"):
            self.ctx.items_received.append(NetworkItem(ITEM_NAME_TO_ID[n], 0, 1, 0))
        await self.ctx._deliver_new_items()
        self.assertEqual(calls[-1], ["melee", "parts"])
        config = open(os.path.join(self.dir, "config.txt")).read()
        self.assertIn("ap_craft_bench=1", config)
        self.assertIn("ap_craft_up=1", config)
        self.assertIn("ap_craft_lab=0", config)
        with open(os.path.join(self.game_dir, "Override", "k2se_recipes.2da"), "rb") as f:
            self.assertEqual(f.read(), b"table for melee,parts")
        await self.wait_effects(2)
        self.assertEqual([e[1] for e in self.game.effects], ["notify", "notify"])
        count = len(calls)
        await self.ctx._deliver_new_items()                     # nothing new: no rebuild
        self.assertEqual(len(calls), count)

    async def test_crafting_without_gating_unlocks_everything_and_never_rebuilds(self):
        self.ctx.slot_data["crafting_plan"] = {"mode": 2, "seed": 1, "gated": False, "types": ["armor", "parts", "lab"], "gear": []}
        calls = []
        old = K.crafting_files
        K.crafting_files = lambda g, p, u, r=None: (calls.append(1) or {"k2se_recipes.2da": b"t"}, [])
        self.addCleanup(setattr, K, "crafting_files", old)
        self.ctx.patch_game()
        config = open(os.path.join(self.dir, "config.txt")).read()
        self.assertIn("ap_craft_bench=1", config)
        self.assertIn("ap_craft_lab=1", config)
        await self.ctx._deliver_new_items()
        self.assertEqual(len(calls), 1)

    async def test_a_gear_item_is_given_when_crafting_is_off(self):
        self.ctx.items_received.append(NetworkItem(ITEM_NAME_TO_ID["Gear: a_light_02"], 0, 1, 0))
        await self.ctx._deliver_new_items()
        await self.wait_effects(1)
        self.assertEqual([(e[1], e[2]) for e in self.game.effects], [("gear", "a_light_02")])

    async def test_in_crafting_mode_a_gear_item_adds_its_recipe_and_gives_components(self):
        self.ctx.slot_data["crafting_plan"] = {"mode": 1, "seed": 3, "gated": False, "types": ["armor"], "gear": [["a_light_02", "armor"], ["a_robe_02", "armor"]],
                                               "gear_gated": True}
        calls = []

        def fake_files(game_dir, p, unlocked, received=None):
            calls.append(sorted(received or ()))
            return {"k2se_recipes.2da": ("recipes " + ",".join(sorted(received or ()))).encode()}, []
        old_files, old_yield = K.crafting_files, K.material_yields
        K.crafting_files = fake_files
        K.material_yields = lambda g, p: {"a_light_02": 7}
        self.addCleanup(setattr, K, "crafting_files", old_files)
        self.addCleanup(setattr, K, "material_yields", old_yield)
        self.ctx.patch_game()
        self.assertEqual(calls, [[]])
        self.ctx.items_received.append(NetworkItem(ITEM_NAME_TO_ID["Gear: a_light_02"], 0, 1, 0))
        await self.ctx._deliver_new_items()
        self.assertEqual(calls[-1], ["a_light_02"])
        with open(os.path.join(self.game_dir, "Override", "k2se_recipes.2da"), "rb") as f:
            self.assertEqual(f.read(), b"recipes a_light_02")
        await self.wait_effects(1)
        self.assertEqual([(e[1], e[2]) for e in self.game.effects], [("materials", "7")])

    async def test_a_vendor_pass_becomes_a_pass_job(self):
        self.ctx.items_received.append(NetworkItem(ITEM_NAME_TO_ID["Vendor Pass: Ability Training"], 0, 1, 0))
        await self.ctx._deliver_new_items()
        await self.wait_effects(1)
        self.assertEqual([(e[1], e[2]) for e in self.game.effects], [("pass", "abil")])

    async def test_visiting_areas_orders_no_token_fill(self):
        # the Bazaar's tokens are placed in the module files when the game is patched, never by an order while playing
        slot = {"locations": LOCS, "seed_guard": 7, "options": {"bazaar": True}}
        self.ctx._on_connected({"slot_data": slot})
        self.game._put("V|202TEL")
        self.game._put("V|203TEL")
        await asyncio.sleep(1.0)
        self.assertEqual(self.game.effects, [])

    async def test_no_bazaar_orders_when_the_option_is_off(self):
        self.game._put("V|202TEL")
        await asyncio.sleep(1.0)
        self.assertEqual(self.game.effects, [])

    async def test_the_prestige_item_orders_the_seeds_pair(self):
        self.ctx.slot_data["prestige_pair"] = [13, 16]
        self.ctx.items_received.append(NetworkItem(ITEM_NAME_TO_ID["Prestige Class"], 0, 1, 0))
        self.game._put("L|9")
        await asyncio.sleep(1.0)
        await self.ctx._deliver_new_items()
        await asyncio.sleep(1.0)
        self.assertEqual(self.game.effects, [])                  # level 9: the item waits for level 15
        self.assertTrue(self.ctx.prestige_pending)
        self.game._put("L|15")
        await self.wait_effects(1)
        self.assertEqual([(e[1], e[2]) for e in self.game.effects], [("prestige", "13:16")])
        self.assertFalse(self.ctx.prestige_pending)

    async def test_no_xp_correction_when_experience_is_off(self):
        self.ctx.slot_data["options"] = {"experience_mode": 0}
        self.game._put("XP|99999")
        self.game._put("V|201TEL")
        await asyncio.sleep(1.0)
        self.assertEqual(self.game.effects, [])

    async def test_a_death_in_the_game_is_sent_when_deathlink_is_on(self):
        deaths = []

        async def fake_death(text=""):
            deaths.append(text)
        self.ctx.send_death = fake_death
        self.ctx.player_names = {1: "Exile"}
        self.game._put("DL|death")
        await asyncio.sleep(1.2)
        self.assertEqual(deaths, [])                      # DeathLink tag not set: nothing is sent
        self.ctx.tags.add("DeathLink")
        self.game._put("DL|death")
        for _ in range(30):
            await asyncio.sleep(0.1)
            if deaths:
                break
        self.assertEqual(len(deaths), 1)

    async def test_a_received_deathlink_kills_the_player_once(self):
        self.ctx.on_deathlink({"time": 5.0, "source": "Bob", "cause": "fell"})
        await self.wait_effects(1)
        self.assertEqual([(e[1], e[2]) for e in self.game.effects], [("death", "")])

    async def test_trap_item_is_sent_as_traplink_and_a_received_trap_is_not(self):
        self.ctx.tags.add("TrapLink")
        self.ctx.server = object()
        self.ctx.player_names = {1: "Exile"}
        self.ctx.slot_data["options"] = {"trap_types": ["lose_credits"]}
        self.ctx.items_received.append(NetworkItem(ITEM_NAME_TO_ID["Trap: Lose Credits"], 0, 1, 0))
        await self.ctx._deliver_new_items()
        await self.wait_effects(1)
        for _ in range(30):
            await asyncio.sleep(0.1)
            if any(m.get("cmd") == "Bounce" for m in self.sent):
                break
        bounces = [m for m in self.sent if m.get("cmd") == "Bounce"]
        self.assertEqual(len(bounces), 1)
        self.assertEqual(bounces[0]["tags"], ["TrapLink"])
        self.assertEqual(bounces[0]["data"]["trap_name"], "Trap: Lose Credits")
        # a trap from another player rolls one of our allowed types and is applied, but is not sent on
        self.ctx._on_trap_link({"time": 99.0, "source": "Bob", "trap_name": "Whatever"})
        await self.wait_effects(2)
        self.assertEqual([(e[1], e[2]) for e in self.game.effects], [("trap", "credits"), ("trap", "credits")])
        await asyncio.sleep(1.0)
        self.assertEqual(len([m for m in self.sent if m.get("cmd") == "Bounce"]), 1)
        # our own bounce coming back is ignored
        self.ctx._on_trap_link({"time": self.ctx._last_trap_link_sent, "source": "Exile", "trap_name": "x"})
        await asyncio.sleep(0.5)
        self.assertEqual(len(self.game.effects), 2)

    async def test_trap_candidates_follow_the_trap_types_option(self):
        self.ctx.slot_data["options"] = {"trap_types": ["halve_wisdom", "cut_max_health"]}
        self.assertEqual(sorted(self.ctx.trap_candidates()), ["trap:halve_wisdom", "trap:max_health"])

    async def test_tokens_are_delivered_as_items(self):
        for n in ("Telos Progression", "Endgame Progression"):
            self.ctx.items_received.append(NetworkItem(ITEM_NAME_TO_ID[n], 0, 1, 0))
        await self.ctx._deliver_new_items()
        await self.wait_effects(2)
        self.assertEqual([(e[1], e[2]) for e in self.game.effects], [("token", "telos"), ("token", "endgame")])
        with open(os.path.join(self.dir, "config.txt")) as f:
            self.assertNotIn("ap_tk_", f.read())            # the seed's block holds settings only; the gates read the family quests in the journal

    async def wait_stages(self, n):
        for _ in range(100):
            await asyncio.sleep(0.1)
            if len(self.game.stages) >= n:
                break

    async def test_the_tracker_starts_at_connect_and_moves_with_the_share_of_checks(self):
        await self.wait_stages(1)
        self.assertEqual(self.game.stages, [1])                               # "your run has begun", sent when the client connects
        locations = sorted(self.ctx.tracker.locations)
        for lid in locations[:len(locations) // 4]:                           # a quarter of the checks: the 20 percent stage
            self.ctx.tracker.checked.add(lid)
        self.ctx._apply_progress()
        await self.wait_stages(2)
        self.assertEqual(self.game.stages, [1, 20])
        self.ctx._apply_progress()                                            # nothing new: nothing is sent again
        await asyncio.sleep(0.6)
        self.assertEqual(self.game.stages, [1, 20])
        self.assertEqual(self.ctx.tracker_sent, 20)
        for lid in locations:
            self.ctx.tracker.checked.add(lid)
        self.ctx._apply_progress()
        await self.wait_stages(3)
        self.assertEqual(self.game.stages, [1, 20, 100])

    async def test_a_tracker_stage_that_never_reached_the_game_is_sent_again_with_the_next_check(self):
        await self.wait_stages(1)
        self.ctx._on_job_failure(Job("tracker", "40"), "no answer")
        self.assertEqual(self.ctx.tracker_sent, 0)
        self.ctx._apply_progress()
        await self.wait_stages(2)
        self.assertEqual(self.game.stages[-1], 1)

    async def test_the_tracker_stage_survives_a_restart(self):
        await self.wait_stages(1)
        self.ctx._save_state()
        again = K.KotorTwoContext(None, None, link_dir=self.dir, game_dir=self.game_dir, payload_dir=os.path.join(self.dir, "none"),
                                  config_path=os.path.join(self.dir, "config.txt"))
        again.seed_name, again.slot = "seedx", 1
        again._on_connected({"slot_data": {"locations": LOCS, "seed_guard": 7}})
        self.assertEqual(again.tracker_sent, 1)
        again.exit_event.set()

    async def test_connecting_patches_the_game_folder(self):
        # setUp connected with seed_guard 7: the seed's numbers are in config.txt, and a second patch changes nothing
        with open(os.path.join(self.dir, "config.txt")) as f:
            before = f.read()
        self.assertIn("ap_seed_guard=7", before)
        self.assertIn("KOTOR 2 patch", self.ctx.last_patch)
        self.ctx.patch_game()
        with open(os.path.join(self.dir, "config.txt")) as f:
            self.assertEqual(f.read(), before)

    async def test_missing_game_folder_is_explained(self):
        self.ctx.make_patcher = lambda: None
        self.assertIn("/k2_patch", self.ctx.patch_game())


    def _commands(self):
        cp = K.KotorTwoCommandProcessor(self.ctx)
        cp.lines = []
        cp.output = lambda text: cp.lines.append(text)
        return cp

    async def _wait_effects(self, n):
        for _ in range(100):
            await asyncio.sleep(0.1)
            if len(self.game.effects) >= n:
                break

    async def test_k2_give_sends_an_item_by_name_or_arm(self):
        cp = self._commands()
        self.assertTrue(cp._cmd_k2_give("Telos", "Progression", "2"))
        self.assertTrue(cp._cmd_k2_give("skill:stealth"))
        self.assertTrue(cp._cmd_k2_give("Vendor", "Pass:", "Skill", "Training"))
        await self._wait_effects(4)
        self.assertEqual([(e[1], e[2]) for e in self.game.effects], [("token", "telos"), ("token", "telos"), ("skill", "stealth"), ("pass", "skill")])
        self.assertEqual(self.ctx.delivered, 0)             # the server's item count is untouched: this is a test, not a received item

    async def test_k2_give_refuses_what_needs_the_real_item(self):
        cp = self._commands()
        self.assertFalse(cp._cmd_k2_give("Crafting:", "Armor", "and", "Robes"))
        self.assertFalse(cp._cmd_k2_give())
        self.assertEqual(self.game.effects, [])

    async def test_k2_prepare_builds_the_payload_in_the_background_and_says_what_to_do_next(self):
        calls = []

        class FakeBuilder:
            @staticmethod
            def build(game, out, k1):
                calls.append((game, out, k1))
                return {"files": {"a.ncs": "x", "b.are": "y"}, "problems": []}
        sys.modules["build_payload"] = FakeBuilder
        self.addCleanup(sys.modules.pop, "build_payload", None)
        cp = self._commands()
        self.assertTrue(cp._cmd_k2_prepare())
        for _ in range(50):
            await asyncio.sleep(0.1)
            if len(cp.lines) >= 2:
                break
        self.assertEqual(calls, [(os.path.normpath(self.game_dir), self.ctx.payload_dir, None)])
        self.assertIn("2 files", cp.lines[-1])
        self.assertIn("/k2_patch", cp.lines[-1])

    async def test_k2_prepare_reports_a_failed_build(self):
        class FakeBuilder:
            @staticmethod
            def build(game, out, k1):
                raise RuntimeError("the compiler is missing")
        sys.modules["build_payload"] = FakeBuilder
        self.addCleanup(sys.modules.pop, "build_payload", None)
        cp = self._commands()
        cp._cmd_k2_prepare()
        for _ in range(50):
            await asyncio.sleep(0.1)
            if len(cp.lines) >= 2:
                break
        self.assertIn("could not be built", cp.lines[-1])
        self.assertIn("the compiler is missing", cp.lines[-1])

    async def test_k2_paths_reports_the_payload_and_the_extender(self):
        cp = self._commands()
        self.assertTrue(cp._cmd_k2_paths())
        text = "\n".join(cp.lines)
        self.assertIn("game folder: " + self.game_dir, text)
        self.assertIn("payload", text)
        self.assertIn("extender", text)


if __name__ == "__main__":
    unittest.main()
