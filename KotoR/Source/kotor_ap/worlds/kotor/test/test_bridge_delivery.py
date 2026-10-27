"""Every delivery the client makes is a dispatcher job (kotor_extender_bridge.py, _submit_job), and the delivery records the rest of the
client reads follow the job."""
import asyncio
import unittest

from kotor_dispatcher import DispatchClient
from kotor_extender_bridge import ExtenderBridge


class _Writer:
    def __init__(self):
        self.sent = []

    def write(self, data):
        self.sent.append(data)

    async def drain(self):
        return None


def _bridge():
    bridge = ExtenderBridge(on_event=lambda event: None)
    bridge._writer = _Writer()
    bridge.dispatcher = DispatchClient(bridge)
    bridge.dispatcher._ensure_pump = lambda: None     # the pump is not needed to see what was submitted
    return bridge


class TestDeliveriesAreJobs(unittest.IsolatedAsyncioTestCase):
    async def test_each_sender_becomes_one_job(self):
        bridge = _bridge()
        await bridge.send_apply("class_guardian", message="You received: Class Switch")
        await bridge.send_apply_item("ap_tk_tar1", 1)
        await bridge.send_apply_value("set_xp", 4000)
        await bridge.send_apply_value("set_credits", 0)
        await bridge.send_delevel(10, 5000, 20)
        await bridge.send_force_power(133)
        await bridge.send_companion_class("carth", "sentinel")
        await bridge.send_trap("reduce_skill", "awareness")
        await bridge.send_trap("cut_max_hp", "-")
        await bridge.send_notify("Hello there")
        queued = [(j.action, j.args) for j in bridge.dispatcher._queue]
        self.assertEqual(queued, [
            ("arm", "class_guardian"), ("give_item", "ap_tk_tar1:1"), ("set_xp", "4000"), ("set_credits", "0"),
            ("delevel", "10:5000:20"), ("force_power", "133"), ("companion_class", "carth:sentinel"),
            ("trap", "reduce_skill:awareness"), ("trap", "cut_max_hp:-"), ("notify", ""),
        ])
        self.assertEqual(bridge.dispatcher._queue[0].message, "You received: Class Switch")
        self.assertEqual(bridge._writer.sent, [])       # nothing is written to the socket until the dispatcher sends a job

    async def test_the_record_is_staged_at_once_and_settled_when_the_game_applies_it(self):
        bridge = _bridge()
        self.assertTrue(await bridge.send_apply_item("ap_tk_tar1", 1))
        record = bridge.deliveries["give_item:ap_tk_tar1"]
        self.assertIsNotNone(record.staged_at)
        self.assertIsNone(record.applied_at)
        self.assertTrue(await bridge.wait_staged("give_item:ap_tk_tar1"))
        bridge._jobs["give_item:ap_tk_tar1"].finish("applied")
        await asyncio.sleep(0.05)
        settled = bridge.deliveries["give_item:ap_tk_tar1"]
        self.assertIsNotNone(settled.applied_at)
        self.assertIsNone(bridge.rejection("give_item:ap_tk_tar1"))

    async def test_a_failed_job_is_a_rejected_delivery(self):
        bridge = _bridge()
        await bridge.send_companion_class("carth", "sentinel")
        job = bridge._jobs["companion_class:carth"]
        job.fail_reason = "the game could not apply it"
        job.finish("failed")
        await asyncio.sleep(0.05)
        self.assertEqual(bridge.rejection("companion_class:carth"), "the game could not apply it")

    async def test_a_replaced_job_leaves_the_newer_record_alone(self):
        bridge = _bridge()
        await bridge.send_apply_value("set_xp", 1000)
        old = bridge._jobs["set_xp"]
        await bridge.send_apply_value("set_xp", 2000)      # replaces the waiting one
        await asyncio.sleep(0.05)
        self.assertTrue(old.done.is_set())
        self.assertIn("set_xp", bridge.deliveries)
        self.assertEqual([(j.action, j.args) for j in bridge.dispatcher._queue], [("set_xp", "2000")])
        self.assertIsNone(bridge.rejection("set_xp"))

    async def test_nothing_is_sent_while_disconnected(self):
        bridge = _bridge()
        bridge._writer = None
        self.assertFalse(await bridge.send_apply("xp"))
        self.assertEqual(len(bridge.dispatcher._queue), 0)


class TestNoOldPathWrites(unittest.TestCase):
    """One authority per delivery: the bridge writes the dispatcher's lines and nothing the old staged-arm path used."""

    def test_the_bridge_writes_no_staged_arm_commands(self):
        import inspect
        import kotor_extender_bridge
        writes = [line.strip() for line in inspect.getsource(kotor_extender_bridge).splitlines() if "_writer.write(" in line]
        self.assertTrue(writes)
        for line in writes:
            self.assertNotIn("APPLY", line)
            self.assertNotIn("NOTIFY", line)
        joined = " ".join(writes)
        self.assertIn("DISPATCH:", joined)

    def test_the_client_starts_no_arm_queueing_of_its_own(self):
        import os
        path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "KotorClient.py")
        with open(path, encoding="utf-8") as f:
            source = f.read()
        for flag in ("--queue-", "--purge-arm", "--delivered="):
            self.assertNotIn(flag, source)
