"""The Status tab and the Heartbeat log: the text (k2_status.py), the dispatcher's lists, and how the client feeds them. No window is opened; the Kivy part
(k2_gui.py) is only built as a class when Kivy is installed.
Run through tools/run_client_tests.py."""
import asyncio
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from fake_game import FakeGame  # noqa: E402
from k2_dispatcher import DispatchClient  # noqa: E402
import k2_status as S  # noqa: E402
import KotorTwoClient as K  # noqa: E402


class Clock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


class TestAgo(unittest.TestCase):
    def test_spans(self):
        self.assertEqual(S.ago(None), "never")
        self.assertEqual(S.ago(4.2), "4 s ago")
        self.assertEqual(S.ago(180), "3 min ago")
        self.assertEqual(S.ago(7200), "2.0 h ago")
        self.assertEqual(S.ago(-5), "0 s ago")


class TestGameWatch(unittest.TestCase):
    def make(self, states):
        clock = Clock()
        it = iter(states)
        watch = S.GameWatch(running=lambda: next(it), clock=clock)
        return watch, clock

    def test_first_look_then_changes(self):
        watch, clock = self.make([False, True, True, False])
        self.assertEqual(watch.refresh(), ["game process: not running"])
        self.assertEqual(watch.refresh(), [])                              # looked less than PROCESS_EVERY seconds ago
        clock.now += S.PROCESS_EVERY
        self.assertEqual(watch.refresh(), ["the game started"])
        clock.now += S.PROCESS_EVERY
        self.assertEqual(watch.refresh(), [])                              # still running: nothing to say
        clock.now += S.PROCESS_EVERY
        self.assertEqual(watch.refresh(), ["the game closed"])

    def test_a_failed_look_claims_nothing(self):
        def boom():
            raise OSError("no tasklist")
        watch = S.GameWatch(running=boom, clock=Clock())
        self.assertEqual(watch.refresh(), [])
        self.assertIsNone(watch.running)

    def test_closing_forgets_the_last_report(self):
        watch, clock = self.make([True, False])
        watch.refresh()
        watch.heard()
        clock.now += S.PROCESS_EVERY
        watch.refresh()
        self.assertIsNone(watch.since_heard())

    def test_silence_needs_a_running_game_and_waiting_jobs(self):
        watch, clock = self.make([True])
        watch.refresh()
        watch.heard()
        clock.now += S.SILENT_AFTER - 1
        self.assertFalse(watch.silent(True))
        clock.now += 2
        self.assertTrue(watch.silent(True))
        self.assertFalse(watch.silent(False))                              # nothing is waiting: a quiet game is just a quiet game
        self.assertIn("has not answered", watch.silence_note(True))
        self.assertIsNone(watch.silence_note(True))                        # said once
        watch.heard()
        self.assertFalse(watch.silent(True))

    def test_a_game_that_never_spoke_counts_as_silent_when_jobs_wait(self):
        watch, _ = self.make([True])
        watch.refresh()
        self.assertTrue(watch.silent(True))

    def test_sessions_and_beat(self):
        watch, clock = self.make([True])
        watch.new_session()
        watch.new_session()
        self.assertEqual(watch.sessions, 2)
        self.assertTrue(watch.beat_due())
        self.assertFalse(watch.beat_due())
        clock.now += S.HEARTBEAT_EVERY
        self.assertTrue(watch.beat_due())


