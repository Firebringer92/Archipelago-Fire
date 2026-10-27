"""The dispatcher never replays a death after a save is loaded (kotor_dispatcher.py, DEATH_ARMS)."""
import unittest

from kotor_dispatcher import DispatchClient, Job, is_death_job


class _Bridge:
    is_connected = True

    async def send_dispatch(self, *args):
        return True


def _client():
    client = DispatchClient(_Bridge())
    client._ensure_pump = lambda: None   # no event loop in these tests: jobs are only queued
    return client


def _applied(client, *jobs):
    """The game counted these jobs, in order, starting after a saved number of 10."""
    client.abs_applied, client.seq = 10, 10
    for number, job in enumerate(jobs, start=11):
        job.seq = number
        client._record(job, True)
        client.seq = number


class TestDeathJobs(unittest.TestCase):
    def test_which_jobs_are_deaths(self):
        self.assertTrue(is_death_job("arm", "force_death"))
        self.assertTrue(is_death_job("arm", "force_death:now"))
        self.assertTrue(is_death_job("arm", "32"))
        self.assertTrue(is_death_job("force_death", ""))
        self.assertFalse(is_death_job("arm", "xp"))
        self.assertFalse(is_death_job("give_item", "ap_tk_tar1:1"))

    def test_a_death_is_counted_but_not_replayed_after_a_reload(self):
        client = _client()
        _applied(client, Job("give_item", "ap_tk_tar1:1"), Job("arm", "force_death"), Job("arm", "xp"))
        client._on_rollback(10)     # the game is back at the number 10: all three jobs are gone from it
        replayed = [(j.action, j.args) for j in client._queue]
        self.assertEqual(replayed, [("give_item", "ap_tk_tar1:1"), ("arm", "xp")])
        self.assertEqual(client.replayed_count, 2)

    def test_a_reload_of_only_a_death_replays_nothing(self):
        client = _client()
        _applied(client, Job("arm", "force_death"))
        client._on_rollback(10)
        self.assertEqual(len(client._queue), 0)

    def test_a_death_waiting_in_the_queue_is_dropped_by_a_reload(self):
        client = _client()
        _applied(client, Job("give_item", "ap_tk_tar1:1"))
        waiting = Job("arm", "force_death")
        client._queue.append(waiting)
        client._queue.append(Job("arm", "credits"))
        client._on_rollback(10)
        remaining = [(j.action, j.args) for j in client._queue]
        self.assertIn(("give_item", "ap_tk_tar1:1"), remaining)
        self.assertIn(("arm", "credits"), remaining)
        self.assertNotIn(("arm", "force_death"), remaining)
        self.assertTrue(waiting.done.is_set())

    def test_the_death_in_flight_is_dropped_by_a_reload(self):
        client = _client()
        _applied(client, Job("arm", "xp"))
        flying = Job("arm", "force_death")
        flying.seq = 12
        client.current = flying
        client._on_rollback(10)
        self.assertTrue(flying.done.is_set())
        self.assertEqual([(j.action, j.args) for j in client._queue], [("arm", "xp")])


