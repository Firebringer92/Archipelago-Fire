"""Tests of the extra companions' helpers and the droid templates. The builders that read the game's files run only where the game is installed.
Run through tools/run_client_tests.py."""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import k2_extras as X  # noqa: E402

GAME = os.environ.get("K2_GAME_DIR") or r"C:\Program Files (x86)\Steam\steamapps\common\Knights of the Old Republic II"
HAVE_GAME = os.path.isfile(os.path.join(GAME, "swkotor2.exe"))
with open(os.path.join(ROOT, "data", "extra_companions.json"), encoding="utf-8") as f:
    DATA = json.load(f)
PLAN = [dict(e, slot=12 + i, item="Companion: " + e["name"]) for i, e in enumerate(DATA["extras"])]


class TestHelpers(unittest.TestCase):
    def test_template_names(self):
        self.assertEqual(X.template_name(12), "apxc12")

    def test_named_items_find_their_entry(self):
        self.assertEqual(X.extra_for_item(PLAN, "Companion: Juhani")["slot"], 15)
        self.assertIsNone(X.extra_for_item(PLAN, "Companion: Atton Rand"))

    def test_ap_items_take_the_next_generated_companion(self):
        plan = PLAN + [{"slot": 24, "kind": "ap", "name": "A"}, {"slot": 25, "kind": "ap", "name": "B"}]
        self.assertEqual(X.extra_for_item(plan, "AP Companion")["slot"], 24)
        self.assertEqual(X.extra_for_item(plan, "AP Companion", {24})["slot"], 25)
        self.assertIsNone(X.extra_for_item(plan, "AP Companion", {24, 25}))

    def test_the_data_file_is_complete(self):
        names = [e["name"] for e in DATA["extras"]]
        self.assertEqual(len(names), 12)
        self.assertEqual(len(set(names)), 12)
        self.assertEqual(sum(1 for e in DATA["extras"] if e["kind"] == "k1"), 7)
        for e in DATA["extras"]:
            for key in ("appearance", "portrait", "gender", "class", "fallback_appearance", "fallback_portrait"):
                self.assertIn(key, e, e["name"])
            self.assertNotIn("source", e)                                  # every extra is built from the one generic base, not from the character's own template
            female, male = DATA["portraits"]["female"], DATA["portraits"]["male"]
            if e["kind"] != "k1":
                self.assertIn(e["portrait"], female if e["gender"] else male, e["name"])
            self.assertIn(e["fallback_portrait"], female if e["gender"] else male, e["name"])      # no other companion's face when the K1 portrait is missing

    def test_the_base_and_the_look_method(self):
        self.assertEqual(DATA["base"], X.BASE_TEMPLATE)
        self.assertIn(DATA["look_method"], ("disguise", "template"))

    def test_the_pool_of_looks_holds_no_story_companion_and_the_portraits_are_shared_by_sex(self):
        companions = {451, 452, 453, 454, 455, 456, 457, 462, 463, 511, 561, 639}                  # the story companions' own appearance rows (and the unhelmeted Mandalore)
        rows = [l["appearance"] for l in DATA["ap_looks"]]
        self.assertEqual(len(rows), len(set(rows)))
        self.assertGreaterEqual(len(rows), 8)                                                      # at most eight generated companions: none repeats
        self.assertFalse(companions & set(rows))
        self.assertTrue({l["gender"] for l in DATA["ap_looks"]} == {0, 1})
        self.assertEqual(len(set(DATA["portraits"]["female"]) | set(DATA["portraits"]["male"])), len(DATA["portraits"]["female"]) + len(DATA["portraits"]["male"]))

    def test_look_lines_name_the_disguised_slots_with_the_look_that_will_be_used(self):
        plan = [{"slot": 12, "kind": "k1", "appearance": 4, "portrait": 33, "fallback_appearance": 30, "fallback_portrait": 1, "look_method": "disguise"},
                {"slot": 13, "kind": "ap", "appearance": 48, "portrait": 18, "fallback_appearance": 48, "fallback_portrait": 18, "look_method": "disguise"},
                {"slot": 14, "kind": "ap", "appearance": 47, "portrait": 1, "fallback_appearance": 47, "fallback_portrait": 1, "look_method": "template"}]
        self.assertEqual(X.look_lines(plan, lambda e: True), ["ap_look_12=4", "ap_look_13=48"])
        self.assertEqual(X.look_lines(plan, lambda e: False), ["ap_look_12=30", "ap_look_13=48"])              # no K1 models: the generic look
        self.assertEqual(X.look_lines([], lambda e: True), [])

    def test_the_script_reads_the_rows_the_client_writes_for_the_creatures_the_client_builds(self):
        with open(os.path.join(ROOT, "nss", "k2ap_comp.nss"), encoding="utf-8") as f:
            source = f.read()
        body = source[source.index("int K2AP_LookEnforce"):]
        self.assertIn('"ap_look_" + IntToString(nSlot)', body)
        self.assertIn('"apxc" + IntToString(nSlot)', body)
        self.assertIn("nSlot = X.BASE_SLOT; nSlot < 32".replace("X.BASE_SLOT", "12"), body)
        self.assertEqual(X.template_name(12), "apxc12")
        self.assertEqual(X.look_lines([{"slot": 12, "kind": "ap", "appearance": 48, "portrait": 1, "fallback_appearance": 48, "fallback_portrait": 1}], lambda e: True),
                         ["ap_look_12=48"])
        with open(os.path.join(ROOT, "nss", "k2se_disp.nss"), encoding="utf-8") as f:
            self.assertIn("K2AP_LookEnforce();", f.read())

    def test_the_droid_slots_are_not_in_the_template_table(self):
        self.assertEqual(set(X.COMPANION_TEMPLATES), {0, 1, 2, 4, 6, 7, 9, 10, 11})


