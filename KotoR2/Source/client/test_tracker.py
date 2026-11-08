"""Tests of the check tracker against the real generated location data. Run: python client/test_tracker.py"""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from k2_tracker import Tracker  # noqa: E402

DATA = json.load(open(os.path.join(HERE, "..", "data", "locations.json")))
SPECS = {l["id"]: {k: v for k, v in l.items() if k not in ("id", "requires", "progression", "only_if_option")} for l in DATA["locations"]}
BY_NAME = {l["name"]: l["id"] for l in DATA["locations"]}


class TestTracker(unittest.TestCase):
    def setUp(self):
        self.t = Tracker(SPECS)

    def test_area_and_level(self):
        self.assertEqual(self.t.handle("V|102PER"), {BY_NAME["Visited: Peragus - Mining Tunnels"]})
        self.assertEqual(self.t.handle("V|102PER"), set())          # only once
        hit = self.t.handle("L|4")
        self.assertEqual(hit, {BY_NAME["Level 2"], BY_NAME["Level 3"], BY_NAME["Level 4"]})

    def test_alignment_and_history(self):
        hit = self.t.handle("A|85")
        self.assertIn(BY_NAME["Alignment: Light Side 80"], hit)
        self.assertNotIn(BY_NAME["Alignment: Fallen Jedi"], hit)
        hit = self.t.handle("A|15")
        self.assertIn(BY_NAME["Alignment: Dark Side 10"] if False else BY_NAME["Alignment: Dark Side 20"], hit)
        self.assertIn(BY_NAME["Alignment: Fallen Jedi"], hit)

    def test_quest_by_stage(self):
        qid = BY_NAME["Quest: Arrested!"]
        spec = SPECS[qid]
        low = self.t.handle("Q|%s=%d" % (spec["journal_tag"], max(0, spec["target"] - 1)))
        self.assertNotIn(qid, low)
        self.assertIn(qid, self.t.handle("Q|%s=%d" % (spec["journal_tag"], spec["target"])))

    def test_influence_pair_fires_both(self):
        hit = self.t.handle("I|7=80")                  # Mira 80
        self.assertEqual(hit, {BY_NAME["Influence: Mira"], BY_NAME["Influence: Hanharr"]})

    def test_recruit_pair(self):
        hit = self.t.handle("R|4")                     # Handmaiden
        self.assertEqual(hit, {BY_NAME["Companion Recruited: Handmaiden"], BY_NAME["Companion Recruited: Disciple"]})

    def test_bazaar_counts(self):
        hit = self.t.handle("B|2|1")
        self.assertEqual(len(hit), 3)

    def test_victory(self):
        self.t.handle("X|victory")
        self.assertTrue(self.t.victory)

    def test_garbage_is_ignored(self):
        self.assertEqual(self.t.handle("Q|nonsense"), set())
        self.assertEqual(self.t.handle("L|abc"), set())


class TestGoals(unittest.TestCase):
    def test_level_goal_fires_from_the_level_check(self):
        t = Tracker(SPECS, goal={"type": "level", "level": 5})
        t.handle("L|4")
        self.assertFalse(t.victory)
        t.handle("L|5")
        self.assertTrue(t.victory)

    def test_kreia_goal_ignores_other_goal_signals(self):
        t = Tracker(SPECS, goal={"type": "nihilus"})
        t.handle("X|victory")                       # the Kreia ending does not end a Nihilus goal
        self.assertFalse(t.victory)
        t.handle("Q|DefeatDarthNihilus=60")
        self.assertFalse(t.victory)
        t.handle("Q|DefeatDarthNihilus=99")
        self.assertTrue(t.victory)

    def test_influence_goal_counts_checks(self):
        t = Tracker(SPECS, goal={"type": "influence", "count": 2})
        t.handle("I|0=80")
        self.assertFalse(t.victory)
        t.handle("I|3=20")
        self.assertTrue(t.victory)

    def test_cult_goal_needs_every_recruit_and_the_items(self):
        t = Tracker(SPECS, goal={"type": "cult", "items": ["Companion: Atton Rand"]})
        for slot in range(12):
            t.handle("R|%d" % slot)
        self.assertFalse(t.victory)                 # item not received yet
        t.note_item("Companion: Atton Rand")
        self.assertTrue(t.victory)


class TestItemLog(unittest.TestCase):
    def test_new_kept_and_lost_items(self):
        import tempfile
        from k2_tracker import ItemLog
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "items_seen.csv")
            log = ItemLog(path)
            self.assertTrue(log.update(ItemLog.parse("Comlink~Comlink,c1_key~Apartment C1 Passkey"), "101PER"))
            self.assertFalse(log.update(ItemLog.parse("Comlink~Comlink,c1_key~Apartment C1 Passkey"), "101PER"))      # nothing new: no write
            self.assertTrue(log.update(ItemLog.parse("Comlink~Comlink"), "203TEL"))                                   # the key left the inventory
            self.assertEqual(log.rows["c1_key"]["held"], "0")
            self.assertEqual(log.rows["c1_key"]["lost_module"], "203TEL")
            self.assertEqual(log.rows["Comlink"]["first_module"], "101PER")
            self.assertTrue(log.update({}, "204TEL"))                                                                 # nothing held at all
            self.assertTrue(log.update(ItemLog.parse("c1_key~Apartment C1 Passkey"), "204TEL"))                       # held again
            self.assertEqual(log.rows["c1_key"]["held"], "1")
            again = ItemLog(path)                                                                                     # survives a restart
            self.assertEqual(sorted(again.rows), ["Comlink", "c1_key"])
            self.assertEqual(again.rows["Comlink"]["held"], "0")

    def test_parse_keeps_names_with_spaces_and_skips_blanks(self):
        from k2_tracker import ItemLog
        self.assertEqual(ItemLog.parse("a~Name With Spaces,,b~"), {"a": "Name With Spaces", "b": ""})
        self.assertEqual(ItemLog.parse(""), {})


if __name__ == "__main__":
    unittest.main()
