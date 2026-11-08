"""Tests of the assets the client builds from constants (k2_assets). Where the project's proven files exist (assets/, not published) the built files are compared
with them field by field. Run through tools/run_client_tests.py."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import k2_assets as A  # noqa: E402


def flat(data):
    from pykotor.resource.formats.gff import read_gff
    out = {}

    def walk(struct, prefix):
        for label, ftype, value in struct:
            key = prefix + label
            if ftype.name == "List":
                out[key] = ("list", len(value))
                for i, e in enumerate(value):
                    walk(e, "%s[%d]/" % (key, i))
            elif ftype.name == "LocalizedString":
                out[key] = (ftype.name, value.stringref, str(value))
            else:
                out[key] = (ftype.name, str(value))
    walk(read_gff(data).root, "")
    return out


class TestBuilt(unittest.TestCase):
    def test_the_console_item_casts_the_spell_and_is_a_plot_item(self):
        from pykotor.resource.generics.uti import read_uti
        uti = read_uti(A.console_item())
        self.assertEqual((str(uti.resref), uti.tag, uti.base_item, bool(uti.plot)), ("k2se_craft", "k2se_craft", 64, True))
        self.assertEqual([(p.property_name, p.subtype) for p in uti.properties], [(10, 85)])

    def test_the_menu_has_four_replies_and_the_conditions_on_the_first_three(self):
        from pykotor.resource.generics.dlg import read_dlg
        dlg = read_dlg(A.console_menu())
        entry = dlg.starters[0].node
        self.assertEqual(str(entry.text), "<CUSTOM9220>")
        self.assertEqual([(str(l.node.script1), str(l.active1)) for l in entry.links],
                         [("k2se_cwb", "k2se_cok_bench"), ("k2se_cup", "k2se_cok_up"), ("k2se_clab", "k2se_cok_lab"), ("", "")])

    def test_the_message_box_is_one_entry_with_the_custom_token_text(self):
        from pykotor.resource.generics.dlg import read_dlg
        dlg = read_dlg(A.message_dialog())
        self.assertEqual(len(dlg.starters), 1)
        entry = dlg.starters[0].node
        self.assertEqual((str(entry.text), len(entry.links), entry.plot_index), ("<CUSTOM9201>", 0, -1))

    def test_files(self):
        self.assertEqual(sorted(A.asset_files()), sorted(["k2se_msg.dlg", "k2se_craft.uti", "k2se_craft.dlg"]))
        self.assertEqual(sorted(A.asset_files(console=False)), ["k2se_msg.dlg"])


PROVEN = [("k2se_craft.uti", A.console_item), ("k2se_craft.dlg", A.console_menu)]


@unittest.skipUnless(os.path.isfile(os.path.join(ROOT, "assets", "k2se_craft.dlg")), "the project's proven assets are not here")
class TestAgainstTheProvenFiles(unittest.TestCase):
    def test_every_field_matches(self):
        for name, build in PROVEN:
            with open(os.path.join(ROOT, "assets", name), "rb") as f:
                proven = flat(f.read())
            built = flat(build())
            self.assertEqual(sorted(built), sorted(proven), name)
            for key in built:
                if key.endswith("Comment"):
                    continue                                   # free text of the proven files
                self.assertEqual(built[key], proven[key], "%s %s" % (name, key))


if __name__ == "__main__":
    unittest.main()
