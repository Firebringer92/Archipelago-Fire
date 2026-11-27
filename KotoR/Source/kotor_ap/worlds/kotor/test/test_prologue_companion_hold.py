"""
No companion recruit is sent while the player is in the Endar Spire (area indexes 0 and 1): the heavy queue holds it, nothing is logged as sent, and
the reconciler counts it as pending. It goes out once the player has entered any other area. The methods are called on a small stand-in for the
client context.
"""
import asyncio
import os
import types
import unittest

KOTOR_CLIENT = os.path.join(os.path.dirname(__file__), "..", "..", "..", "KotorClient.py")


@unittest.skipUnless(os.path.exists(KOTOR_CLIENT), "client not next to this world")
class TestPrologueCompanionHold(unittest.TestCase):
    def setUp(self):
        import KotorClient
        self.cls = KotorClient.KotorContext
        self.sent = []
        self.deliveries = {}
        ctx = types.SimpleNamespace(
            _heavy_in_hand=None,
            _current_area_idx=None,
            extender=types.SimpleNamespace(deliveries=self.deliveries),
        )
        ctx._PROLOGUE_AREA_IDXS = self.cls._PROLOGUE_AREA_IDXS
        ctx._is_companion_recruit_arm = self.cls._is_companion_recruit_arm
        ctx._in_prologue = lambda: self.cls._in_prologue(ctx)
        ctx._heavy_queue_holds = lambda arm: self.cls._heavy_queue_holds(ctx, arm)

        async def do_deliver(item_name, arm_name, index, character, *, is_correction=False):
            self.sent.append(arm_name)
            key = "companion_class:" + arm_name.split(":")[1] if arm_name.startswith("companion_class:") else arm_name
            self.deliveries[key] = types.SimpleNamespace(applied_at=1.0, rejected_at=None)

        ctx._do_deliver = do_deliver
        self.ctx = ctx

    def _run(self, area_idx, arms, then_move_to=None):
        async def go():
            self.ctx._heavy_queue = asyncio.Queue()
            self.ctx._current_area_idx = area_idx
            for i, arm in enumerate(arms):
                self.ctx._heavy_queue.put_nowait((arm, arm, i, "Rann", False))
            task = asyncio.create_task(self.cls._process_heavy_queue(self.ctx))
            await asyncio.sleep(0.3)
            before = list(self.sent)
            held = self.ctx._heavy_in_hand
            holds = self.ctx._heavy_queue_holds(arms[0])
            if then_move_to is not None:
                self.ctx._current_area_idx = then_move_to
                await asyncio.sleep(1.5)
            task.cancel()
            return before, held, holds, list(self.sent)
        return asyncio.run(go())

    def test_a_recruit_waits_in_the_first_endar_spire_area(self):
        before, held, holds, _ = self._run(0, ["companion_jolee"])
        self.assertEqual(before, [])
        self.assertEqual(held, "companion_jolee")
        self.assertTrue(holds)

    def test_a_recruit_waits_in_the_second_endar_spire_area(self):
        before, *_ = self._run(1, ["companion_bastila"])
        self.assertEqual(before, [])

    def test_a_held_recruit_goes_out_after_leaving_the_endar_spire(self):
        _, _, _, after = self._run(0, ["companion_jolee"], then_move_to=2)
        self.assertEqual(after, ["companion_jolee"])

    def test_a_recruit_is_sent_at_once_outside_the_endar_spire(self):
        before, *_ = self._run(2, ["companion_jolee"])
        self.assertEqual(before, ["companion_jolee"])

    def test_a_recruit_is_sent_when_no_area_has_been_seen_yet(self):
        before, *_ = self._run(None, ["companion_jolee"])
        self.assertEqual(before, ["companion_jolee"])

    def test_a_jedi_training_item_is_not_held(self):
        before, *_ = self._run(0, ["companion_class:jolee:consular"])
        self.assertEqual(before, ["companion_class:jolee:consular"])

    def test_which_arms_count_as_recruits(self):
        is_recruit = self.cls._is_companion_recruit_arm
        self.assertTrue(is_recruit("companion_bastila"))
        self.assertFalse(is_recruit("companion_class:bastila:guardian"))
        self.assertFalse(is_recruit("heavy_something"))


if __name__ == "__main__":
    unittest.main()