class TestRender(unittest.TestCase):
    def test_a_fresh_client(self):
        text = S.render(S.Snapshot())
        self.assertEqual(text["server"], "Archipelago server: not connected")
        self.assertEqual(text["game"], "Game: looking ...")
        self.assertEqual(text["patch"], "Game files: not written in this run")
        self.assertEqual(text["checks"], "Checks: 0 / 0")
        self.assertIn("Not connected to the Archipelago server", text["warnings"])
        self.assertEqual(text["state"], "")

    def test_a_running_game(self):
        s = S.Snapshot(server_connected=True, slot_name="Exile", seed_name="123", game_running=True, since_heard=4.0, module="101PER", level=3, alignment=80, xp=2800,
                       patch_text="Wrote 12 files.", patch_age=120, checks_done=5, checks_total=300, job_counter=17, jobs_applied=3)
        text = S.render(s)
        self.assertEqual(text["server"], "Archipelago server: connected as Exile (seed 123)")
        self.assertEqual(text["game"], "Game: running; last report 4 s ago")
        self.assertEqual(text["state"], "Area 101PER, level 3, light side (80), 2800 XP")
        self.assertEqual(text["patch"], "Game files: Wrote 12 files. (2 min ago)")
        self.assertEqual(text["jobs"], "Game job number: 17; applied this run: 3")
        self.assertEqual(text["warnings"], "")

    def test_state_line_only_for_a_running_game(self):
        s = S.Snapshot(game_running=False, module="101PER", level=3)
        self.assertEqual(S.render(s)["state"], "")

    def test_goal_and_patching(self):
        s = S.Snapshot(patching=True, victory=True, goal_sent=True, checks_done=9, checks_total=9)
        text = S.render(s)
        self.assertEqual(text["patch"], "Game files: being written now ...")
        self.assertEqual(text["checks"], "Checks: 9 / 9 - goal reached, reported to the server")

    def test_warnings(self):
        s = S.Snapshot(server_connected=True, game_running=False, jobs_waiting=2, jobs_failed=1, patch_problems=True)
        out = S.warnings_for(s, False)
        self.assertEqual(len(out), 3)
        self.assertIn("wait for the game", out[1])
        self.assertTrue(S.warnings_for(S.Snapshot(server_connected=True, game_running=True, jobs_waiting=1, since_heard=200), True)[0].startswith("The game is running but"))

    def test_alignment_words(self):
        self.assertEqual([S.alignment_word(v) for v in (0, 33, 34, 66, 67, 100)], ["dark side", "dark side", "neutral", "neutral", "light side", "light side"])

    def test_heartbeat_line(self):
        s = S.Snapshot(server_connected=True, game_running=True, since_heard=3, job_counter=9, jobs_waiting=2, jobs_applied=7, jobs_failed=1, checks_done=4, checks_total=100)
        self.assertEqual(S.heartbeat_line(s), "heartbeat: server connected; game running, last report 3 s ago; job 9; 2 waiting, 7 applied, 1 failed; checks 4/100")
        self.assertEqual(S.heartbeat_line(S.Snapshot()), "heartbeat: server not connected; game unknown; job ?; 0 waiting, 0 applied, 0 failed; checks 0/0")


class FakeLink:
    def __init__(self):
        self.written = []

    def write_job(self, seq, guard, action, args, message):
        self.written.append((seq, action, args))
        return True


class TestWindowText(unittest.IsolatedAsyncioTestCase):
    async def test_waiting_failed_recent(self):
        d = DispatchClient(FakeLink())
        self.assertEqual(d.window_text(), {"waiting": "Deliveries waiting: none", "failed": "", "recent": "Recently delivered: none"})
        d.counter = 0
        a = d.submit("credits", "100", item_name="Republic Credits")
        b = d.submit("skill", "stealth", item_name="Skill: Stealth")
        await asyncio.sleep(0.05)                       # the pump takes the first job
        text = d.window_text()
        self.assertEqual(text["waiting"].splitlines(), ["Deliveries waiting: 2", "  sending Republic Credits", "  queued  Skill: Stealth"])
        d.on_event("D|1|credits|1")
        await asyncio.sleep(0.6)                                       # the pump moves on to the second job
        d.on_event("D|2|skill|2")
        await asyncio.sleep(0.6)
        self.assertEqual(d.window_text()["recent"].splitlines(), ["Recently delivered:", "  Skill: Stealth", "  Republic Credits"])
        self.assertEqual(d.window_text()["failed"], "")
        self.assertTrue(a.done.is_set() and b.done.is_set())

    async def test_failed_and_overflow(self):
        d = DispatchClient(FakeLink())
        d.counter = 0
        for i in range(10):
            d.submit("notify", "", item_name="item %d" % i)
        await asyncio.sleep(0.05)
        lines = d.window_text()["waiting"].splitlines()
        self.assertEqual(lines[0], "Deliveries waiting: 10")
        self.assertEqual(lines[-1], "  ... and 2 more")
        job = d.current
        d._fail(job, "this save belongs to a different seed")
        await asyncio.sleep(0.4)
        self.assertEqual(d.window_text()["failed"].splitlines(), ["Failed deliveries (1):", "  item 0: this save belongs to a different seed"])
        d._queue.clear()
        d.current = None


