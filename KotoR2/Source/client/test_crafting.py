"""Tests of the crafting mode's game side (k2_crafting): the rules alone, and the table and templates built from the real game files where the game is installed.
Run through tools/run_client_tests.py."""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import k2_crafting as C  # noqa: E402

GAME = os.environ.get("K2_GAME_DIR") or r"C:\Program Files (x86)\Steam\steamapps\common\Knights of the Old Republic II"
HAVE_GAME = os.path.isfile(os.path.join(GAME, "swkotor2.exe"))
TYPES = ["armor", "ranged", "melee", "lightsaber", "other", "parts", "lab"]


class TestRules(unittest.TestCase):
    def test_ranks_follow_value_and_are_capped(self):
        self.assertEqual([C.base_rank(v) for v in (0, 249, 250, 5000, 100000)], [1, 1, 2, 21, 30])

    def test_costs_are_multiples_of_twenty_and_never_free(self):
        self.assertEqual(C.new_add_cost(0, 1.0), 20)
        self.assertEqual(C.new_add_cost(75, 1.0), 80)
        self.assertEqual(C.new_add_cost(1000, 2.0), 2000)
        self.assertEqual(C.new_add_cost(1000, 0.5), 500)
        self.assertTrue(all(C.new_add_cost(b, f) >= 20 and C.new_add_cost(b, f) % 20 == 0 for b in (0, 1, 33, 999) for f in C.COST_FACTORS))

    def test_switches_without_gating_are_all_on(self):
        plan = {"mode": 1, "gated": False, "types": TYPES}
        self.assertEqual(C.flags(plan, set()), {"ap_craft_bench": 1, "ap_craft_up": 1, "ap_craft_lab": 1})

    def test_switches_follow_the_unlocked_types(self):
        plan = {"mode": 1, "gated": True, "types": TYPES}
        self.assertEqual(C.flags(plan, set()), {"ap_craft_bench": 0, "ap_craft_up": 0, "ap_craft_lab": 0})
        self.assertEqual(C.flags(plan, {"melee"}), {"ap_craft_bench": 1, "ap_craft_up": 0, "ap_craft_lab": 0})
        self.assertEqual(C.flags(plan, {"parts", "lab"}), {"ap_craft_bench": 1, "ap_craft_up": 1, "ap_craft_lab": 1})

    def test_gating_without_a_mode_only_gates_the_game_own_crafting(self):
        plan = {"mode": 0, "gated": True, "types": ["parts", "lab"]}
        self.assertEqual(C.flags(plan, {"lab"}), {"ap_craft_bench": 0, "ap_craft_up": 0, "ap_craft_lab": 1})
        self.assertEqual(C.flags(plan, {"parts"}), {"ap_craft_bench": 1, "ap_craft_up": 1, "ap_craft_lab": 0})

    def test_no_plan_no_switches(self):
        self.assertEqual(C.flags({}, set()), {})
        self.assertEqual(C.flag_lines({}, set()), [])

    def test_flag_lines_are_config_lines(self):
        self.assertEqual(C.flag_lines({"mode": 1, "gated": False, "types": TYPES}, set()), ["ap_craft_bench=1", "ap_craft_lab=1", "ap_craft_up=1"])


