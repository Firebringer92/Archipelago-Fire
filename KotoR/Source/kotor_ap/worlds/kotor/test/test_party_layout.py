"""The 32-slot party selection layout (scripts/party_layout.py): the recipe is numbers only, and the layout built from the game's own file has everything the
extender's paged screen binds by tag."""
import json
import os
import sys
import unittest

SCRIPTS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "scripts"))
GAME = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"


def _recipe():
    with open(os.path.join(SCRIPTS, "party_layout.json"), encoding="utf-8") as f:
        return json.load(f)


@unittest.skipUnless(os.path.isdir(SCRIPTS), "scripts folder not next to this world")
class TestRecipe(unittest.TestCase):
    def test_every_control_the_screen_binds_is_in_the_recipe(self):
        tags = [c["tag"] for c in _recipe()["controls"]]
        self.assertEqual(len(tags), len(set(tags)))
        for i in range(16):
            for prefix in ("BTN_NPC", "LBL_CHAR", "LBL_NA"):
                self.assertIn(f"{prefix}{i}", tags)
        for tag in ("BTN_PAGE_PREV", "BTN_PAGE_NEXT", "BTN_DONE", "BTN_ACCEPT", "BTN_BACK"):
            self.assertIn(tag, tags)

    def test_the_extender_looks_for_tags_that_exist(self):
        """LayoutReady() in extender/src_k1se/party32.cpp refuses a layout without these."""
        tags = {c["tag"] for c in _recipe()["controls"]}
        sys.path.insert(0, SCRIPTS)
        import party_layout
        self.assertTrue(set(party_layout.REQUIRED_TAGS) <= tags)

    def test_new_controls_name_a_stock_control_to_copy(self):
        stock = {"LBL_CHAR0", "LBL_CHAR1", "LBL_CHAR2", "LBL_CHAR3", "LBL_CHAR4", "LBL_CHAR5", "LBL_CHAR6", "LBL_CHAR7", "LBL_CHAR8", "BTN_NPC0", "BTN_NPC8",
                 "LBL_NA0", "LBL_NA8", "BTN_DONE", "BTN_BACK", "BTN_ACCEPT", "LBL_3D", "LBL_TITLE"}
        for entry in _recipe()["controls"]:
            if "from" in entry:
                with self.subTest(tag=entry["tag"]):
                    self.assertIn(entry["from"].split("_")[0], ("LBL", "BTN"))
                    self.assertIn(entry["from"], {f"{p}{i}" for p in ("LBL_CHAR", "BTN_NPC", "LBL_NA") for i in range(9)} | stock)

    def test_the_recipe_holds_no_text_of_the_game(self):
        """Only numbers, the names of resources (textures, fonts) and the tags: no dialogue, no strings the game shows."""
        for entry in _recipe()["controls"]:
            for path, (_kind, value) in entry["set"].items():
                if path.endswith("TEXT/TEXT"):
                    self.assertIn(value, ("<", ">", ""), path)


@unittest.skipUnless(os.path.isdir(GAME) and os.path.isdir(SCRIPTS), "needs a KOTOR 1 install")
class TestBuiltFromTheGame(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, SCRIPTS)
        import build_game_assets
        import party_layout
        from pykotor.resource.formats.gff import read_gff
        data = party_layout.build(build_game_assets.GameData(GAME))["partyselection.gui"]
        cls.root = read_gff(data).root
        cls.controls = {str(c.get_string("TAG")): c for c in cls.root.get_list("CONTROLS")}

    def test_it_has_110_controls_and_the_two_page_buttons(self):
        self.assertEqual(len(self.controls), 110)
        self.assertIn("BTN_PAGE_PREV", self.controls)
        self.assertIn("BTN_PAGE_NEXT", self.controls)

    def test_the_sixteen_slots_form_a_grid_of_four_columns(self):
        lefts, tops = set(), set()
        for i in range(16):
            extent = self.controls[f"BTN_NPC{i}"].get_struct("EXTENT")
            lefts.add(extent.get_int32("LEFT"))
            tops.add(extent.get_int32("TOP"))
            self.assertEqual((extent.get_int32("WIDTH"), extent.get_int32("HEIGHT")), (63, 63))
        self.assertEqual(len(lefts), 4)
        self.assertEqual(len(tops), 4)

    def test_every_slot_has_a_label_over_its_button(self):
        for i in range(16):
            a = self.controls[f"BTN_NPC{i}"].get_struct("EXTENT")
            for prefix in ("LBL_CHAR", "LBL_NA"):
                b = self.controls[f"{prefix}{i}"].get_struct("EXTENT")
                self.assertEqual((a.get_int32("LEFT"), a.get_int32("TOP")), (b.get_int32("LEFT"), b.get_int32("TOP")))

    def test_the_top_level_of_the_game_file_is_kept(self):
        for label in ("TAG", "EXTENT", "ALPHA", "BORDER", "COLOR"):
            self.assertTrue(self.root.exists(label))
