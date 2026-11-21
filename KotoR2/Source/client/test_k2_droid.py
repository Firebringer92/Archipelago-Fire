"""Tests of the Battle Droid class and the melee rules for droids (k2_droid) against the player's own game tables. Run through tools/run_client_tests.py."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
import k2_droid as D  # noqa: E402

GAME = os.environ.get("K2_GAME_DIR") or r"C:\Program Files (x86)\Steam\steamapps\common\Knights of the Old Republic II"
HAVE_GAME = os.path.isfile(os.path.join(GAME, "swkotor2.exe"))


def game_tables():
    from pykotor.extract.installation import Installation, SearchLocation
    from pykotor.resource.formats.twoda import read_2da
    from pykotor.resource.type import ResourceType
    inst = Installation(GAME)
    return {n: read_2da(inst.resource(n, ResourceType.TwoDA, [SearchLocation.CHITIN]).data) for n in D.TABLES}


@unittest.skipUnless(HAVE_GAME, "the game is not installed")
class TestBattleDroid(unittest.TestCase):
    def setUp(self):
        self.t = game_tables()
        self.cell = lambda name, row, col: self.t[name].get_row(row).get_string(col)

    def apply(self):
        return D.apply_battle_class(self.t["classes"], self.t["feat"], self.t["skills"], self.t["featgain"])

    def test_it_takes_the_cut_row_and_copies_the_combat_droid(self):
        self.assertTrue(self.cell("classes", 10, "label").startswith("BountyHunter"))
        self.assertTrue(self.apply())
        self.assertEqual(self.cell("classes", 10, "label"), "BattleDroid")
        self.assertEqual(self.cell("classes", 10, "name"), "15680")
        for column in ("featstable", "skillstable", "featgain"):
            self.assertEqual(self.cell("classes", 10, column), "DRB")
        for column in ("icon", "savingthrowtable", "attackbonustable", "armorclasscolumn", "forcedie"):
            self.assertEqual(self.cell("classes", 10, column), self.cell("classes", 6, column), column)
        self.assertEqual(self.cell("classes", 10, "hitdie"), "10")
        self.assertEqual(self.cell("classes", 6, "label"), "CombatDroid")         # the game's own droid classes are untouched
        self.assertEqual(self.cell("classes", 7, "label"), "ExpertDroid")

    def test_the_second_run_changes_nothing(self):
        self.apply()
        self.assertFalse(self.apply())

    def test_another_label_in_the_row_is_refused(self):
        self.t["classes"].set_cell(10, "label", "Something")
        with self.assertRaises(ValueError):
            self.apply()

    def test_it_gets_the_combat_droid_feats_plus_both_melee_proficiencies(self):
        self.apply()
        feat = "feat"
        for i in range(self.t[feat].get_height()):
            if i in (D.FEAT_LIGHTSABER_PROF, D.FEAT_MELEE_PROF):
                continue
            self.assertEqual(self.cell(feat, i, "drb_granted"), self.cell(feat, i, "drc_granted"), i)       # nothing else is granted differently
        for f in (D.FEAT_LIGHTSABER_PROF, D.FEAT_MELEE_PROF):
            self.assertEqual(self.cell(feat, f, "drb_granted"), "1")
            self.assertEqual(self.cell(feat, f, "drb_list"), "3")
        self.assertEqual(self.cell(feat, 43, "label"), "WEAPON_PROF_LIGHTSABER")
        self.assertEqual(self.cell(feat, 44, "label"), "WEAPON_PROF_MELEE_WEAPONS")
        self.assertEqual(self.cell(feat, 39, "drb_granted"), "1")                                           # the blaster proficiency of the Combat Droid stays

    def test_the_pick_list_has_no_dead_feats_and_is_ranked(self):
        self.apply()
        ranked = [i for i in range(self.t["feat"].get_height()) if self.cell("feat", i, "drb_recom") not in ("", "0", "****") and self.cell("feat", i, "drb_list") == "1"]
        self.assertGreater(len(ranked), 20)
        for i in ranked:
            self.assertFalse(self.cell("feat", i, "label").upper().startswith("XXX"), i)

    def test_skills_and_feat_gain_columns(self):
        self.apply()
        classes = [i for i in range(self.t["skills"].get_height()) if self.cell("skills", i, "drb_class") == "1"]
        self.assertEqual(set(classes), D.BATTLE_CLASS_SKILLS)
        for i in range(self.t["featgain"].get_height()):
            self.assertEqual(self.cell("featgain", i, "drb_reg"), self.cell("featgain", i, "drx_reg"))
            self.assertEqual(self.cell("featgain", i, "drb_bon"), self.cell("featgain", i, "drx_bon"))

    def test_melee_rows_open_to_droids_and_nothing_else(self):
        before = {i: self.cell("baseitems", i, "droidorhuman") for i in range(self.t["baseitems"].get_height())}
        changed = D.open_melee_to_droids(self.t["baseitems"])
        self.assertEqual(changed, len(D.MELEE_BASEITEM_ROWS))
        for i, was in before.items():
            now = self.cell("baseitems", i, "droidorhuman")
            self.assertEqual(now, "0" if i in D.MELEE_BASEITEM_ROWS else was, i)
        self.assertEqual(self.cell("baseitems", 8, "label"), "Lightsaber")
        self.assertEqual(D.open_melee_to_droids(self.t["baseitems"]), 0)

    def test_the_melee_rows_are_the_human_only_weapons(self):
        weapons = [i for i in range(self.t["baseitems"].get_height()) if self.cell("baseitems", i, "droidorhuman") == "1" and self.cell("baseitems", i, "weaponwield") not in ("", "****")]
        self.assertEqual(sorted(weapons), sorted(D.MELEE_BASEITEM_ROWS))

    def test_files_for_the_override_folder(self):
        files, problems = D.droid_table_files(GAME)
        self.assertEqual(problems, [])
        self.assertEqual(sorted(files), sorted(n + ".2da" for n in D.TABLES))
        from pykotor.resource.formats.twoda import read_2da
        self.assertEqual(read_2da(files["classes.2da"]).get_row(10).get_string("label"), "BattleDroid")


class TestWhereTheClassIsKnown(unittest.TestCase):
    def test_the_class_rebuild_treats_class_10_as_a_droid(self):
        root = os.path.normpath(os.path.join(HERE, ".."))
        with open(os.path.join(root, "nss", "k2se_rb.nss"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn("bDroidClass = (nNew == 6 || nNew == 7 || nNew == 10);", src)         # skills a droid cannot use are skipped for the Battle Droid too
        with open(os.path.join(root, "tools", "classrb_data.py"), encoding="utf-8") as f:
            self.assertIn("DROID_CLASSES = (6, 7, 10)", f.read())

    @unittest.skipUnless(HAVE_GAME, "the game is not installed")
    def test_the_rebuild_data_grants_the_melee_proficiencies_to_class_10_only(self):
        sys.path.insert(0, os.path.join(HERE, "..", "tools"))
        os.environ.setdefault("K2_GAME_DIR", GAME)
        import classrb_data
        d = classrb_data.load()
        self.assertEqual(d["classes"][10]["label"], "BattleDroid")
        self.assertEqual(d["classes"][10]["featstable"], "DRB")
        self.assertEqual(d["classes"][6]["label"], "CombatDroid")


class TestLooksAndFiles(unittest.TestCase):
    SLOT = {"start_class": {"class": 10, "mode": 1, "race": 5, "look": 82},
            "companion_classes": {"0": {"class": 10, "look": 58}, "1": {"class": 6, "look": 66}, "2": {"class": 7, "look": 63}, "3": {"class": 10, "look": 29},
                                  "4": {"class": 10, "look": 380}, "5": {"class": 10, "look": 538}}}

    def test_a_seed_without_a_battle_droid_gets_no_files(self):
        self.assertFalse(D.uses_battle_droid({}))
        self.assertFalse(D.uses_battle_droid({"start_class": {"class": 6}, "companion_classes": {"1": {"class": 7}}}))
        self.assertEqual(D.droid_files(GAME, {}, "tools"), ({}, []))

    def test_either_the_player_or_a_companion_makes_it_needed(self):
        self.assertTrue(D.uses_battle_droid(self.SLOT))
        self.assertTrue(D.uses_battle_droid({"companion_classes": {"4": {"class": 10}}}))
        self.assertTrue(D.uses_battle_droid({"start_class": {"class": 10}}))

    def test_the_fallback_replaces_only_the_human_rig_looks(self):
        import copy
        slot = copy.deepcopy(self.SLOT)
        self.assertEqual(D.fallback_looks(slot), 4)
        self.assertEqual(slot["start_class"]["look"], 66)
        self.assertEqual([slot["companion_classes"][k]["look"] for k in "012345"], [66, 66, 63, 66, 66, 538])     # the HK-50 body (538) is a game row and stays

    def test_a_missing_model_replaces_only_the_looks_that_need_it(self):
        import copy
        slot = copy.deepcopy(self.SLOT)
        self.assertEqual(D.looks_in_use(slot), {82, 58, 29, 380})
        self.assertEqual(D.fallback_looks(slot, {58}), 1)
        self.assertEqual(slot["start_class"]["look"], 82)
        self.assertEqual([slot["companion_classes"][k]["look"] for k in "012345"], [66, 66, 63, 29, 380, 538])

    def test_a_human_rig_look_needs_its_model_files(self):
        import tempfile
        with tempfile.TemporaryDirectory() as override:
            self.assertEqual(D.usable_look(82, override), 66)
            self.assertEqual(D.usable_look(66, override), 66)
            self.assertEqual(D.usable_look(63, override), 63)
            for ext in (".mdl", ".mdx"):
                open(os.path.join(override, "ap_drdassn" + ext), "wb").close()
            self.assertEqual(D.usable_look(82, override), 82)
            self.assertEqual(D.usable_look(58, override), 66)                       # the other model is still missing
            self.assertEqual(D.usable_look(538, override), 538)                     # the HK-50 body needs no model

    @unittest.skipUnless(HAVE_GAME, "the game is not installed")
    def test_a_battle_droid_seed_gets_tables_models_and_appearance(self):
        import build_droid_models  # noqa: F401  (tools folder on the path below)
        import copy
        files, problems = D.droid_files(GAME, copy.deepcopy(self.SLOT), os.path.join(HERE, "..", "tools"))      # a copy: a model that is missing changes the looks in place
        self.assertTrue({"classes.2da", "feat.2da", "baseitems.2da"} <= set(files), problems)
        if "appearance.2da" in files:
            self.assertTrue({"ap_drdassn.mdl", "ap_drdassn.mdx", "ap_drdmine.mdl", "ap_drdmine.mdx"} <= set(files))
        else:
            self.assertTrue(problems)                                               # no models: the reason is reported


class TestPlayerConversionRuns(unittest.TestCase):
    """The player's class conversion runs in four script runs (found live 2026-11-18: one run did not fit; nothing after the feat removal happened)."""

    def read(self, rel):
        with open(os.path.join(HERE, "..", rel), encoding="utf-8") as f:
            return f.read()

    def test_the_rebuild_has_four_phases_and_the_marker_stays_until_the_last(self):
        rb = self.read("nss/k2se_rb.nss")
        for n in (1, 2, 3):
            self.assertIn("if (nPhase == %d) return RB_STEP_DONE;" % n, rb)
        self.assertIn("nRes == RB_BAD_STATE || nRes == RB_STEP_DONE", rb)                    # a step never reaches the hit points, the XP or the marker clear

    def test_the_marker_of_the_player_uses_seven_bits_per_local_number(self):
        rb = self.read("nss/k2se_rb.nss")
        self.assertIn("1 + b / 7", rb)
        self.assertIn("(127 - nMask)", rb)
        self.assertNotIn("b / 8", rb)

    def test_the_battle_droid_is_not_refused_by_the_rebuild_or_the_extender(self):
        self.assertNotIn("nNewClass == 10", self.read("nss/k2se_rb.nss"))
        self.assertIn("id >= 0 && id <= 16;", self.read("src/cwrite.cpp"))

    def test_the_dispatcher_schedules_each_phase_before_running_it_and_the_next_poll_first(self):
        disp = self.read("nss/k2se_disp.nss")
        self.assertIn("if (nPhase < 4) DelayCommand(1.0, DispClassPhase(oPC, sArgs, nPhase + 1));", disp)
        self.assertIn("DelayCommand(0.5, DispClassPhase(oPC, sArgs, 1));", disp)
        poll = disp.index("DispPollOnce();" + chr(10) + "    // companions whose item")
        self.assertLess(disp.index('AssignCommand(oPC, DelayCommand(K2SE_ConfigInt("disp_period", 3) + 0.0, DispTick(nGen)));'), poll)   # the loop is re-armed before the work
        self.assertIn('K2SE_MemSet("rb_phase", "0");' + chr(10) + '    ExecuteScript("k2se_rb", oC,', disp)             # a companion's conversion always runs whole

    def test_the_droid_race_and_disguise_come_after_the_last_phase(self):
        disp = self.read("nss/k2se_disp.nss")
        self.assertIn("if (nPhase == 4) DispClassFinish(oPC, sArgs);", disp)
        self.assertIn("EffectDisguise(nLook)", disp)


