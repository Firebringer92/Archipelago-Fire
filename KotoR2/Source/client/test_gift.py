"""Tests of the AP Companion Gift: the item and the menu the client builds, the placement of the fifty gifts, the scripts and the start grant.
Run through tools/run_client_tests.py."""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import k2_assets as A  # noqa: E402
import k2_gift as G  # noqa: E402


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class TestItemAndMenu(unittest.TestCase):
    def test_the_item_is_a_lootable_useable_item_that_casts_the_menu_spell(self):
        from pykotor.resource.generics.uti import read_uti
        uti = read_uti(A.gift_item())
        self.assertEqual((str(uti.resref), uti.tag, uti.base_item, bool(uti.plot)), ("ap_gift", "ap_gift", 64, False))   # not a plot item: it is carried and looted like any item
        self.assertEqual([(p.property_name, p.subtype) for p in uti.properties], [(10, A.SPELL_ROW)])

    def test_the_menu_has_a_reply_per_companion_with_its_slot_as_the_script_parameter(self):
        from pykotor.resource.formats.gff import read_gff
        root = read_gff(A.gift_menu()).root
        entry = root.get_list("EntryList").at(0)
        links = entry.get_list("RepliesList")
        nodes = root.get_list("ReplyList")
        self.assertEqual((len(links), len(nodes)), (13, 13))
        for n in range(12):
            self.assertEqual(str(links.at(n).get_resref("Active")), "k2ap_gok")
            self.assertEqual(links.at(n).get_int32("Param1"), n)                           # the condition's parameter: which companion
            self.assertEqual(str(nodes.at(n).get_resref("Script")), "k2ap_gans")
            self.assertEqual(nodes.at(n).get_int32("ActionParam1"), n)                     # the answer's parameter: the same companion
        self.assertEqual(str(links.at(12).get_resref("Active")), "")                       # the close reply is always shown
        self.assertEqual(str(nodes.at(12).get_resref("Script")), "")

    def test_the_patch_writes_the_item_and_the_menu(self):
        files = A.asset_files(console=False)
        self.assertIn("ap_gift.uti", files)
        self.assertIn("ap_gift.dlg", files)


class TestPlacement(unittest.TestCase):
    def candidates(self):
        return {"M%02d" % m: [(i, "plc%d" % i, b"raw") for i in range(8)] for m in range(30)}

    def test_fifty_gifts_at_most_four_to_a_module_and_the_same_for_the_same_seed(self):
        a = G.plan_gifts(self.candidates(), "seedA")
        self.assertEqual(len(a), 50)
        self.assertEqual(len({(c["module"], c["index"]) for c in a}), 50)                 # one gift per container
        per = {}
        for c in a:
            per[c["module"]] = per.get(c["module"], 0) + 1
        self.assertLessEqual(max(per.values()), G.PER_MODULE)
        self.assertEqual(a, G.plan_gifts(self.candidates(), "seedA"))
        self.assertNotEqual([(c["module"], c["index"]) for c in a], [(c["module"], c["index"]) for c in G.plan_gifts(self.candidates(), "seedB")])
        self.assertTrue(all(c["clone"].startswith("apgf") and len(c["clone"]) <= 16 for c in a))

    def test_a_clone_template_lists_one_gift_and_keeps_what_was_there(self):
        from pykotor.resource.formats.gff import GFF, GFFContent, GFFList, bytes_gff, read_gff
        from pykotor.common.misc import ResRef
        gff = GFF(GFFContent.UTP)
        items = GFFList()
        entry = items.add(0)
        entry.set_resref("InventoryRes", ResRef("g_i_credits01"))
        gff.root.set_list("ItemList", items)
        out = read_gff(G.with_gift(bytes_gff(gff))).root.get_list("ItemList")
        self.assertEqual([str(i.get_resref("InventoryRes")) for i in out], ["g_i_credits01", "ap_gift"])


class TestScriptsAndGrant(unittest.TestCase):
    def test_the_lean_table_covers_every_slot_and_the_names_match(self):
        src = read("nss/k2ap_gift.nss")
        self.assertIn("nLean == 1", src)
        self.assertEqual(len(re.findall(r'if \(nSlot == \d+\) return "', src)), 11)       # slots 0-10 by name, the Disciple is the fall-through
        self.assertIn("return GetNPCSelectability(nSlot) == 1;", src)                      # offered = selectable now
        self.assertIn("ModifyInfluence(nSlot, nDelta);", src)
        self.assertIn("return 20;", src)
        self.assertIn("if (nLean == 0)", src)                                              # no leaning: the Exile's side decides, so the change can be negative

    def test_using_the_item_opens_the_menu_and_the_dispatcher_can_give_a_stack(self):
        self.assertIn('GetTag(GetSpellCastItem()) == "ap_gift"', read("nss/k_ptat_sandper.nss"))
        disp = read("nss/k2se_disp.nss")
        self.assertIn('sAction == "gift"', disp)
        self.assertIn('CreateItemOnObject("ap_gift", oPC, nGifts, 1);', disp)

    def test_the_scripts_are_compiled_with_the_payload(self):
        import build_payload
        import k2compile
        self.assertIn("k2ap_gok", build_payload.PROJECT_SCRIPTS)
        self.assertIn("k2ap_gans", build_payload.PROJECT_SCRIPTS)
        self.assertIn("k2ap_gift.nss", k2compile.INCLUDES)

    def test_the_client_orders_the_starting_gifts_once(self):
        src = read("client/KotorTwoClient.py")
        self.assertIn('self.dispatcher.submit("gift", str(START_STOCK)', src)
        self.assertIn("if self.start_gifts_sent:", src)
        self.assertEqual(G.START_STOCK, 0)                     # the shipped build starts with no gifts
        self.assertIn("if START_STOCK <= 0:", src)


if __name__ == "__main__":
    unittest.main()
