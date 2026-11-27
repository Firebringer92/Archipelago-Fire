"""ReconciliationTracker.has_class: the pre-send guard for a Jedi class arm looks at the first class slot only."""
import unittest

from kotor_reconciliation import ReconciliationTracker


class TestHasClassFirstSlot(unittest.TestCase):
    def _tracker(self, report):
        async def send_apply(name):
            return True

        async def send_apply_value(name, value):
            return True

        tracker = ReconciliationTracker(send_apply, send_apply_value)
        tracker.handle_event(report)
        return tracker

    def test_the_jedi_class_in_the_first_slot_counts(self):
        tracker = self._tracker("AP|CLASSREPORT|guardian=10|consular=0|sentinel=0|baseclass=3|baselevel=10")
        self.assertTrue(tracker.has_class("class_guardian"))
        self.assertFalse(tracker.has_class("class_consular"))
        self.assertFalse(tracker.has_class("class_sentinel"))

    def test_a_jedi_class_in_another_slot_does_not_count(self):
        # Guardian levels exist, but the first slot is Scout: the grant has not landed, so the self-heal must be allowed to send it.
        tracker = self._tracker("AP|CLASSREPORT|guardian=1|consular=0|sentinel=0|baseclass=1|baselevel=9")
        self.assertFalse(tracker.has_class("class_guardian"))

    def test_each_jedi_class_matches_its_own_constant(self):
        for arm, const in (("class_guardian", 3), ("class_consular", 4), ("class_sentinel", 5)):
            tracker = self._tracker(f"AP|CLASSREPORT|guardian=0|consular=0|sentinel=0|baseclass={const}|baselevel=4")
            self.assertTrue(tracker.has_class(arm), arm)

    def test_a_poll_without_the_first_slot_falls_back_to_the_level_count(self):
        tracker = self._tracker("AP|CLASSREPORT|guardian=2|consular=0|sentinel=0")
        self.assertTrue(tracker.has_class("class_guardian"))
        self.assertFalse(tracker.has_class("class_sentinel"))

    def test_non_class_arms_are_never_matched(self):
        tracker = self._tracker("AP|CLASSREPORT|guardian=1|consular=0|sentinel=0|baseclass=3|baselevel=1")
        self.assertFalse(tracker.has_class("pc_class_scout"))
        self.assertFalse(tracker.has_class("xp"))


if __name__ == "__main__":
    unittest.main()
