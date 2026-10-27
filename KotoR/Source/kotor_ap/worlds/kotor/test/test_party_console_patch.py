"""patch_party_console.py: the spells.2da row the Party Console item needs on a player's machine (vanilla spells.2da stops at row 131)."""
import os
import sys
import unittest

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "scripts")


@unittest.skipUnless(os.path.isdir(SCRIPTS), "scripts folder not next to this world")
class TestPartyConsoleSpellRow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.abspath(SCRIPTS))
        import patch_party_console as p
        cls.p = p

    def _table(self, rows):
        from pykotor.resource.formats.twoda import TwoDA
        t = TwoDA(["label", "name", "impactscript", "usertype"])
        for i in range(rows):
            r = t.add_row(str(i))
            t.set_cell(r, "label", f"VANILLA_{i}")
            t.set_cell(r, "name", str(i))
            t.set_cell(r, "impactscript", f"k_sp_{i}")
            t.set_cell(r, "usertype", "2" if i == self.p.PLOT_SPELL_ROW else "1")
        return t

    def test_a_vanilla_table_gets_the_row_appended(self):
        t = self._table(132)
        self.assertEqual(self.p.ensure_row(t), "added")
        self.assertEqual(t.get_height(), 133)
        self.assertEqual(t.get_cell(132, "label"), self.p.LABEL)
        self.assertEqual(t.get_cell(132, "impactscript"), self.p.IMPACT_SCRIPT)
        self.assertEqual(t.get_cell(132, "usertype"), "2")           # every other column copied from the plot spell row

    def test_running_it_again_changes_nothing(self):
        t = self._table(132)
        self.p.ensure_row(t)
        self.assertEqual(self.p.ensure_row(t), "present")
        self.assertEqual(t.get_height(), 133)

    def test_our_own_older_row_is_brought_up_to_date(self):
        t = self._table(133)
        t.set_cell(132, "label", "AP_TEST_CASTSPELL_DIAG")
        self.assertEqual(self.p.ensure_row(t), "updated")
        self.assertEqual(t.get_cell(132, "impactscript"), self.p.IMPACT_SCRIPT)

    def test_another_mods_row_is_left_alone(self):
        t = self._table(133)
        self.assertEqual(self.p.ensure_row(t), "foreign")
        self.assertEqual(t.get_cell(132, "label"), "VANILLA_132")

    def test_a_table_too_short_is_refused(self):
        with self.assertRaises(ValueError):
            self.p.ensure_row(self._table(100))

    def test_the_constants_match_the_developer_generator(self):
        text = open(os.path.join(SCRIPTS, "generate_party_console.py"), encoding="utf-8").read()
        self.assertIn(f"SPELL_ROW = {self.p.SPELL_ROW}", text)
        self.assertIn(f"PLOT_SPELL_ROW = {self.p.PLOT_SPELL_ROW}", text)
