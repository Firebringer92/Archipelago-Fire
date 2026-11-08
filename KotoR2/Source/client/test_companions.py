"""Tests of the companion class planner (no game, no server). Run through tools/run_client_tests.py."""
import os
import random
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from k2_companions import CompanionPlanner, parse_cc  # noqa: E402


def planner(**data):
    slot = {"options": data.pop("options", {})}
    slot.update(data)
    return CompanionPlanner(slot, data.get("prestige_slots", ()), random.Random(1))


class TestParse(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_cc("0:3:5:255:0,6:4:7:11:2"), {0: (3, 5, 255, 0), 6: (4, 7, 11, 2)})
        self.assertEqual(parse_cc(""), {})
        self.assertEqual(parse_cc("x:1:2:3:4,1:2:3"), {})


class TestAssignedClass(unittest.TestCase):
    def test_wrong_class_is_converted_at_the_players_level(self):
        p = planner(companion_classes={"0": {"class": 3, "mode": 0}})
        self.assertEqual(p.orders({0: (0, 2, 255, 0)}, 12, 50), [(0, "0:0:3:12:0:0:0")])

    def test_right_class_and_level_means_no_order(self):
        p = planner(companion_classes={"0": {"class": 3, "mode": 0}})
        self.assertEqual(p.orders({0: (3, 12, 255, 0)}, 12, 50), [])

    def test_right_class_but_behind_the_player_is_raised(self):
        p = planner(companion_classes={"0": {"class": 3, "mode": 0}})
        self.assertEqual(p.orders({0: (3, 8, 255, 0)}, 12, 50), [(0, "0:0:3:12:0:0:0")])

    def test_never_lowers_a_level(self):
        p = planner(companion_classes={"0": {"class": 3, "mode": 0}})
        self.assertEqual(p.orders({0: (0, 20, 255, 0)}, 12, 50), [(0, "0:0:3:20:0:0:0")])

    def test_strip_and_race_travel_with_the_order(self):
        p = planner(companion_classes={"7": {"class": 6, "mode": 1, "race": 5, "look": 66}})
        self.assertEqual(p.orders({7: (2, 3, 255, 0)}, 3, 50), [(7, "7:0:6:3:1:5:0")])

    def test_unassigned_companions_are_left_alone_without_experience_modes(self):
        p = planner(companion_classes={"0": {"class": 3, "mode": 0}})
        self.assertEqual(p.orders({1: (9, 2, 255, 0)}, 12, 50), [])

    def test_no_order_before_the_game_reports_a_player_level(self):
        p = planner(companion_classes={"0": {"class": 3, "mode": 0}})
        self.assertEqual(p.orders({0: (0, 2, 255, 0)}, 0, 50), [(0, "0:0:3:2:0:0:0")])      # the level stays; the class still changes


class TestExperienceRaising(unittest.TestCase):
    def test_default_companions_follow_the_players_level_when_experience_is_on(self):
        p = planner(options={"experience_mode": 2})
        self.assertEqual(p.orders({1: (9, 4, 255, 0)}, 10, 50), [(1, "1:0:9:10:0:0:0")])

    def test_not_when_it_is_off(self):
        p = planner(options={"experience_mode": 0})
        self.assertFalse(p.active())
        self.assertEqual(p.orders({1: (9, 4, 255, 0)}, 10, 50), [])


class TestSecondClass(unittest.TestCase):
    def test_added_at_fifteen_character_levels(self):
        p = planner(companion_second_class={"0": 9})
        self.assertEqual(p.orders({0: (0, 14, 255, 0)}, 14, 50), [])
        self.assertEqual(p.orders({0: (0, 15, 255, 0)}, 15, 50), [(0, "0:1:9:1:0:0:0")])

    def test_skipped_when_it_equals_the_first_class_or_is_already_there(self):
        p = planner(companion_second_class={"0": 0})
        self.assertEqual(p.orders({0: (0, 20, 255, 0)}, 20, 50), [])
        p = planner(companion_second_class={"0": 9})
        self.assertEqual(p.orders({0: (0, 15, 9, 1)}, 16, 50), [])


class TestPrestige(unittest.TestCase):
    def pl(self):
        return planner(companion_prestige_pairs={"6": [13, 16]}, prestige_slots={6})

    def test_waits_for_fifteen_levels(self):
        self.assertEqual(self.pl().orders({6: (4, 14, 255, 0)}, 14, 80), [])

    def test_light_side_for_a_light_alignment_dark_for_a_dark_one(self):
        self.assertEqual(self.pl().orders({6: (4, 15, 255, 0)}, 15, 80), [(6, "6:1:13:1:0:0:0")])
        self.assertEqual(self.pl().orders({6: (4, 15, 255, 0)}, 15, 20), [(6, "6:1:16:1:0:0:0")])

    def test_neutral_alignment_picks_a_side_at_random(self):
        sides = {self.pl().orders({6: (4, 15, 255, 0)}, 15, 50)[0][1] for _ in range(1)}
        p = planner(companion_prestige_pairs={"6": [13, 16]}, prestige_slots={6})
        seen = {p.orders({6: (4, 15, 255, 0)}, 15, 50)[0][1] for _ in range(40)}
        self.assertEqual(seen, {"6:1:13:1:0:0:0", "6:1:16:1:0:0:0"})

    def test_only_once_and_only_with_the_item(self):
        self.assertEqual(self.pl().orders({6: (4, 15, 13, 1)}, 16, 80), [])
        p = planner(companion_prestige_pairs={"6": [13, 16]}, prestige_slots=set())
        self.assertEqual(p.orders({6: (4, 20, 255, 0)}, 20, 80), [])


class TestExtras(unittest.TestCase):
    def test_an_extra_is_raised_to_the_players_level_and_keeps_its_class(self):
        p = planner(extras=[{"slot": 12}, {"slot": 13}])
        self.assertTrue(p.active())
        self.assertEqual(p.orders({12: (5, 1, 255, 0)}, 7, 50), [(12, "12:0:5:7:0:0:0")])
        self.assertEqual(p.orders({12: (5, 7, 255, 0)}, 7, 50), [])
        self.assertEqual(p.orders({13: (0, 9, 255, 0)}, 7, 50), [])


if __name__ == "__main__":
    unittest.main()