class TestReplaceByKey(unittest.TestCase):
    """A correction that is sent again replaces the one still waiting; counted things never do."""

    def test_which_actions_have_a_key(self):
        from kotor_dispatcher import replace_key
        self.assertEqual(replace_key("set_xp", "5000"), "set_xp")
        self.assertEqual(replace_key("set_credits", "100"), "set_credits")
        self.assertEqual(replace_key("delevel", "10:5000:20"), "delevel")
        self.assertEqual(replace_key("companion_class", "carth:sentinel"), "companion_class:carth")
        self.assertIsNone(replace_key("arm", "xp"))
        self.assertIsNone(replace_key("give_item", "ap_tk_tar1:1"))
        self.assertIsNone(replace_key("trap", "cut_max_hp:-"))
        self.assertIsNone(replace_key("arm", "force_death"))

    def test_the_latest_value_replaces_a_waiting_one(self):
        client = _client()
        first = client.submit("set_xp", "1000")
        client.submit("arm", "xp")
        second = client.submit("set_xp", "2000")
        third = client.submit("set_xp", "3000")
        queued = [(j.action, j.args) for j in client._queue]
        self.assertEqual(queued, [("arm", "xp"), ("set_xp", "3000")])
        self.assertTrue(first.done.is_set() and second.done.is_set())
        self.assertFalse(third.done.is_set())
        self.assertEqual(client.replaced_count, 2)

    def test_counted_jobs_are_never_replaced(self):
        client = _client()
        for _ in range(3):
            client.submit("arm", "xp")
            client.submit("give_item", "ap_tk_tar1:1")
        self.assertEqual(len(client._queue), 6)

    def test_different_companions_do_not_replace_each_other(self):
        client = _client()
        client.submit("companion_class", "carth:sentinel")
        client.submit("companion_class", "jolee:guardian")
        client.submit("companion_class", "carth:guardian")
        self.assertEqual([j.args for j in client._queue], ["jolee:guardian", "carth:guardian"])

    def test_a_job_already_sent_is_left_alone(self):
        client = _client()
        sent = client.submit("set_xp", "1000")
        client._queue.popleft()
        sent.seq = 12                      # in flight: numbered and sent
        client.current = sent
        client.submit("set_xp", "2000")
        self.assertFalse(sent.done.is_set())
        self.assertEqual([j.args for j in client._queue], ["2000"])


class TestWindowText(unittest.TestCase):
    """What the client window shows about deliveries."""

    def test_nothing_waiting(self):
        client = _client()
        text = client.window_text()
        self.assertEqual(text["waiting"], "Deliveries waiting: none")
        self.assertEqual(text["failed"], "")
        self.assertEqual(text["recent"], "Recently delivered: none")

    def test_waiting_jobs_are_named_and_the_gate_is_said(self):
        client = _client()
        current = Job("give_item", "ap_tk_tar1:1", message="You received: Taris Progression 1")
        current.state, current.gate = "waiting", 16
        client.current = current
        client._queue.append(Job("arm", "companion_carth", message="You received: Companion: Carth Onasi"))
        client._queue.append(Job("set_xp", "4000"))
        for n in range(3):
            client._queue.append(Job("arm", "xp"))
        lines = client.window_text()["waiting"].split("\n")
        self.assertEqual(lines[0], "Deliveries waiting: 6")
        self.assertIn("Now: Taris Progression 1 - waiting for a calm moment (combat)", lines[1])
        self.assertEqual(lines[2], "  Next: Companion: Carth Onasi")
        self.assertEqual(lines[3], "  Next: set XP to 4000")
        self.assertEqual(lines[4], "  Next: xp")
        self.assertEqual(lines[5], "  ... and 2 more")

    def test_failures_and_recent_jobs(self):
        client = _client()
        bad = Job("companion_class", "carth:sentinel")
        client._fail(bad, "the game could not apply it")
        client.history.append(bad)
        good = Job("give_item", "ap_tk_tar1:1", message="You received: Taris Progression 1")
        good.finish("applied")
        client.history.append(good)
        text = client.window_text()
        self.assertIn("Failed (1, written to the delivery log):", text["failed"])
        self.assertIn("carth: class sentinel: the game could not apply it", text["failed"])
        self.assertTrue(text["recent"].startswith("Recently delivered:"))
        self.assertIn("Taris Progression 1", text["recent"])
        self.assertNotIn("carth", text["recent"])


class TestUnfinishedJobs(unittest.TestCase):
    """The reconciler asks before it sends a lost item again: a delivery still waiting means the item is not missing, just not applied yet."""

    def test_a_queued_or_current_job_counts_until_it_finishes(self):
        client = _client()
        job = client.submit("give_item", "ap_tk_tat2:1")
        self.assertTrue(client.has_unfinished("give_item", "ap_tk_tat2:1"))
        self.assertFalse(client.has_unfinished("give_item", "ap_tk_tat1:1"))
        client._queue.clear()
        client.current = job                  # sent to the game, waiting for a calm moment
        self.assertTrue(client.has_unfinished("give_item", "ap_tk_tat2:1"))
        job.finish("applied")
        self.assertFalse(client.has_unfinished("give_item", "ap_tk_tat2:1"))
