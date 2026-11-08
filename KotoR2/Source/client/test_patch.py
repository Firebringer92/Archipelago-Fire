"""Tests of the seed file and the patcher. Run through tools/run_client_tests.py."""
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import k2_seed  # noqa: E402
from k2_patch import PAYLOAD_KEY_FILES, Patcher, find_game_dir, path_report  # noqa: E402

SLOT = {"seed_guard": 9, "level_cap": 22, "disabled_gates": ["NAR1", "FIN4"],
        "options": {"goal": 2, "goal_level": 25, "story_gates": True, "experience_mode": 2, "bazaar": False, "shop_count": 12, "death_link": True}}


class TestSeedFile(unittest.TestCase):
    def values(self, slot=SLOT):
        return dict(k2_seed.seed_values(slot))

    def test_values(self):
        v = self.values()
        self.assertEqual(v["FORMAT"], 1)
        self.assertEqual(v["SEED_GUARD"], 9)
        self.assertEqual(v["GOAL"], 2)
        self.assertEqual(v["LEVEL_CAP"], 22)
        self.assertEqual(v["STORY_GATES"], 1)
        self.assertEqual(v["BAZAAR"], 0)
        self.assertEqual(v["SHOP_COUNT"], 12)
        self.assertEqual(v["DEATH_LINK"], 1)
        self.assertEqual(v["XP_CLAMP"], 1)
        self.assertEqual(v["SKIP_TURRETS"], 1)

    def test_gate_mask(self):
        mask = self.values()["DISABLED_GATES"]
        self.assertEqual(mask, (1 << k2_seed.GATE_ORDER.index("NAR1")) | (1 << k2_seed.GATE_ORDER.index("FIN4")))
        self.assertEqual(self.values({"disabled_gates": []})["DISABLED_GATES"], 0)

    def test_defaults_for_a_bare_slot(self):
        v = self.values({})
        self.assertEqual(v["STORY_GATES"], 1)
        self.assertEqual(v["COMPANIONS"], 1)
        self.assertEqual(v["XP_CLAMP"], 0)

    def test_gate_order_matches_the_world(self):
        from worlds.kotor2.Options import DisabledGates
        self.assertEqual(set(k2_seed.GATE_ORDER), set(DisabledGates.valid_keys))
        self.assertLess(len(k2_seed.GATE_ORDER), 31)

    def test_config_lines(self):
        lines = k2_seed.config_lines(SLOT)
        self.assertEqual(len(lines), len(k2_seed.ROWS))
        self.assertIn("ap_goal=2", lines)
        self.assertIn("ap_seed_guard=9", lines)
        self.assertIn("ap_bazaar=0", lines)
        # the extender matches a key by prefix up to the '=': no key may be the start of another one followed by '='
        keys = [l.split("=")[0] for l in lines]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertLess(len("\n".join(lines)), 2000)       # config.txt holds 8191 bytes in all

    def test_2da_writer(self):
        text = k2_seed.render_2da(("Key", "Value"), [("a", 1), ("b", "")])
        self.assertEqual(text.split("\r\n"), ["2DA V2.0", "", "    Key Value", "0    a 1", "1    b ****", ""])

    def test_rows_are_unique_and_valid_script_names(self):
        keys = [k for k, _ in k2_seed.ROWS]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertTrue(all(k.replace("_", "").isalnum() and k.upper() == k for k in keys))

    def test_include_file_is_current(self):
        path = os.path.join(HERE, "..", "nss", "k2ap_seed.nss")
        with open(path, newline="") as f:
            self.assertEqual(f.read(), k2_seed.nss_include(), "run tools/build_seed_include.py")

    def test_function_names(self):
        self.assertEqual(k2_seed.func_name("SEED_GUARD"), "K2AP_SeedGuard")
        self.assertEqual(k2_seed.func_name("GOAL"), "K2AP_Goal")
        text = k2_seed.nss_include()
        self.assertIn('int K2AP_StoryGates()', text)
        self.assertIn('K2SE_ConfigInt("ap_story_gates", 0)', text)