class TestClient(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.dir = tempfile.mkdtemp()
        self.ctx = K.KotorTwoContext(None, None, link_dir=self.dir, game_dir=os.path.join(self.dir, "game"), payload_dir=os.path.join(self.dir, "none"),
                                     config_path=os.path.join(self.dir, "config.txt"))
        self.clock = Clock()
        self.alive = True
        self.ctx.watch = S.GameWatch(running=lambda: self.alive, clock=self.clock)
        self.game = FakeGame(self.ctx.link)

    async def asyncTearDown(self):
        self.ctx.exit_event.set()
        shutil.rmtree(self.dir, ignore_errors=True)

    async def test_lines_from_the_game_feed_the_watch(self):
        self.game._put("V|101PER")                     # history: written before the client started, so it does not count as the game speaking
        await self.ctx._process_outbox()
        self.assertIsNone(self.ctx.watch.last_heard)
        self.game._put("L|3")
        await self.ctx._process_outbox()
        self.assertEqual(self.ctx.watch.since_heard(), 0)
        self.clock.now += 10
        self.assertEqual(self.ctx.watch.since_heard(), 10)
        self.game._out_seq = 0                         # a new game process numbers its lines from 1 again
        self.game._put("V|102PER")
        await self.ctx._process_outbox()
        self.assertEqual(self.ctx.watch.sessions, 1)
        self.assertEqual(self.ctx.current_module, "102PER")

    async def test_snapshot_and_status_lines(self):
        self.ctx.watch.refresh(force=True)
        self.ctx.game_level, self.ctx.current_module, self.ctx.game_alignment = 5, "201TEL", 20
        self.ctx.watch.heard()
        lines = self.ctx.status_lines()
        self.assertIn("Game: running; last report 0 s ago", lines)
        self.assertTrue(any(l.startswith("Area 201TEL, level 5, dark side (20)") for l in lines), lines)
        self.assertIn("Archipelago server: not connected", lines)
        self.assertTrue(any(l.startswith("! Not connected") for l in lines))

    async def test_status_command_prints_the_same_lines(self):
        out = []
        proc = K.KotorTwoCommandProcessor(self.ctx)
        proc.output = out.append
        self.assertTrue(proc._cmd_k2_status())
        self.assertEqual(out, self.ctx.status_lines())

    async def test_heartbeat_step_logs_changes_silence_and_the_periodic_line(self):
        self.ctx.dispatcher.submit("credits", "10", item_name="Republic Credits")
        with self.assertLogs("Heartbeat", level="INFO") as logs:
            await self.ctx._heartbeat_step()
            self.assertEqual([r.getMessage() for r in logs.records][:1], ["KOTOR 2: game process: running"])
            self.assertTrue(any(m.startswith("heartbeat: server not connected; game running") for m in [r.getMessage() for r in logs.records]))
            self.clock.now += S.SILENT_AFTER + 1
            await self.ctx._heartbeat_step()
            warnings = [r for r in logs.records if r.levelname == "WARNING"]
            self.assertEqual(len(warnings), 1)
            self.assertIn("has not answered", warnings[0].getMessage())
            await self.ctx._heartbeat_step()                       # the silence is not repeated every second
            self.assertEqual(len([r for r in logs.records if r.levelname == "WARNING"]), 1)
            self.alive = False
            self.clock.now += S.PROCESS_EVERY
            await self.ctx._heartbeat_step()
            self.assertTrue(any(r.getMessage() == "KOTOR 2: the game closed" for r in logs.records))
        self.ctx.dispatcher._queue.clear()
        self.ctx.dispatcher.current = None

    async def test_patch_state_reaches_the_snapshot(self):
        self.assertEqual(self.ctx.status_snapshot().patch_text, "")
        self.ctx.make_patcher = lambda: None           # never let a test find the real game on this machine: the patch must report that it has no game folder
        text = self.ctx._patch_game()
        snap = self.ctx.status_snapshot()
        self.assertTrue(snap.patch_problems)
        self.assertEqual(snap.patch_text, text)
        self.assertFalse(snap.patching)
        self.assertIsNotNone(snap.patch_age)


class TestGui(unittest.TestCase):
    def test_manager_class(self):
        if os.environ.get("GITHUB_ACTIONS") or os.environ.get("CI"):
            self.skipTest("Kivy opens a window when it is imported, which hangs on a machine with no display (GitHub's runners)")
        try:
            from kvui import GameManager
            import kivymd  # noqa: F401
        except Exception:
            self.skipTest("Kivy is not installed here")
        from k2_gui import manager_class
        cls = manager_class(GameManager)
        self.assertTrue(issubclass(cls, GameManager))
        self.assertEqual(cls.logging_pairs, [("Client", "Archipelago"), ("Heartbeat", "Heartbeat")])
        self.assertEqual(cls.base_title, "KOTOR 2 Archipelago Client")


if __name__ == "__main__":
    unittest.main()