@unittest.skipUnless(HAVE_GAME, "needs the game files")
class TestBuildersAgainstTheGame(unittest.TestCase):
    def test_every_extra_builds_and_reads_back(self):
        from pykotor.resource.formats.gff import read_gff
        files, problems = X.build_templates(GAME, PLAN, lambda e: True)
        self.assertEqual(problems, [])
        self.assertEqual(sorted(files), sorted("apxc%d.utc" % e["slot"] for e in PLAN))
        for entry in PLAN:
            root = read_gff(files["apxc%d.utc" % entry["slot"]]).root
            self.assertEqual(root.get_string("Tag"), "apxc%d" % entry["slot"])
            self.assertEqual(str(root.get_resref("Conversation")), "")
            self.assertEqual([c.get_int16("ClassLevel") for c in root.get_list("ClassList")][0], 1)
            self.assertEqual(root.get_uint16("Appearance_Type"), 452)                       # the generic base's body: the look is a disguise (look_method)
            self.assertEqual(root.get_uint16("PortraitId"), entry["portrait"])
            self.assertEqual(root.get_uint8("Gender"), entry["gender"])

    def test_the_template_method_writes_the_look_into_the_template(self):
        from pykotor.resource.formats.gff import read_gff
        plan = [dict(e, look_method="template") for e in PLAN]
        files, problems = X.build_templates(GAME, plan, lambda e: True)
        self.assertEqual(problems, [])
        for entry in plan:
            self.assertEqual(read_gff(files["apxc%d.utc" % entry["slot"]]).root.get_uint16("Appearance_Type"), entry["appearance"])

    def test_every_look_row_exists_and_a_look_that_shows_armour_has_a_body_with_a_head(self):
        from pykotor.extract.installation import Installation
        from pykotor.resource.formats.twoda import read_2da
        from pykotor.resource.type import ResourceType
        table = read_2da(Installation(GAME).resource("appearance", ResourceType.TwoDA).data)
        rows = [(l["appearance"], l["armor"]) for l in DATA["ap_looks"]] + [(e["fallback_appearance"], None) for e in DATA["extras"] if e["kind"] == "k1"]
        for row, armor in rows:
            kind = table.get_cell(row, "modeltype")
            self.assertTrue(kind in ("B", "F"), "row %d is of type %s" % (row, kind))
            if armor is not None:
                self.assertEqual(kind == "B", armor, "row %d: armor flag %s but model type %s" % (row, armor, kind))

    def test_the_generic_portraits_exist(self):
        from pykotor.extract.installation import Installation
        from pykotor.resource.formats.twoda import read_2da
        from pykotor.resource.type import ResourceType
        inst = Installation(GAME)
        table = read_2da(inst.resource("portraits", ResourceType.TwoDA).data)
        for row in DATA["portraits"]["female"] + DATA["portraits"]["male"]:
            self.assertTrue(inst.texture(table.get_cell(row, "baseresref")) is not None, "portrait row %d has no image" % row)

    def test_without_the_k1_models_a_k1_character_takes_the_fallback_look(self):
        from pykotor.resource.formats.gff import read_gff
        entry = dict(PLAN[0])
        files, problems = X.build_templates(GAME, [entry], lambda e: False)
        root = read_gff(files["apxc12.utc"]).root
        self.assertEqual(root.get_uint16("PortraitId"), entry["fallback_portrait"])
        files, problems = X.build_templates(GAME, [dict(entry, look_method="template")], lambda e: False)
        self.assertEqual(read_gff(files["apxc12.utc"]).root.get_uint16("Appearance_Type"), entry["fallback_appearance"])

    def test_droid_templates_keep_everything_but_race_and_look(self):
        from pykotor.resource.formats.gff import read_gff
        plan = {"0": {"class": 7, "mode": 1, "race": 5, "look": 63}, "3": {"class": 6, "mode": 1, "race": 5, "look": 66}, "6": {"class": 0, "mode": 1}}
        files, problems = X.build_droid_templates(GAME, plan)
        self.assertEqual(problems, [])
        self.assertEqual(sorted(files), ["p_atton.utc"])         # slot 3 is a droid already, slot 6 has no look
        root = read_gff(files["p_atton.utc"]).root
        self.assertEqual((root.get_uint16("Appearance_Type"), root.get_uint8("Race"), root.get_string("Tag")), (63, 5, "Atton"))


if __name__ == "__main__":
    unittest.main()
