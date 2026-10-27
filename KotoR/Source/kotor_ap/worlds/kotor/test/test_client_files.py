"""
client_files.py records the files the client writes into Override while connected and removes them on Uninstall and /ap_restore_all. It must remove exactly what was written, only while
it is still what was written, and never touch a file that was already there.
"""
import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
import client_files as cf  # noqa: E402


class Game:
    """A throwaway game folder with an Override folder, and the module's state file pointed into it."""

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.override = os.path.join(self.dir, "Override")
        os.makedirs(self.override)
        self._state = (cf.STATE_DIR, cf.STATE_PATH)
        cf.STATE_DIR = os.path.join(self.dir, "state")
        cf.STATE_PATH = os.path.join(cf.STATE_DIR, "client_files.json")
        return self

    def __exit__(self, *exc):
        cf.STATE_DIR, cf.STATE_PATH = self._state
        self.tmp.cleanup()

    def write(self, name, data=b"x"):
        with open(os.path.join(self.override, name), "wb") as f:
            f.write(data)

    def has(self, name):
        return os.path.isfile(os.path.join(self.override, name))


class TestTracking(unittest.TestCase):
    def test_new_files_are_recorded_and_removed_but_files_already_there_are_not(self):
        with Game() as g:
            g.write("someone_elses_mod.uti")
            with cf.tracked("shop", g.dir):
                g.write("ap_new.uti", b"new")
                g.write("someone_elses_mod.uti", b"rewritten by us")      # existed before: not ours to remove
            self.assertEqual(cf.restore_group(g.dir, "shop"), 1)
            self.assertFalse(g.has("ap_new.uti"))
            self.assertTrue(g.has("someone_elses_mod.uti"))

    def test_a_file_changed_since_it_was_written_is_left_alone(self):
        with Game() as g:
            with cf.tracked("tracker", g.dir):
                g.write("global.jrl", b"ours")
            g.write("global.jrl", b"replaced by another mod")
            self.assertEqual(cf.restore_group(g.dir, "tracker"), 0)
            self.assertTrue(g.has("global.jrl"))

    def test_a_rerun_that_rewrites_our_file_keeps_it_removable(self):
        with Game() as g:
            with cf.tracked("new_companion", g.dir):
                g.write("p_calo.utc", b"first")
            with cf.tracked("new_companion", g.dir):
                g.write("p_calo.utc", b"second (the class was rolled again)")
            self.assertEqual(cf.restore_group(g.dir, "new_companion"), 1)
            self.assertFalse(g.has("p_calo.utc"))

    def test_a_file_another_script_changed_keeps_the_fingerprint_it_was_recorded_with(self):
        with Game() as g:
            with cf.tracked("shop", g.dir):
                g.write("g_i_drdsncsen002.uti", b"the shop price fix")
            with cf.tracked("droid", g.dir):
                g.write("g_i_drdsncsen002.uti", b"the droid assets' version")        # another script rewrites it
            with cf.tracked("shop", g.dir):
                pass                                                                   # the shop script runs again and leaves it alone
            g.write("g_i_drdsncsen002.uti", b"the shop price fix")                    # the droid script's own undo puts the earlier file back
            self.assertEqual(cf.restore_group(g.dir, "shop"), 1)
            self.assertFalse(g.has("g_i_drdsncsen002.uti"))

    def test_restore_all_covers_every_group_and_forgets_them(self):
        with Game() as g:
            with cf.tracked("a", g.dir):
                g.write("one.ncs")
            with cf.tracked("b", g.dir):
                g.write("two.ncs")
            self.assertEqual(cf.restore_all(g.dir), 2)
            self.assertEqual(cf.restore_all(g.dir), 0)
            self.assertEqual(cf._load(), {})

    def test_a_group_never_recorded_removes_nothing(self):
        with Game() as g:
            g.write("keep.uti")
            self.assertEqual(cf.restore_group(g.dir, "nothing"), 0)
            self.assertTrue(g.has("keep.uti"))


class TestTables(unittest.TestCase):
    @staticmethod
    def table(rows):
        from pykotor.resource.formats.twoda import TwoDA
        t = TwoDA(["label", "denysubrace", "name"])
        for label, deny, name in rows:
            t.add_row(label, {"label": label, "denysubrace": deny, "name": name})
        return t

    def test_identical_tables_match(self):
        vanilla = self.table([("a", "0", "x"), ("b", "0x2", "y")])
        self.assertTrue(cf.table_matches_game(self.table([("a", "0", "x"), ("b", "0x2", "y")]), vanilla))

    def test_only_the_tolerated_cells_may_differ(self):
        vanilla = self.table([("armor", "0", "x"), ("robe", "0x2", "y")])
        edited = self.table([("armor", "0x4", "x"), ("robe", "0x6", "y")])
        self.assertTrue(cf.table_matches_game(edited, vanilla, tolerated_rows={"armor", "robe"}))
        self.assertFalse(cf.table_matches_game(edited, vanilla, tolerated_rows={"armor"}))       # the robe row is not one of ours
        renamed = self.table([("armor", "0", "changed"), ("robe", "0x2", "y")])
        self.assertFalse(cf.table_matches_game(renamed, vanilla, tolerated_rows={"armor", "robe"}))
        self.assertFalse(cf.table_matches_game(self.table([("armor", "0", "x")]), vanilla))     # a row was added or dropped


if __name__ == "__main__":
    unittest.main()
