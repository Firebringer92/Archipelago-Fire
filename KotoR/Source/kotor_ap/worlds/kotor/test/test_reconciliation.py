"""The reconciler's XP clamp (experience modes ap_limited / ap_gated) at area entries."""
import asyncio
import unittest

from kotor_reconciliation import ReconciliationTracker


class TestXpClampAtAreaEntry(unittest.IsolatedAsyncioTestCase):
    def _tracker(self, mode):
        self.values, self.delevels = [], []

        async def send_apply(name):
            return True

        async def send_apply_value(name, value):
            self.values.append((name, value))
            return True

        async def send_delevel(level, xp, force):
            self.delevels.append((level, xp, force))
            return True

        tracker = ReconciliationTracker(send_apply, send_apply_value, send_delevel=send_delevel)
        tracker.experience_mode = mode
        tracker._xp_seen_since_reset = True
        tracker.current_scalar["xp"] = 1100       # the vanilla XP of the Endar Spire (level 2 needs 1000)
        tracker.expected_scalar["xp"] = 0         # nothing received yet
        tracker.current_level = 2
        return tracker

    async def _enter(self, tracker, idx):
        tracker.handle_event(f"AP|CHECK|AREA|{idx}|seen=0")
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    async def test_the_endar_spire_areas_are_not_clamped(self):
        for mode in (1, 2):
            tracker = self._tracker(mode)
            for idx in (0, 1):
                await self._enter(tracker, idx)
            with self.subTest(mode=mode):
                self.assertEqual((self.values, self.delevels), ([], []))

    async def test_the_first_area_after_the_endar_spire_is_clamped(self):
        for mode in (1, 2):
            tracker = self._tracker(mode)
            await self._enter(tracker, 2)
            with self.subTest(mode=mode):
                self.assertTrue(self.values or self.delevels, "the clamp must run from the first area after the Endar Spire")

    async def test_mode_off_never_clamps(self):
        tracker = self._tracker(0)
        await self._enter(tracker, 2)
        self.assertEqual((self.values, self.delevels), ([], []))


class TestCutMaxHpTrap(unittest.TestCase):
    """The Cut Max HP trap lowers base Constitution; the reconciler's baseline must follow or it grants the points back."""

    def _tracker(self):
        async def send_apply(name):
            return True

        async def send_apply_value(name, value):
            return True

        tracker = ReconciliationTracker(send_apply, send_apply_value)
        tracker._ability_baseline["con"] = 16
        return tracker

    def test_the_baseline_falls_by_the_constitution_the_trap_took(self):
        tracker = self._tracker()
        tracker.handle_event("AP|APPLIED|trap|type=cut_max_hp|maxbefore=64|maxafter=33|conbefore=16|conafter=3")
        self.assertEqual(tracker._ability_baseline["con"], 3)

    def test_two_traps_before_the_next_poll_add_up(self):
        tracker = self._tracker()
        tracker.handle_event("AP|APPLIED|trap|type=cut_max_hp|maxbefore=64|maxafter=40|conbefore=16|conafter=9")
        tracker.handle_event("AP|APPLIED|trap|type=cut_max_hp|maxbefore=40|maxafter=25|conbefore=9|conafter=5")
        self.assertEqual(tracker._ability_baseline["con"], 5)

    def test_an_older_report_without_the_constitution_leaves_the_baseline_alone(self):
        tracker = self._tracker()
        tracker.handle_event("AP|APPLIED|trap|type=cut_max_hp|maxbefore=64|maxafter=33")
        self.assertEqual(tracker._ability_baseline["con"], 16)

    def test_an_unbootstrapped_baseline_stays_unset(self):
        tracker = self._tracker()
        tracker._ability_baseline["con"] = None
        tracker.handle_event("AP|APPLIED|trap|type=cut_max_hp|maxbefore=64|maxafter=33|conbefore=16|conafter=3")
        self.assertIsNone(tracker._ability_baseline["con"])

    def test_the_game_side_trap_reports_the_constitution(self):
        """The reconciler can only follow the trap if the script that runs it prints the numbers."""
        import os
        import sys
        scripts = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "scripts")
        if not os.path.isdir(scripts):
            self.skipTest("scripts folder not next to this world")
        sys.path.insert(0, scripts)
        import generate_trampoline_batch as gtb
        text = "\n".join(gtb.build_trap_block("cut_max_hp", "-"))
        self.assertIn("conbefore=", text)
        self.assertIn("conafter=", text)