class TestPatcher(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.game = os.path.join(self.root, "game")
        self.state = os.path.join(self.root, "state")
        os.makedirs(self.game)
        open(os.path.join(self.game, "swkotor2.exe"), "wb").close()
        self.running = False
        self.p = Patcher(self.game, self.state, running=lambda: self.running)
        self.over = os.path.join(self.game, "Override")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def read(self, name):
        return open(os.path.join(self.over, name), "rb").read()

    def test_create_then_same_then_update(self):
        r = self.p.apply({"a.2da": b"one"})
        self.assertEqual((r.created, r.changed, r.same), (["a.2da"], [], []))
        self.assertEqual(self.read("a.2da"), b"one")
        r = self.p.apply({"a.2da": b"one"})
        self.assertEqual((r.created, r.changed, r.same), ([], [], ["a.2da"]))
        r = self.p.apply({"a.2da": b"two"})
        self.assertEqual(r.changed, ["a.2da"])
        self.assertEqual(self.read("a.2da"), b"two")

    def test_relaunch_only_for_new_files_while_running(self):
        self.running = True
        r = self.p.apply({"a.2da": b"x"})
        self.assertTrue(r.relaunch_needed)
        self.assertIn("close it", r.summary())
        r = self.p.apply({"a.2da": b"y"})
        self.assertFalse(r.relaunch_needed)
        self.running = False
        r = self.p.apply({"a.2da": b"y", "b.2da": b"z"})
        self.assertFalse(r.relaunch_needed)

    def test_files_of_an_earlier_seed_are_removed(self):
        self.p.apply({"a.2da": b"1", "shop.2da": b"2"})
        r = self.p.apply({"a.2da": b"1"})
        self.assertEqual(r.removed, ["shop.2da"])
        self.assertFalse(os.path.exists(os.path.join(self.over, "shop.2da")))

    def test_foreign_file_is_backed_up_and_restored(self):
        os.makedirs(self.over)
        with open(os.path.join(self.over, "x.2da"), "wb") as f:
            f.write(b"theirs")
        r = self.p.apply({"x.2da": b"ours"})
        self.assertEqual(r.backed_up, ["x.2da"])
        self.assertEqual(self.read("x.2da"), b"ours")
        r = self.p.revert()
        self.assertEqual(self.read("x.2da"), b"theirs")
        self.assertEqual(r.removed, ["x.2da"])

    def test_an_identical_file_that_was_already_there_is_given_back_by_a_revert(self):
        os.makedirs(self.over)
        with open(os.path.join(self.over, "same.ncs"), "wb") as f:
            f.write(b"alike")
        r = self.p.apply({"same.ncs": b"alike"})
        self.assertEqual((r.same, r.created), (["same.ncs"], []))
        self.assertEqual(self.p.apply({"same.ncs": b"alike"}).same, ["same.ncs"])        # a second patch still sees it as unchanged
        self.p.revert()
        self.assertEqual(self.read("same.ncs"), b"alike")                              # not deleted: it was there before the client

    def test_revert_removes_only_ours(self):
        os.makedirs(self.over)
        with open(os.path.join(self.over, "mine.txt"), "wb") as f:
            f.write(b"keep")
        self.p.apply({"a.2da": b"1"})
        self.p.revert()
        self.assertEqual(sorted(os.listdir(self.over)), ["mine.txt"])

    def test_manifest_survives_a_new_patcher(self):
        self.p.apply({"a.2da": b"1"})
        again = Patcher(self.game, self.state, running=lambda: False)
        r = again.apply({})
        self.assertEqual(r.removed, ["a.2da"])

    def config(self):
        with open(os.path.join(self.root, "config.txt")) as f:
            return f.read()

    def test_config_block_keeps_other_lines(self):
        with open(os.path.join(self.root, "config.txt"), "w") as f:
            f.write("stage=3\nallow_memwrite=0\n")
        self.p.apply({}, config=["ap_goal=2", "ap_bazaar=0"])
        text = self.config()
        self.assertIn("stage=3\nallow_memwrite=0\n", text)
        self.assertIn("ap_goal=2\nap_bazaar=0\n", text)
        # a second seed replaces the block instead of adding to it
        self.p.apply({}, config=["ap_goal=4"])
        text = self.config()
        self.assertEqual(text.count("ap_goal"), 1)
        self.assertIn("ap_goal=4", text)
        self.assertNotIn("ap_bazaar", text)
        self.assertIn("stage=3", text)

    def test_config_is_created_and_reverted(self):
        self.p.apply({}, config=["ap_goal=2"])
        self.assertIn("ap_goal=2", self.config())
        self.p.revert()
        self.assertNotIn("ap_goal", self.config())

    def test_config_too_big_is_refused(self):
        r = self.p.apply({}, config=["ap_x%d=1" % i for i in range(2000)])
        self.assertTrue(r.errors)
        self.assertIn("8191", r.errors[0])
        self.assertFalse(os.path.exists(os.path.join(self.root, "config.txt")))

    def test_unwritable_override_reports_a_problem(self):
        open(os.path.join(self.game, "Override"), "w").close()        # a file where the folder should be
        r = self.p.apply({"a.2da": b"1"})
        self.assertTrue(r.errors)
        self.assertIn("Problems", r.summary())


class TestFindGameDir(unittest.TestCase):
    def test_finds_by_preferred_and_saved(self):
        root = tempfile.mkdtemp()
        try:
            good = os.path.join(root, "g")
            os.makedirs(good)
            open(os.path.join(good, "swkotor2.exe"), "wb").close()
            saved = os.path.join(root, "game_dir.txt")
            self.assertEqual(find_game_dir(good, saved), os.path.normpath(good))
            open(saved, "w").write(good)
            self.assertEqual(find_game_dir(os.path.join(root, "nope"), saved), os.path.normpath(good))
        finally:
            shutil.rmtree(root, ignore_errors=True)


class TestPathReport(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.game = os.path.join(self.root, "game")
        self.state = os.path.join(self.root, "K2SE", "ap")
        self.config = os.path.join(self.root, "K2SE", "config.txt")
        self.payload = os.path.join(self.root, "payload")
        os.makedirs(os.path.join(self.game, "Override"))
        os.makedirs(os.path.join(self.game, "Modules"))
        os.makedirs(self.state)
        open(os.path.join(self.game, "swkotor2.exe"), "wb").close()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def report(self):
        return path_report(self.game, self.state, self.config, self.payload, running=lambda: False)

    def wrong(self):
        return [l for l in self.report() if l.startswith("WRONG")]

    def test_an_empty_install_lists_what_is_missing(self):
        text = "\n".join(self.wrong())
        for part in ("extender", "extender config", "payload"):
            self.assertIn(part, text)

    def test_a_complete_install_has_nothing_wrong(self):
        open(os.path.join(self.game, "version.dll"), "wb").close()
        with open(self.config, "w") as f:
            f.write("disp_enable=1\n")
        os.makedirs(self.payload)
        for name in PAYLOAD_KEY_FILES:
            open(os.path.join(self.payload, name), "wb").close()
        self.assertEqual(self.wrong(), [])

    def test_a_missing_game_folder_is_the_first_line(self):
        lines = path_report(None, self.state, self.config, self.payload, running=lambda: False)
        self.assertTrue(lines[0].startswith("WRONG") and "game folder" in lines[0])

    def test_disp_enable_inside_our_block_does_not_count(self):
        with open(self.config, "w") as f:
            f.write("# --- k2ap begin (written by the Archipelago client; do not edit) ---\ndisp_enable=1\n# --- k2ap end ---\n")
        self.assertIn("disp_enable", "\n".join(self.wrong()))

    def test_stray_files_in_the_payload_are_flagged(self):
        os.makedirs(self.payload)
        open(os.path.join(self.payload, "notes.txt"), "wb").close()
        self.assertIn("notes.txt", "\n".join(self.wrong()))

    def test_research_files_in_override_are_noted_not_wrong(self):
        open(os.path.join(self.game, "Override", "k2se_craft.dlg"), "wb").close()
        notes = [l for l in self.report() if l.startswith("NOTE") and "k2se_craft.dlg" in l]
        self.assertEqual(len(notes), 1)


if __name__ == "__main__":
    unittest.main()
