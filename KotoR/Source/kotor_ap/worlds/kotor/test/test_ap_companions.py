"""AP companions: the seeded plan (names from the players, looks without repeats, portraits of the same sex) and the world scenarios that use it."""
import random
import unittest

from ..ApCompanions import AP_CLASSES, AP_COMPANION_FIRST_SLOT, AP_COMPANION_MAX, AP_LOOKS, AP_PORTRAITS, build_plan
from ..Items import EXTRA_COMPANIONS, item_table
from .test_generation import KotorScenario


class TestPlan(unittest.TestCase):
    def test_names_come_from_the_players_in_order_and_repeat_with_a_number(self):
        plan = build_plan(random.Random(1), ["Ann", "Bo"], 5)
        self.assertEqual([p["name"] for p in plan], ["Ann", "Bo", "Ann 2", "Bo 2", "Ann 3"])

    def test_slots_follow_the_extra_companions_and_are_in_order(self):
        plan = build_plan(random.Random(2), ["Ann"], 4)
        self.assertEqual([p["slot"] for p in plan], [15, 16, 17, 18])
        self.assertGreater(AP_COMPANION_FIRST_SLOT, max(slot for _label, slot, _t in EXTRA_COMPANIONS.values()))

    def test_looks_do_not_repeat_within_the_pool(self):
        plan = build_plan(random.Random(3), ["Ann"], AP_COMPANION_MAX)
        rows = [p["appearance"] for p in plan]
        self.assertEqual(len(rows), len(set(rows)))
        self.assertTrue(set(rows) <= {row for row, _g in AP_LOOKS})

    def test_each_entry_is_complete_and_consistent(self):
        for k, p in enumerate(build_plan(random.Random(4), ["Ann", "Bo", "Cy"], AP_COMPANION_MAX), start=1):
            with self.subTest(n=k):
                self.assertEqual(p["n"], k)
                self.assertEqual(p["template"], f"p_apc{k}")
                self.assertEqual(p["tag"], f"apl{p['appearance']}x{k}")
                self.assertIn(p["class"], AP_CLASSES)
                self.assertIn(p["portrait"], AP_PORTRAITS[p["gender"]])
                self.assertEqual(dict(AP_LOOKS)[p["appearance"]], p["gender"])
                self.assertLessEqual(len(p["tag"]), 32)     # a tag holds 32 characters

    def test_the_same_seed_gives_the_same_plan(self):
        self.assertEqual(build_plan(random.Random(5), ["Ann", "Bo"], 6), build_plan(random.Random(5), ["Ann", "Bo"], 6))

    def test_the_count_is_capped_and_zero_gives_nothing(self):
        self.assertEqual(build_plan(random.Random(6), ["Ann"], 0), [])
        self.assertEqual(len(build_plan(random.Random(6), ["Ann"], 99)), AP_COMPANION_MAX)

    def test_names_are_cut_to_twenty_characters(self):
        self.assertEqual(len(build_plan(random.Random(7), ["x" * 40], 1)[0]["name"]), 20)

    def test_no_name_at_all_still_gives_a_name(self):
        self.assertTrue(build_plan(random.Random(8), [], 1)[0]["name"])


class TestApCompanionItems(unittest.TestCase):
    def test_the_items_are_static_and_name_their_slot_and_template(self):
        for n in range(1, AP_COMPANION_MAX + 1):
            with self.subTest(n=n):
                data = item_table[f"AP Companion {n}"]
                self.assertEqual(data.arm_name, f"extra_companion:{14 + n}:p_apc{n}")

    def test_item_codes_do_not_clash_with_any_other_item(self):
        codes = [d.code for d in item_table.values()]
        self.assertEqual(len(codes), len(set(codes)))


class TestApCompanionsInAWorld(KotorScenario):
    options = {"companion_mode": 0, "ap_companions": 3, "extra_companions": ["Calo Nord"]}
    expected_items = ("AP Companion 1", "AP Companion 2", "AP Companion 3", "Extra Companion: Calo Nord")
    forbidden_items = ("AP Companion 4",)

    def test_the_plan_reaches_the_client_and_names_the_only_player(self):
        plan = self.world.fill_slot_data()["ap_companions"]
        self.assertEqual([p["slot"] for p in plan], [15, 16, 17])
        self.assertEqual(plan[0]["name"], self.world.player_name[:20])
        self.assertEqual(plan[1]["name"], f"{self.world.player_name[:20]} 2")


class TestApCompanionsOff(KotorScenario):
    options = {"companion_mode": 0}
    forbidden_items = tuple(f"AP Companion {n}" for n in range(1, AP_COMPANION_MAX + 1))

    def test_nothing_is_sent(self):
        self.assertEqual(self.world.fill_slot_data()["ap_companions"], [])


class TestApCompanionsNoCompanions(KotorScenario):
    options = {"companion_mode": 2, "ap_companions": 8}
    forbidden_items = tuple(f"AP Companion {n}" for n in range(1, AP_COMPANION_MAX + 1))

    def test_nothing_is_sent(self):
        self.assertEqual(self.world.fill_slot_data()["ap_companions"], [])


class TestApCompanionsAll(KotorScenario):
    options = {"companion_mode": 0, "ap_companions": 8, "extra_companions": ["Mystery Companion", "Darth Malak", "Calo Nord", "Yuthura Ban", "Darth Bandon", "Trask Ulgo"]}
    expected_items = tuple(f"AP Companion {n}" for n in range(1, 9))

    def test_all_fourteen_slots_are_distinct(self):
        data = self.world.fill_slot_data()
        slots = [c["slot"] for c in data["extra_companions"]] + [c["slot"] for c in data["ap_companions"]]
        self.assertEqual(sorted(slots), list(range(9, 23)))
