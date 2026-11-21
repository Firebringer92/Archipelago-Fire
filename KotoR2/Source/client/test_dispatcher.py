"""Tests of the client dispatcher against a fake game. Run: python client/test_dispatcher.py  (from the project folder)"""
import asyncio
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fake_game import FakeGame  # noqa: E402
from k2_dispatcher import DispatchClient, counter_of, next_seq  # noqa: E402
from k2_files import Link  # noqa: E402


class Rig(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.dir = tempfile.mkdtemp()
        self.link = Link(self.dir)
        self.game = FakeGame(self.link)
        self.client = DispatchClient(self.link, guard=7)
        self.client.RESEND_AFTER = 0.5
        self.client.LEARN_WAIT = 1.0
        self.stop = False
        self.task = asyncio.ensure_future(self.run_game())

    async def asyncTearDown(self):
        self.stop = True
        await self.task
        shutil.rmtree(self.dir, ignore_errors=True)

    async def run_game(self):
        while not self.stop:
            self.game.poll()
            for line in self.link.read_new():
                self.client.on_event(line)
            await asyncio.sleep(0.03)

    async def finish(self, jobs, timeout=15):
        await asyncio.wait_for(asyncio.gather(*[j.done.wait() for j in jobs]), timeout)


class TestDispatch(Rig):
    async def test_jobs_apply_once_in_order(self):
        jobs = [self.client.submit("credits", str(100 * (i + 1))) for i in range(5)]
        await self.finish(jobs)
        self.assertEqual([e[1:] for e in self.game.effects], [("credits", "100"), ("credits", "200"), ("credits", "300"), ("credits", "400"), ("credits", "500")])
        self.assertEqual(self.game.counter, 5)
        self.assertTrue(all(j.state == "applied" for j in jobs))

    async def test_number_wraps_after_255(self):
        self.game.counter = 253
        jobs = [self.client.submit("xp", str(i)) for i in range(5)]
        await self.finish(jobs)
        self.assertEqual([e[0] for e in self.game.effects], [254, 255, 1, 2, 3])
        self.assertEqual(self.game.counter, 3)

    async def test_wrong_guess_is_corrected(self):
        self.game.counter = 40          # the client has not heard the number yet, but the game says T first, so also test a stale guess
        self.client.counter = 10        # stale
        job = self.client.submit("credits", "1")
        await self.finish([job])
        self.assertEqual(self.game.effects[-1][0], 41)
        self.assertEqual(job.state, "applied")

    async def test_a_rollback_while_the_pump_waits_does_not_end_the_pump(self):
        """The pump sleeps with a job in flight; a rollback takes the job out of flight (no number) before the pump wakes. The pump must not send that job
        without a number (a TypeError ended the pump and every queued job stopped)."""
        self.game.poll = lambda: None                      # the game answers nothing: the job stays in flight
        job = self.client.submit("credits", "1")
        for _ in range(40):
            if self.client.current is job:
                break
            await asyncio.sleep(0.05)
        self.assertIs(self.client.current, job)
        self.client.current = None                         # what a rollback does to the job in flight
        job.seq = None
        job.state = "queued"
        self.client._queue.append(job)
        await asyncio.sleep(0.8)                           # longer than the resend time: the old code sent the numberless job here
        self.assertFalse(self.client._task.done())
        self.assertIsNotNone(job.seq)                      # taken up again from the queue and numbered

    async def test_rollback_replays_missing_jobs(self):
        first = [self.client.submit("credits", str(i)) for i in range(1, 3)]
        await self.finish(first)
        self.game.save("old")                       # counter 2
        more = [self.client.submit("credits", str(i)) for i in range(3, 5)]
        await self.finish(more)
        self.assertEqual(self.game.counter, 4)
        self.game.load("old")                       # the player reloads the older save
        for _ in range(100):
            await asyncio.sleep(0.1)
            if self.game.counter == 4:
                break
        self.assertEqual(self.game.counter, 4)
        self.assertEqual([e[2] for e in self.game.effects], ["1", "2", "3", "4"])

    async def _wait_for(self, check, seconds=12):
        for _ in range(int(seconds / 0.1)):
            if check():
                return True
            await asyncio.sleep(0.1)
        return check()

    async def test_second_reload_during_a_replay(self):
        """Two older saves loaded one after the other, the second while the first replay is still in flight (found live: the replayed jobs stayed in flight
        for ever and failed with 'no answer from the game')."""
        await self.finish([self.client.submit("credits", str(i)) for i in range(1, 5)])
        self.assertEqual(self.game.counter, 4)
        real_poll = self.game.poll
        self.game.poll = lambda: None                      # the game is busy loading: it answers nothing for a moment
        self.client.on_event("T|0|7")                      # save A (number 0) was loaded
        await self._wait_for(lambda: self.client.current is not None and self.client.current.fixed_seq, 3)
        self.assertEqual(self.client.current.seq, 1)       # the first replayed job is in flight
        self.game.counter = 2                              # then save B (number 2) is loaded
        self.client.on_event("T|2|7")
        self.client.on_event("S|1|2")                      # the game's answer to the old replay job
        self.game.poll = real_poll
        done = await self._wait_for(lambda: self.game.counter == 4)
        self.assertTrue(done, "the game stayed at %d (client failed %d job(s))" % (self.game.counter, self.client.stats["failed"]))
        self.assertEqual(self.client.stats["failed"], 0)
        self.assertEqual([e[2] for e in self.game.effects][-2:], ["3", "4"])

    async def test_new_job_after_a_replay_is_numbered_right(self):
        await self.finish([self.client.submit("credits", str(i)) for i in range(1, 4)])
        self.game.save("old")
        await self.finish([self.client.submit("credits", "4")])
        self.game.load("old")
        await self._wait_for(lambda: self.game.counter == 4)
        later = self.client.submit("credits", "5")
        await self.finish([later])
        self.assertEqual(self.game.counter, 5)
        self.game.load("old")                              # and a second reload of the same save replays all of it again
        self.assertTrue(await self._wait_for(lambda: self.game.counter == 5))
        self.assertEqual(self.client.stats["failed"], 0)

    async def test_death_job_is_not_replayed(self):
        await self.finish([self.client.submit("credits", "1")])
        self.game.save("old")
        d = self.client.submit("trap", "death")
        d.action, d.args = "trap", "death"
        await self.finish([d, self.client.submit("credits", "2")])
        self.client.ledger = [(i, a, b, c, not (a == "trap" and b == "death")) for (i, a, b, c, _r) in self.client.ledger]
        self.game.load("old")
        for _ in range(100):
            await asyncio.sleep(0.1)
            if self.game.counter == 3:
                break
        self.assertEqual(self.game.counter, 3)
        self.assertNotIn(("trap", "death"), [(e[1], e[2]) for e in self.game.effects])

    async def test_the_inventory_trap_is_counted_but_not_carried_out_again_after_an_older_save_loads(self):
        await self.finish([self.client.submit("credits", "1")])
        self.game.save("old")
        await self.finish([self.client.submit("trap", "inventory"), self.client.submit("credits", "2")])
        self.assertEqual([(e[1], e[2]) for e in self.game.effects].count(("trap", "inventory")), 1)
        self.game.load("old")
        self.assertTrue(await self._wait_for(lambda: self.game.counter == 3))                    # the numbers stay in step
        self.assertEqual([(e[1], e[2]) for e in self.game.effects].count(("trap", "inventory")), 0)   # the old save did not get the trap a second time
        self.assertIn(("credits", "2"), [(e[1], e[2]) for e in self.game.effects])               # other jobs are still replayed
        self.assertEqual(self.client.stats["failed"], 0)

    async def test_class_order_is_not_replayed(self):
        """A class order is for the companions in the party at that moment: after an older save is loaded it is counted (the numbers stay in step) but not carried
        out again (found live 2026-11-15: replayed orders for slots 13 and 14 were refused, the two who were no longer in the party)."""
        await self.finish([self.client.submit("credits", "1")])
        self.game.save("old")
        await self.finish([self.client.submit("compclass", "13:0:4:11:0:0:0"), self.client.submit("credits", "2")])
        self.assertEqual(self.game.counter, 3)
        self.game.load("old")
        self.assertTrue(await self._wait_for(lambda: self.game.counter == 3))
        self.assertNotIn("compclass", [e[1] for e in self.game.effects])                    # the load restored the old save's jobs; the replay did not carry the order out again
        self.assertEqual([e[2] for e in self.game.effects if e[1] == "credits"], ["1", "2"])
        self.assertEqual(self.client.stats["failed"], 0)

    async def test_wrong_seed_fails_the_job(self):
        self.game.guard = 9
        job = self.client.submit("credits", "5")
        await self.finish([job])
        self.assertEqual(job.state, "failed")
        self.assertIn("different seed", job.fail_reason)

    async def test_refused_action_still_counts(self):
        self.game.refuse_actions = {"item"}
        a, b = self.client.submit("item", "nonexistent"), self.client.submit("credits", "5")
        await self.finish([a, b])
        self.assertEqual(self.game.counter, 2)
        self.assertEqual(a.refused[:7], "refused")

    async def test_messages_are_batched_into_one_box(self):
        jobs = [self.client.submit("item", "x%d" % i, message="You received: item %d" % i) for i in range(3)]
        await self.finish(jobs)
        sent = [j.message for j in jobs]
        self.assertEqual(sent[0], "")
        self.assertEqual(sent[1], "")
        self.assertEqual(sent[2], "You received: item 0~~You received: item 1~~You received: item 2")

    async def test_new_game_session_relearns_number(self):
        await self.finish([self.client.submit("credits", "1")])
        self.game.restart_process()
        self.game.counter = 1
        await asyncio.sleep(0.3)
        job = self.client.submit("credits", "2")
        await self.finish([job])
        self.assertEqual(self.game.counter, 2)


class TestNumbers(unittest.TestCase):
    def test_counter_math(self):
        self.assertEqual([counter_of(i) for i in (0, 1, 255, 256, 510, 511)], [0, 1, 255, 1, 255, 1])
        self.assertEqual([next_seq(c) for c in (0, 1, 254, 255)], [1, 2, 255, 1])


if __name__ == "__main__":
    unittest.main()
