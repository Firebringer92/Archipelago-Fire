"""
CompanionClass=jedi_companion, client side: a "Jedi Training" item is remembered as the companion's expected class again after a reconnect, and the
reconciler's correction waits while the item's own job is still pending. The methods are called on a small stand-in for the client context.
"""
import asyncio
import os
import types
import unittest

from kotor_reconciliation import ReconciliationTracker

KOTOR_CLIENT = os.path.join(os.path.dirname(__file__), "..", "..", "..", "KotorClient.py")
ARM = "companion_class:zaalbar:consular"


async def _noop(*args, **kwargs):
    return True


@unittest.skipUnless(os.path.exists(KOTOR_CLIENT), "client not next to this world")
class TestJediTrainingClient(unittest.TestCase):
    def setUp(self):
        import KotorClient
        self.module = KotorClient
        self.ctx_class = KotorClient.KotorContext
        self.jobs = []
        self.deliveries = {}
        self.ctx = types.SimpleNamespace(
            reconciler=ReconciliationTracker(_noop, _noop),
            _heavy_queue=asyncio.Queue(),
            dispatcher=types.SimpleNamespace(has_unfinished=lambda action, args: (action, args) in self.jobs),
            extender=types.SimpleNamespace(deliveries=self.deliveries),
        )
        self.ctx._heavy_queue_holds = lambda arm: self.ctx_class._heavy_queue_holds(self.ctx, arm)

    def test_a_replayed_training_item_restores_the_expected_class(self):
        self.ctx_class._reseed_expected_state(self.ctx, ARM)
        self.assertEqual(self.ctx.reconciler.companion_class_items, {"zaalbar": "consular"})

    def test_nothing_is_pending_when_nothing_was_sent(self):
        self.assertFalse(self.ctx_class._is_arm_awaiting_confirmation(self.ctx, ARM))

    def test_a_job_waiting_in_the_dispatcher_counts_as_pending(self):
        self.jobs.append(("companion_class", "zaalbar:consular"))
        self.assertTrue(self.ctx_class._is_arm_awaiting_confirmation(self.ctx, ARM))

    def test_a_different_class_for_the_same_companion_does_not_count(self):
        self.jobs.append(("companion_class", "zaalbar:guardian"))
        self.assertFalse(self.ctx_class._is_arm_awaiting_confirmation(self.ctx, ARM))

    def test_an_entry_waiting_in_the_heavy_queue_counts_as_pending(self):
        self.ctx._heavy_queue.put_nowait(("Jedi Training: Zaalbar (Consular)", ARM, 15, "Rann Mothma", False))
        self.assertTrue(self.ctx_class._is_arm_awaiting_confirmation(self.ctx, ARM))
        self.assertFalse(self.ctx_class._is_arm_awaiting_confirmation(self.ctx, "companion_class:zaalbar:guardian"))


if __name__ == "__main__":
    unittest.main()
