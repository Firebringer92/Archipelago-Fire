"""Tests of the Bazaar's data and builders. The part that reads the game's files runs only where the game is installed. Run through tools/run_client_tests.py."""
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import k2_bazaar as B  # noqa: E402
import build_bazaar as BB  # noqa: E402

GAME = os.environ.get("K2_GAME_DIR") or r"C:\Program Files (x86)\Steam\steamapps\common\Knights of the Old Republic II"
HAVE_GAME = os.path.isfile(os.path.join(GAME, "swkotor2.exe"))
CFG = B.config()


class TestNumbers(unittest.TestCase):
    def test_the_locations_match_the_data(self):
        with open(os.path.join(ROOT, "data", "locations.json"), encoding="utf-8") as f:
            locs = [l for l in json.load(f)["locations"] if l["type"] == "bazaar"]
        self.assertEqual(sum(1 for l in locs if "Purchase" in l["name"]), CFG["purchases"])
        self.assertEqual(sum(1 for l in locs if "Exchange" in l["name"]), CFG["exchanges"])
        self.assertEqual(CFG["exchanges"] * CFG["tokens_per_exchange"], CFG["tokens_total"])

    def test_the_game_script_prices_match_the_data(self):
        with open(os.path.join(ROOT, "nss", "k2ap_bazaar.nss"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("return %d + %d * nBought;" % (CFG["first_price"], CFG["price_step"]), text)

    def test_every_conversation_script_is_generated(self):
        sources = BB.script_sources(CFG)
        self.assertEqual(sorted(sources), sorted(["ap_jw_greet", "ap_jw_canbuy", "ap_jw_cantrd", "ap_jw_gold", "ap_jw_nogold", "ap_jw_tok", "ap_jw_notok", "ap_jw_buy", "ap_jw_swap"]))
        self.assertTrue(all(len(name) <= 16 for name in sources))
        self.assertIn("K2SE_SetPartyCredits(GetGold(oPC) - nPrice);", sources["ap_jw_buy"])
        self.assertIn("SetItemStackSize(oTokens, nHave - %d);" % CFG["tokens_per_exchange"], sources["ap_jw_swap"])

    def test_the_poll_counts_the_receipts(self):
        with open(os.path.join(ROOT, "nss", "k2se_poll.nss"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn('GetTag(oItem) == "ap_bz_buy"', text)
        self.assertIn('"B|" + IntToString(nBuy) + "|" + IntToString(nSwap)', text)

    def test_the_locker_guard_also_keeps_the_bazaar_items(self):
        with open(os.path.join(ROOT, "nss", "k2ap_gate.nss"), encoding="utf-8") as f:
            text = f.read()
        for tag in ("ap_bz_token", "ap_bz_buy", "ap_bz_swap"):
            self.assertIn('"%s"' % tag, text)


@unittest.skipUnless(HAVE_GAME, "needs the game files")
class TestBuild(unittest.TestCase):
    def test_files_build_and_read_back(self):
        from pykotor.resource.formats.gff import read_gff
        files, problems = B.build_files(GAME)
        self.assertEqual(problems, [])
        self.assertEqual(sorted(files), ["ap_bz_buy.uti", "ap_bz_swap.uti", "ap_bz_token.uti", "ap_jawa.dlg", "apjawa.utc"])
        jawa = read_gff(files["apjawa.utc"]).root
        self.assertEqual((jawa.get_string("Tag"), str(jawa.get_resref("Conversation")), jawa.get_uint8("Plot")), ("apjawa", "ap_jawa", 1))
        token = read_gff(files["ap_bz_token.uti"]).root
        self.assertEqual((token.get_string("Tag"), token.get_uint8("Plot"), token.get_uint16("StackSize")), ("ap_bz_token", 1, 1))
        dlg = read_gff(files["ap_jawa.dlg"]).root
        self.assertEqual((len(dlg.get_list("EntryList")), len(dlg.get_list("StartingList"))), (5, 1))
        # entries and replies strictly alternate: no entry links to an entry
        for entry in dlg.get_list("EntryList"):
            for lk in entry.get_list("RepliesList"):
                self.assertLess(lk.get_uint32("Index"), len(dlg.get_list("ReplyList")))


if __name__ == "__main__":
    unittest.main()
