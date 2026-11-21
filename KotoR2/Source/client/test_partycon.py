"""The Party Console: its item and menu (client/k2_assets.py), its scripts (nss/), its delivery (the dispatcher's partycon action) and the seed's item.
Run through tools/run_client_tests.py."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import k2_assets as A  # noqa: E402


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class TestItemAndMenu(unittest.TestCase):
    def test_the_item_is_a_plot_item_that_casts_the_menu_spell_without_being_used_up(self):
        from pykotor.resource.generics.uti import read_uti
        uti = read_uti(A.partycon_item())
        self.assertEqual((str(uti.resref), uti.tag, uti.base_item, uti.plot), ("ap_partycon", "ap_partycon", 64, True))
        self.assertEqual(len(uti.properties), 1)
        prop = uti.properties[0]
        self.assertEqual((prop.property_name, prop.subtype, prop.cost_table, prop.cost_value), (10, A.SPELL_ROW, 3, 13))     # cast spell 85, unlimited uses

    def test_the_menu_has_a_header_and_four_replies_each_with_its_script(self):
        from pykotor.resource.formats.gff import read_gff
        root = read_gff(A.partycon_menu()).root
        self.assertEqual(len(root.get_list("EntryList")), 1)
        self.assertEqual(len(root.get_list("EntryList").at(0).get_list("RepliesList")), 4)
        replies = root.get_list("ReplyList")
        self.assertEqual([str(replies.at(n).get_resref("Script")) for n in range(4)], ["k2ap_pcopen", "k2ap_pcstand", "k2ap_pcclear", ""])
        self.assertEqual([replies.at(n).get_int32("PlotIndex") for n in range(4)], [-1] * 4)           # a reply with plot index 0 awards plot XP
        self.assertEqual(str(root.get_list("EntryList").at(0).get_locstring("Text")), "<CUSTOM9250>")

    def test_every_seed_writes_both_files(self):
        self.assertIn("ap_partycon.uti", A.asset_files(console=False))
        self.assertIn("ap_partycon.dlg", A.asset_files(console=False))


class TestScripts(unittest.TestCase):
    def test_using_the_item_opens_the_menu_and_gives_the_item_back(self):
        src = read("nss/k_ptat_sandper.nss")
        self.assertIn('GetTag(GetSpellCastItem()) == "ap_partycon"', src)
        self.assertIn('"ap_partycon", FALSE, CONVERSATION_TYPE_CINEMATIC, TRUE', src)
        self.assertIn('CreateItemOnObject("ap_partycon", oPC, 1, 1);', src)

    def test_the_reply_opens_the_party_screen(self):
        self.assertIn('ShowPartySelectionGUI("k2ap_pcdone", -1, -1, TRUE);', read("nss/k2ap_pcopen.nss"))

    def test_the_dispatcher_gives_one_console_and_never_a_second(self):
        disp = read("nss/k2se_disp.nss")
        self.assertIn('sAction == "partycon"', disp)
        self.assertIn('if (GetIsObjectValid(GetItemPossessedBy(oPC, "ap_partycon"))) return TRUE;', disp)

    def test_the_scripts_are_compiled_with_the_payload(self):
        import build_payload
        self.assertIn("k2ap_pcopen", build_payload.PROJECT_SCRIPTS)
        for name in ("k2ap_pcdone", "k2ap_pcstand", "k2ap_pcsdone", "k2ap_pcclear"):
            self.assertIn(name, build_payload.PROJECT_SCRIPTS)

    def test_the_scripts_compile(self):
        import shutil
        import tempfile
        import k2compile
        import tsl_data
        folder = tempfile.mkdtemp()
        try:
            k2compile.prepare_include_dir(folder, tsl_data.GAME)
            for name in ("k_ptat_sandper", "k2ap_pcopen", "k2ap_pcdone", "k2ap_pcstand", "k2ap_pcsdone", "k2ap_pcclear"):
                shutil.copy(os.path.join(ROOT, "nss", name + ".nss"), os.path.join(folder, name + ".nss"))
                ok, message = k2compile.compile_script(folder, name)
                self.assertTrue(ok, "%s: %s" % (name, message))
        finally:
            shutil.rmtree(folder, ignore_errors=True)


class TestSceneLoanEnds(unittest.TestCase):
    def test_a_loan_ends_unless_the_item_arrived_and_being_selectable_proves_nothing(self):
        scene = read("nss/k2ap_scene.nss")
        release = scene[scene.index("void K2AP_SceneRelease"):scene.index("void K2AP_SceneEnsure")]
        self.assertIn('K2SE_MemGet("cu" + IntToString(nSlot)) == "1"', release)
        self.assertNotIn("GetNPCSelectability(nSlot) == 1", release)           # the story makes every recruit selectable, so a loan never ended
        self.assertIn('K2SE_MemSet("cu" + IntToString(nSlot), "1");', read("nss/k2ap_comp.nss"))

    def test_a_loan_whose_timer_was_cut_short_is_ended_by_the_hiding_pass(self):
        comp, scene = read("nss/k2ap_comp.nss"), read("nss/k2ap_scene.nss")
        sweep = comp[comp.index("void K2AP_LoanSweep"):comp.index("int K2AP_CompHeld")]
        self.assertIn('"cu" + IntToString(nSlot)) == "1"', sweep)               # an item that really arrived keeps the bit
        self.assertIn("& ~(1 << K2AP_CompShift(nSlot))", sweep)
        enforce = comp[comp.index("int K2AP_CompEnforce"):]
        self.assertIn("K2AP_LoanSweep(oPC);", enforce)
        self.assertEqual(scene.count('K2SE_MemSet("loan" + IntToString(nSlot), "1");'), 2)    # SceneEnsure and SceneLend both mark the loan


class TestStanding(unittest.TestCase):
    def test_two_standing_slots_are_kept_in_player_numbers_that_no_other_feature_uses(self):
        src = read("nss/k2ap_stand.nss")
        self.assertIn("GetLocalNumber(GetFirstPC(), 7 + k) - 1", src)             # slot + 1 in numbers 7 and 8 (a local number keeps 7 bits: 0-127)
        self.assertIn("GetLocalNumber(GetFirstPC(), 9 + k) - 1", src)             # the active pair put aside, numbers 9 and 10
        for other in ("nss/k2se_disp.nss", "nss/k2ap_comp.nss", "nss/k2se_rb.nss", "nss/k2ap_scene.nss", "nss/k2ap_per.nss"):
            text = read(other)
            for n in (7, 8, 9, 10):
                self.assertNotIn("SetLocalNumber(oPC, %d," % n, text, other)
                self.assertNotIn("SetLocalNumber(GetFirstPC(), %d," % n, text, other)

    def test_the_tags_of_extra_companions_match_the_templates_the_client_builds(self):
        import k2_extras
        self.assertIn('return "apxc" + IntToString(nSlot);', read("nss/k2ap_stand.nss"))
        self.assertEqual(k2_extras.template_name(12), "apxc12")

    def test_the_area_tail_starts_the_loop_and_sees_the_config_switch(self):
        import build_area_wrappers
        self.assertIn("K2AP_StandEnter();", build_area_wrappers.TAIL_SOURCE)
        self.assertIn('#include "k2ap_stand"', build_area_wrappers.TAIL_SOURCE)
        self.assertIn('K2SE_ConfigInt("ap_standing", 1)', read("nss/k2ap_stand.nss"))

    def test_a_picked_pair_replaces_the_old_one_and_a_cancel_changes_nothing(self):
        src = read("nss/k2ap_pcsdone.nss")
        self.assertIn("nOld != nPick0 && nOld != nPick1", src)
        self.assertIn("if (nPicked != 0)", src)
        self.assertIn("ShowPartySelectionGUI(", read("nss/k2ap_pcstand.nss"))

    def test_the_active_screen_takes_a_standing_companion_out_of_standing(self):
        self.assertIn("IsNPCPartyMember(nSlot)) K2AP_StandSet(k, -1);", read("nss/k2ap_pcdone.nss"))

    def test_the_scripts_compile_together_with_the_area_tail(self):
        import shutil
        import tempfile
        import build_area_wrappers
        import k2compile
        import tsl_data
        folder = tempfile.mkdtemp()
        try:
            k2compile.prepare_include_dir(folder, tsl_data.GAME)
            with open(os.path.join(folder, "tail.nss"), "w") as f:
                f.write(build_area_wrappers.TAIL_SOURCE)
            ok, message = k2compile.compile_script(folder, "tail")
            self.assertTrue(ok, message)
        finally:
            shutil.rmtree(folder, ignore_errors=True)


class TestClient(unittest.TestCase):
    def test_the_arm_becomes_a_partycon_job_and_a_test_can_send_it(self):
        import KotorTwoClient as K
        from worlds.kotor2.Items import ITEMS
        self.assertEqual(ITEMS["Party Console"].arm, "partycon")
        self.assertEqual(K.arm_to_job("partycon"), ("partycon", ""))
        self.assertIn("partycon", K.TEST_GIVE_ACTIONS)


if __name__ == "__main__":
    unittest.main()