class TestPlayerDisguiseStays(unittest.TestCase):
    """The game's a_suitrestrict removes every disguise effect from the Exile; the tick puts the droid look back."""

    def read(self, rel):
        with open(os.path.join(HERE, "..", rel), encoding="utf-8") as f:
            return f.read()

    def test_the_tick_puts_the_look_back_when_none_is_on(self):
        comp = self.read("nss/k2ap_comp.nss")
        body = comp[comp.index("int K2AP_PlayerLookEnforce"):comp.index("int K2AP_LookEnforce")]
        self.assertIn('K2SE_ConfigInt("ap_pc_look", 0)', body)
        self.assertIn("if (K2AP_HasDisguise(oPC)) return 0;", body)
        self.assertIn("K2AP_PlayerLookEnforce(oPC);", self.read("nss/k2se_disp.nss"))

    def test_the_protocol_droid_look_of_a_story_companion_is_a_disguise_not_the_template_row(self):
        import k2_extras as X
        classes = {"0": {"class": 10, "race": 5, "look": 380}, "1": {"class": 10, "race": 5, "look": 538}, "3": {"class": 10, "race": 5, "look": 380}}
        self.assertEqual(X.companion_look_lines(classes), ["ap_clook_0=380", "ap_clook_1=538"])      # every droid story companion; slot 3 (G0-T0) has no template to change
        comp = self.read("nss/k2ap_comp.nss")
        self.assertIn('K2SE_ConfigInt("ap_clook_" + IntToString(nSlot), 0)', comp)
        self.assertIn("K2AP_CompLookEnforce();", self.read("nss/k2se_disp.nss"))
        self.assertIn("K2AP_StripDisguise(oCreature);", comp)             # a disguise saved under an earlier look row is replaced on the first pass of a session
        self.assertIn('"clk" + IntToString(nSlot)', comp)
        self.assertIn(380, D.DISGUISE_LOOKS)

    def test_a_droid_in_the_party_wears_the_hidden_plating_with_the_game_droids_immunities(self):
        import k2_assets as A
        from pykotor.resource.generics.uti import read_uti
        uti = read_uti(A.droid_hide_item())
        self.assertEqual((str(uti.resref), uti.base_item, uti.plot), ("ap_drdhide", 84, True))
        self.assertEqual(sorted((p.property_name, p.subtype) for p in uti.properties), [(24, 2), (24, 3), (24, 7)])       # mind spells, poison, paralysis
        self.assertIn("ap_drdhide.uti", A.asset_files(console=False))
        comp = self.read("nss/k2ap_comp.nss")
        body = comp[comp.index("int K2AP_DroidHideEnforce"):comp.index("string K2AP_CompTag")]
        self.assertIn("GetRacialType(oMember) != RACIAL_TYPE_DROID", body)
        self.assertIn("GetItemInSlot(INVENTORY_SLOT_CARMOUR, oMember)", body)
        self.assertIn("K2AP_DroidHideEnforce();", self.read("nss/k2se_disp.nss"))

    def test_shortened_peragus_unlocks_every_door_in_both_acts(self):
        per = self.read("nss/k2ap_per.nss")
        self.assertIn("GetNearestObject(OBJECT_TYPE_DOOR, oPC, n)", per)
        tick = per[per.index("void K2AP_PerTick"):per.index("void K2AP_PeragusEnter")]
        self.assertIn("K2AP_PerUnlockDoors(oPC);", tick)
        self.assertNotIn("SetLocked(oDorm, TRUE)", per)
        self.assertNotIn("SetLocked", self.read("nss/k2se_disp.nss"))  # the dispatcher is not where door locks are fixed (client/k2_doors.py peragus_unlock edits the templates)
        enter = per[per.index("void K2AP_PerDoorsRepeat"):]
        self.assertIn('GetStringRight(GetStringUpperCase(GetModuleName()), 3) != "PER"', enter)   # every Peragus module, on entry, not only 101PER and 105PER
        self.assertIn("K2AP_PerDoorsRepeat(nDoors);", enter[enter.index("void K2AP_PeragusEnter"):])
        self.assertIn('StringToInt(K2SE_MemGet("per_dgen")) != nGen', enter)                      # lasts as long as the player stays; a newer entry ends an older loop

    def test_the_hangar_door_script_starts_the_delivery_loop_because_the_hangar_has_no_area_hook(self):
        scene = self.read("nss/k2ap_scene.nss")
        body = scene[scene.index("int K2AP_SceneUnlockDoor"):]
        self.assertIn('== "106per") ExecuteScript("k2se_ap_enter"', body)

    def test_the_protocol_droid_host_row_has_the_movement_values_of_a_human_rig_body(self):
        import build_droid_models as B
        cells = B.CONFIGS["protocol"]["row_cells"]
        self.assertEqual((cells["walkdist"], cells["rundist"], cells["moverate"]), ("1.75", "3.75", "NORM"))   # the creature row's 0.6 / 0.7 / SLOW played every clip at the wrong pace

    def test_creature_droid_looks_become_human_rig_bodies_that_can_hold_weapons(self):
        import k2_droid as D
        slot = {"start_class": {"class": 7, "race": 5, "look": 63},
                "companion_classes": {"6": {"class": 7, "race": 5, "look": 63}, "1": {"class": 6, "race": 5, "look": 66}, "0": {"class": 10, "race": 5, "look": 58}}}
        self.assertFalse(D.uses_battle_droid({"companion_classes": {"6": {"class": 7, "race": 5, "look": 63}}}))      # creature looks alone need no models
        self.assertEqual(D.rig_looks(slot), 3)
        self.assertEqual((slot["start_class"]["look"], slot["companion_classes"]["6"]["look"], slot["companion_classes"]["1"]["look"], slot["companion_classes"]["0"]["look"]), (380, 380, 29, 58))
        self.assertEqual(D.rig_looks(slot), 0)                                                    # repeating changes nothing
        self.assertTrue(D.uses_battle_droid({"companion_classes": {"6": {"class": 7, "race": 5, "look": 380}}}))     # a human-rig look has its models and rows built

    def test_the_client_writes_the_look_of_the_start_class_into_the_config(self):
        import KotorTwoClient as K
        ctx = K.KotorTwoContext.__new__(K.KotorTwoContext)
        ctx.slot_data = {"start_class": {"class": 10, "mode": 1, "race": 5, "look": 380}}
        ctx._look_lines = []
        self.assertIn("ap_pc_look=380", K.KotorTwoContext._config(ctx, None, set()))
        ctx.slot_data = {}
        self.assertFalse([l for l in K.KotorTwoContext._config(ctx, None, set()) if l.startswith("ap_pc_look")])


if __name__ == "__main__":
    unittest.main()