@unittest.skipUnless(HAVE_GAME, "needs the game files")
class TestRealGame(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, "data", "crafting.json"), encoding="utf-8") as f:
            cls.gear = json.load(f)["gear"]

    def plan(self, mode, gated=False, seed=7):
        return {"mode": mode, "seed": seed, "gated": gated, "types": TYPES, "gear": self.gear}

    def rows(self, files):
        from pykotor.resource.formats.twoda import read_2da
        table = read_2da(files["k2se_recipes.2da"])
        return [{h: row.get_string(h) for h in table.get_headers()} for row in table]

    def uti_add_cost(self, files, resref):
        from pykotor.resource.formats.gff import read_gff
        return read_gff(files[resref + ".uti"]).root.get_uint32("AddCost")

    def test_simple_mode_adds_every_gear_row_on_the_matching_tab(self):
        files, problems = C.crafting_files(GAME, self.plan(C.SIMPLE), set())
        self.assertEqual(problems, [])
        rows = self.rows(files)
        gear = {r["label"]: r for r in rows if r["label"] in {g[0] for g in self.gear}}
        self.assertEqual(len(gear), len(self.gear))
        for resref, kind in self.gear:
            self.assertEqual(int(gear[resref]["group"]), C.TYPE_GROUP[kind], resref)
            self.assertTrue(1 <= int(gear[resref]["skill"]) <= 30)
            self.assertEqual(gear[resref]["base_skill"], str(C.REPAIR))
        self.assertGreater(len(rows), len(self.gear) + 100)                          # and the game's own rows
        self.assertTrue(all(name.endswith(".uti") or name == "k2se_recipes.2da" for name in files))
        self.assertLess(len(files), 40)                                              # simple mode only repairs templates that would build for nothing

    def test_complex_mode_raises_ranks_and_doubles_costs(self):
        simple, _ = C.crafting_files(GAME, self.plan(C.SIMPLE), set())
        files, _ = C.crafting_files(GAME, self.plan(C.COMPLEX), set())
        a = {r["label"]: int(r["skill"]) for r in self.rows(simple)}
        b = {r["label"]: int(r["skill"]) for r in self.rows(files)}
        for resref, _ in self.gear:
            self.assertEqual(b[resref], min(32, a[resref] + 6), resref)
        self.assertGreater(len(files), 300)                                          # nearly every gear template got a new AddCost
        resref = next(r for r, _ in self.gear if r + ".uti" in files)
        self.assertEqual(self.uti_add_cost(files, resref) % 20, 0)

    def test_random_mode_is_seeded_and_in_range(self):
        one, _ = C.crafting_files(GAME, self.plan(C.RANDOM, seed=1), set())
        again, _ = C.crafting_files(GAME, self.plan(C.RANDOM, seed=1), set())
        other, _ = C.crafting_files(GAME, self.plan(C.RANDOM, seed=2), set())
        self.assertEqual(one, again)
        self.assertNotEqual(self.rows(one), self.rows(other))
        self.assertTrue(all(1 <= int(r["skill"]) <= 32 for r in self.rows(one)))

    def test_gating_builds_only_the_unlocked_types(self):
        files, _ = C.crafting_files(GAME, self.plan(C.SIMPLE, gated=True), set())
        self.assertEqual(self.rows(files), [])                                       # nothing unlocked: an empty table
        files, _ = C.crafting_files(GAME, self.plan(C.SIMPLE, gated=True), {"melee"})
        labels = {r["label"] for r in self.rows(files)}
        self.assertEqual(labels, {g[0] for g in self.gear if g[1] == "melee"})
        files, _ = C.crafting_files(GAME, self.plan(C.SIMPLE, gated=True), {"parts"})
        self.assertFalse({g[0] for g in self.gear} & {r["label"] for r in self.rows(files)})
        self.assertGreater(len(self.rows(files)), 100)                               # the game's own rows

    def test_templates_are_the_same_whatever_is_unlocked(self):
        locked, _ = C.crafting_files(GAME, self.plan(C.COMPLEX, gated=True), set())
        open_, _ = C.crafting_files(GAME, self.plan(C.COMPLEX, gated=True), set(TYPES))
        self.assertEqual({k: v for k, v in locked.items() if k.endswith(".uti")}, {k: v for k, v in open_.items() if k.endswith(".uti")})

    def test_gear_gated_rows_appear_only_with_their_item(self):
        plan = dict(self.plan(C.SIMPLE), gear_gated=True)
        files, _ = C.crafting_files(GAME, plan, set(), set())
        self.assertFalse({g[0] for g in self.gear} & {r["label"] for r in self.rows(files)})
        some = {self.gear[0][0], self.gear[5][0]}
        files, _ = C.crafting_files(GAME, plan, set(), some)
        self.assertEqual({r["label"] for r in self.rows(files)} & {g[0] for g in self.gear}, some)

    def test_yields_follow_the_templates_and_the_mode(self):
        simple = C.material_yields(GAME, self.plan(C.SIMPLE))
        complex_ = C.material_yields(GAME, self.plan(C.COMPLEX))
        self.assertEqual(set(simple), {g[0] for g in self.gear})
        self.assertTrue(all(v >= 1 for v in simple.values()))
        self.assertGreater(sum(complex_.values()), sum(simple.values()))
        self.assertEqual(C.yield_of(0), 1)
        self.assertEqual(C.yield_of(5800), 29)

    def test_no_mode_builds_nothing(self):
        self.assertEqual(C.crafting_files(GAME, {"mode": 0, "gated": True, "seed": 1, "types": ["parts", "lab"], "gear": []}, set()), ({}, []))


if __name__ == "__main__":
    unittest.main()
