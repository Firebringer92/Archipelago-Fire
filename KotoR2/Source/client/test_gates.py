"""Tests of the story-gate pieces that need no game: the gate order shared by the scripts, and the generated wrapper sources.
Run through tools/run_client_tests.py."""
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import k2_seed  # noqa: E402
import build_gate_wrappers as W  # noqa: E402

GATES = {g["id"]: g for g in json.load(open(os.path.join(ROOT, "data", "gates.json"), encoding="utf-8"))["gates"]}


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class TestGateOrder(unittest.TestCase):
    def test_dispatcher_and_seed_agree_on_the_gate_order(self):
        # the dispatcher sets release flag 32 + n, the gate check reads 32 + K2AP_GateBit: both must number the gates the same way
        m = re.search(r'string sList = "([^"]+)"', read("nss/k2se_disp.nss"))
        self.assertEqual(tuple(m.group(1).split()), k2_seed.GATE_ORDER)

    def test_gates_file_lists_the_same_gates(self):
        self.assertEqual(set(GATES), set(k2_seed.GATE_ORDER))


class TestWrapperTable(unittest.TestCase):
    def test_every_wrapped_gate_is_a_script_gate_with_a_family(self):
        for script, gated in W.GATED.items():
            for module, entry in gated.items():
                gate = entry[0] if isinstance(entry, tuple) else entry
                self.assertIn(GATES[gate]["hook"]["kind"], ("S", "T", "D"), gate)
                self.assertIn(GATES[gate]["family"], W.FAMILY_KEY, gate)
                self.assertTrue(module.isupper() and len(module) == 6, module)

    def test_the_hook_text_names_the_script(self):
        for script, gated in W.GATED.items():
            for gate in {e[0] if isinstance(e, tuple) else e for e in gated.values()}:
                self.assertIn(script, GATES[gate]["hook"]["target"] + GATES[gate]["hook"]["called_from"], (script, gate))

    def test_family_keys_match_the_client(self):
        import KotorTwoClient   # noqa: F401  (needs the Archipelago core: run through tools/run_client_tests.py)
        self.assertEqual(tuple(W.FAMILY_KEY.values()), KotorTwoClient.TOKEN_FAMILIES)


class TestWrapperSource(unittest.TestCase):
    """The generated sources are the CHECK part of a gate script (an int script: TRUE = held back); the game's own original is joined on by tools/ncs_merge.py,
    never run through ExecuteScript (it would lose the engine's event: GetEnteringObject, GetScriptParameter)."""

    def test_no_generated_source_runs_an_original_through_execute_script(self):
        sources = [W.wrapper_source("a_load262", {"006EBO": "FIN2"}), W.guard_source("my_clear_inv"),
                   W.replace_source("a_505turret", W.TURRETS["a_505turret"]), W.replace_source("tr_exit702_end", {"701KOR": ""}, None, None, W.HOLD["tr_exit702_end"])]
        for src in sources:
            self.assertNotIn("ExecuteScript", src)

    def test_gated_module_asks_the_gate_and_answers_held_or_not(self):
        src = W.wrapper_source("a_load262", {"006EBO": "FIN2"})
        self.assertIn("int StartingConditional()", src)
        self.assertIn('if (sMod == "006ebo")', src)
        self.assertLess(src.index('K2AP_GateOpen("FIN2", "endgame", "Endgame", 2)'), src.index("return TRUE;"))       # held back -> TRUE: the original does not run
        self.assertTrue(src.rstrip().endswith("return FALSE;\n}"))                                                      # every other module: the original runs

    def test_locker_guard_is_what_runs_after_the_original(self):
        src = W.guard_source("my_clear_inv")
        self.assertIn("void main()", src)
        self.assertIn("K2AP_TokensFromLockers();", src)
        self.assertIn("my_clear_inv", W.GUARDED)

    def test_turret_skips_run_only_when_the_seed_says_so(self):
        for name, bodies in W.TURRETS.items():
            src = W.replace_source(name, bodies)
            module = next(iter(bodies)).lower()
            self.assertIn('if (sMod == "%s" && (K2AP_SkipTurrets()))' % module, src)
            self.assertIn("return TRUE; }", src)                 # the code ran instead: the original is skipped
            self.assertTrue(src.rstrip().endswith("return FALSE;\n}"))      # the seed off: the original, as before
        self.assertIn('"107PER_MG_DEAD", 25', W.TURRETS["a_load003ebo"]["106PER"])
        self.assertIn("int K2AP_SkipTurrets()", k2_seed.nss_include())

    def test_trigger_gates_only_hold_the_party_leader_and_the_right_branch(self):
        src = W.wrapper_source("tr_enclave_cam", {"605DAN": W.GATED["tr_enclave_cam"]["605DAN"]})
        self.assertIn('if (GetIsPartyLeader(GetEnteringObject()) && GetGlobalNumber("650DAN_Rebuilt") != 0)', src)
        self.assertLess(src.index("650DAN_Rebuilt"), src.index('K2AP_GateOpen("FIN1"'))       # the gate is asked only inside that branch
        self.assertEqual(W.GATED["tr_vash"]["702KOR"][0], "KOR2")

    def test_academy_door_stays_open_until_vash_is_found(self):
        src = W.replace_source("tr_exit702_end", {"701KOR": ""}, None, None, W.HOLD["tr_exit702_end"])
        self.assertIn('GetGlobalNumber("702KOR_Vash") != 1', src)
        self.assertIn("return TRUE;", src)

    def test_a_scene_check_brings_the_companion_in_before_the_scenes_dialogue(self):
        """233TEL's mercenary talk (dialogue 233mrcc) is spoken by Bao-Dur; the check is joined onto the game's own trigger script, never run through ExecuteScript."""
        src = W.scene_source("a_mercctalk", ["233TEL"])
        self.assertNotIn("ExecuteScript", src)
        self.assertIn('#include "k2ap_scene"', src)
        self.assertIn('if (sMod == "233tel")', src)
        self.assertIn("if (GetEnteringObject() == GetPartyLeader())", src)
        self.assertIn("K2AP_SceneEnsure(2);", src)                                # Bao-Dur is slot 1: bit 2
        self.assertNotIn("K2AP_SceneEnsureAgain", src)                            # the loan (unlock bit) keeps the hiding pass off: no second check is needed
        self.assertTrue(src.rstrip().endswith("return FALSE;\n}"))                  # the original always runs

    def test_a_gated_script_with_a_scene_does_both_and_the_scene_runs_only_when_the_gate_is_open(self):
        src = W.wrapper_source("tr_baodurpad", {"233TEL": ("TEL2", "GetIsPartyLeader(GetEnteringObject())")})
        self.assertIn('#include "k2ap_scene"', src)
        self.assertLess(src.index('K2AP_Trace("tr_baodurpad", "held back by TEL2")'), src.index("K2AP_SceneEnsure(2);"))      # a held gate returns before the scene check
        self.assertNotIn("K2AP_SceneEnsure", W.wrapper_source("a_load262", {"006EBO": "FIN2"}))                             # a script without a scene gets none

    def test_a_lend_scene_only_lends_and_never_adds(self):
        src = W.scene_source("k_301_ref3", ["301NAR"])
        self.assertIn("K2AP_SceneLend(64);", src)                 # Kreia, slot 6
        self.assertNotIn("K2AP_SceneEnsure", src)
        self.assertIn("GetEnteringObject() == GetPartyLeader()", src)
        arrival = W.scene_source("k_301_enter", ["301NAR"])
        self.assertIn("K2AP_SceneLend(%d);" % (16 + 64 + 512 + 2048), arrival)        # Handmaiden, Kreia, Visas, Disciple

    def test_a_stage_scene_makes_the_missing_actor_at_the_story_spot(self):
        src = W.scene_source("k_305_intro", ["305NAR"])
        self.assertIn("K2AP_SceneStage(7, -39.78, -3.34, -1.97, 191.50);", src)      # Mira at her cell in the tunnels
        self.assertNotIn("K2AP_SceneEnsure", src)
        self.assertNotIn("K2AP_SceneLend", src)
        self.assertTrue(W.scene_table()["k_305_intro"]["305NAR"]["area"])             # joined by build_area_wrappers.py, not made here

    def test_the_305_door_scene_clears_the_flag_and_stages_mira(self):
        src = W.scene_source("a_compdlg", ["232TEL", "305NAR"])
        self.assertIn('GetTag(OBJECT_SELF) == "HighSecurityDoorInterior"', src)
        self.assertIn("K2AP_SceneStage(7, -39.78, -3.34, -1.97, 191.50);", src)
        self.assertIn("K2AP_SceneReset(10, 50);", src)
        self.assertIn("K2AP_SceneEnsure(2);", src)                                    # the 232TEL force-field scene is still there

    def test_the_onderon_return_scene_stages_mandalore_only_before_the_scene_has_played(self):
        src = W.scene_source("k_501_enter", ["501OND"])
        self.assertIn("K2AP_SceneStage(2, 7.60, 95.20, 12.76, 214.50);", src)         # Mandalore (slot 2) beside the entry from the cantina
        self.assertIn('GetGlobalNumber("502OND_End_First") == 2', src)                # only on the return from the cantina
        self.assertIn('!GetLocalBoolean(GetObjectByTag("fake_mand", 0), 50)', src)     # not again once the game's own flag marks the scene as started
        self.assertIn("GetEnteringObject() == GetFirstPC()", src)
        self.assertNotIn("K2AP_SceneEnsure", src)                                      # nobody is added to the party
        self.assertTrue(W.scene_table()["k_501_enter"]["501OND"]["area"])

    def test_the_dxun_return_scene_stages_mandalore_before_the_first_entry_flag_is_used(self):
        src = W.scene_source("k_403_enter", ["403DXN"])
        self.assertIn("K2AP_SceneStage(2, 27.15, 156.04, 25.16, 233.90);", src)       # Mandalore (slot 2) at the shuttle arrival
        self.assertIn('GetGlobalNumber("502OND_End_First") > 0', src)
        self.assertIn('!GetLocalBoolean(GetObjectByTag("From_402DXN", 0), 53)', src)  # the game's own once-only flag
        self.assertNotIn("K2AP_SceneEnsure", src)
        self.assertTrue(W.scene_table()["k_403_enter"]["403DXN"]["area"])

    def test_the_inventory_trap_makes_one_pass_and_is_counted_before_it_runs(self):
        src = read("nss/k2se_disp.nss")
        trap = src[src.index("int DispTrapInventory"):src.index("// DeathLink: the player dies.")]
        self.assertEqual(trap.count("GetFirstItemInInventory"), 2)                        # one pass to count, one to take: never a scan per item
        self.assertIn("Random(nLeft) < nTake", trap)
        poll = src[src.index("void DispPollOnce()"):src.index("void DispTick(int nGen)")]
        counted = poll.index('if (sAction == "trap" && sArgs == "inventory")')
        self.assertLess(counted, poll.index("if (!DispApply(oPC, sAction, sArgs))"))       # the number advances first
        self.assertLess(poll.index("DispCounterSet(oPC, nSeq);"), poll.index("if (!DispApply(oPC, sAction, sArgs))"))

    def test_the_companion_unlock_bits_stay_within_the_seven_bits_a_local_number_keeps(self):
        # a local number holds 0-127 (number 5 read 127 in every save, so Mira's bit 7 was lost); both scripts use the same layout
        for name, prefix in (("nss/k2ap_comp.nss", "K2AP_Comp"), ("nss/k2ap_scene.nss", "K2AP_Scene")):
            src = read(name)
            self.assertIn("if (nSlot == 7) return 4;", src)
            self.assertIn("if (nSlot < 7) return 5;", src)
            self.assertIn("return nSlot - 8;", src)
        layout = {slot: ((5, slot) if slot < 7 else (6, 4) if slot == 7 else (6, slot - 8)) for slot in range(12)}
        self.assertTrue(all(shift <= 6 for _, shift in layout.values()))
        self.assertEqual(len(set(layout.values())), 12)                               # no two companions share a bit
        self.assertIn("& 127) | (((GetLocalNumber(oPC, 6) >> 4) & 1) << 7) | ((GetLocalNumber(oPC, 6) & 15) << 8)", read("nss/k2se_poll.nss"))   # the report puts slot n at bit n

    def test_the_dispatcher_waits_while_the_player_controls_a_companions_body(self):
        # In the Dxun tomb GetFirstPC() is a companion; its own old job number looked like a loaded older save and the client sent every job since then again.
        src = read("nss/k2se_disp.nss")
        tick = src[src.index("void DispTick(int nGen)"):src.index("void DispStart()")]
        guard = tick.index('if (GetTag(oPC) != "")')
        self.assertLess(tick.index("GetHitDice(oPC) < 1"), guard)
        self.assertLess(guard, tick.index("DispPollOnce();"))                          # nothing is reported or applied while the body is not the Exile's
        self.assertIn("DelayCommand(1.0, DispTick(nGen));", tick[guard:tick.index("DispPollOnce();")])   # and the loop keeps going for when the Exile is back

    def test_revitalize_heals_more_through_a_check_joined_onto_the_force_power_script(self):
        self.assertEqual(W.SPELLS, {"k_sp1_generic": "k2ap_revit"})                  # every Force power runs this script: the check answers FALSE for all others
        src = read("nss/k2ap_revit.nss")
        self.assertIn("if (nSpell == FORCE_POWER_IMPROVED_REVITALIZE) return 500;", src)   # TEMPORARY: back to 125 after the test run
        self.assertIn("return 250;", src)                                             # Master Revitalize
        self.assertIn("EffectHeal(nHeal)", src)
        self.assertIn("if (nSpell != FORCE_POWER_IMPROVED_REVITALIZE && nSpell != FORCE_POWER_MASTER_REVITALIZE) return FALSE;", src)
        self.assertNotIn("#include", src)                                             # nothing of the game's is copied into it

    def test_the_duel_ring_scene_checks_the_opponent_after_the_fight_start(self):
        src = W.scene_source("a_circle_fight", ["403DXN"])
        self.assertIn("K2AP_SceneRing();", src)
        self.assertNotIn("K2AP_SceneEnsure", src)
        self.assertNotIn("K2AP_SceneStage", src)
        scene = read("nss/k2ap_scene.nss")
        for name in ("npc_davrel", "npc_kex", "npc_tagren", "npc_kelborn", "npc_bralor", "wp_circle_enemy", "403DXN_Battle_Circle"):
            self.assertIn('"%s"' % name, scene)                                       # the names the game's own a_circle_fight uses

    def test_the_scene_table_is_consistent(self):
        table = W.scene_table()
        self.assertIn("233TEL", table["a_mercctalk"])
        for script, modules in table.items():
            for module, entry in modules.items():
                if entry.get("mode") not in ("ring", "unlock"):                       # the duel ring and the door unlock need no companion
                    self.assertTrue(entry["slots"] and all(0 <= int(s) <= 11 for s in entry["slots"]), (script, module))
                self.assertTrue(entry.get("why"), (script, module))
            if script in W.GUARDED or script in W.TURRETS or script in W.HOLD:
                self.fail("%s is a guard/replace/hold script: scenes are not supported there" % script)
            if script in W.GATED:
                self.assertLessEqual(set(modules), {m.upper() for m in W.GATED[script]}, script)

    def test_every_wrapper_reports_what_it_did(self):
        sources = [W.wrapper_source("a_load262", {"006EBO": "FIN2"}),
                   W.guard_source("my_clear_inv"),
                   W.replace_source("a_505turret", W.TURRETS["a_505turret"]),
                   W.replace_source("tr_exit702_end", {"701KOR": ""}, None, None, W.HOLD["tr_exit702_end"])]
        for src in sources:
            self.assertIn("K2AP_Trace(", src)

    def test_the_test_aids_are_in_the_gate_include(self):
        text = read("nss/k2ap_gate.nss")
        self.assertIn('K2SE_ConfigInt("ap_debug", 0)', text)
        self.assertIn('K2SE_ConfigInt("ap_gate_dryrun", 0)', text)
        self.assertIn('"WT|"', text)

    def test_master_hold_numbers_match_the_gates_file(self):
        text = read("nss/k2ap_master.nss")
        for gate in ("NAR3", "DXN3", "DAN2"):
            g = GATES[gate]
            self.assertIn('if (sGate == "%s") return %d;' % (gate, g["tokens_needed"]) if gate == "DAN2" else 'return %d;' % g["tokens_needed"], text)
            self.assertEqual(g["family"], {"NAR3": "Nar Shaddaa", "DXN3": "Dxun/Onderon", "DAN2": "Dantooine"}[gate])
        self.assertEqual((GATES["NAR3"]["tokens_needed"], GATES["DXN3"]["tokens_needed"], GATES["DAN2"]["tokens_needed"]), (3, 3, 2))

    def test_the_masters_script_does_what_the_game_script_does_when_the_gate_is_open(self):
        text = read("nss/ap_jedi_inc.nss")
        self.assertIn("SetGlobalNumber(sGlobal, GetGlobalNumber(sGlobal) + nAdd);", text)
        self.assertIn("K2AP_MasterHold(sGate);", text)
        self.assertIn("ap_jedi_inc", W.SPECIAL)
        self.assertFalse(os.path.exists(os.path.join(ROOT, "nss", "a_global_inc.nss")))         # the game's shared script is no longer replaced

    def test_the_master_modules(self):
        text = read("nss/k2ap_master.nss")
        for module in ("303nar", "506ond", "602dan"):
            self.assertIn('"%s"' % module, text)

    def test_token_need_comes_from_the_gates_file(self):
        src = W.wrapper_source("a_to851", {"222TEL": "FIN3"})
        self.assertIn('"FIN3", "endgame", "Endgame", %d)' % GATES["FIN3"]["tokens_needed"], src)


class TestShortenedPeragusScript(unittest.TestCase):
    """nss/k2ap_per.nss, joined onto every area entry script (the tail of tools/build_area_wrappers.py)."""

    def test_the_area_tail_calls_it_before_the_dispatcher(self):
        import build_area_wrappers as AW
        tail = AW.TAIL_SOURCE
        self.assertIn('#include "k2ap_per"', tail)
        self.assertLess(tail.index("K2AP_PeragusEnter();"), tail.index("DispStart();"))
        self.assertIn("k2ap_per.nss", read("tools/k2compile.py"))                      # the include is copied to the compile folder

    def test_it_acts_only_in_101per_with_the_option_and_the_patch(self):
        src = read("nss/k2ap_per.nss")
        self.assertIn("K2AP_ShortenedPeragus() != 0", src)
        self.assertIn("K2AP_Patched() == 0", src)
        enter = src[src.index("void K2AP_PeragusEnter()"):]
        self.assertIn('GetStringUpperCase(GetModuleName()) != "101PER"', enter)

    def test_the_jump_waits_for_the_end_of_atton_conversation_and_a_calm_moment(self):
        src = read("nss/k2ap_per.nss")
        tick = src[src.index("void K2AP_PerTick(int nGen)\n{"):src.index("// The area entry hook")]
        self.assertIn('GetGlobalNumber("101PER_Know_Adm_Code") != 0 && DispCalm(oPC)', tick)     # the code is given at the last node of the conversation
        self.assertIn('GetTag(oPC) == ""', tick)                                                   # never while a companion's body is the player's
        self.assertIn('StringToInt(K2SE_MemGet("per_gen")) != nGen', tick)                         # one loop at a time

    def test_the_state_of_the_skipped_parts_is_set_before_the_module_is_loaded(self):
        src = read("nss/k2ap_per.nss")
        load = src[src.index("void K2AP_PerLoad(object oPC)"):src.index("void K2AP_PerFade()")]
        for needle in ("AddAvailableNPCByObject(8, oT3)", 'SetGlobalNumber("105PER_T3_End", 2)', 'SetGlobalNumber("101PER_Open_Hatch", 1)', 'AddJournalQuestEntry("MedBayMur", 40)',
                       'CreateItemOnObject("g_i_progspike01", oPC, 4)'):
            self.assertIn(needle, load)
        self.assertLess(load.index('SetGlobalNumber("101PER_Sion_Arrives", 1)'), load.index('StartNewModule("101PER", "From_105PER", "permov03")'))
        self.assertLess(load.index("AddAvailableNPCByObject(8, oT3)"), load.index("DestroyObject(oT3)"))

    def test_act_two_runs_the_stories_own_scripts_in_order(self):
        src = read("nss/k2ap_per.nss")
        two = src[src.index("int K2AP_PerActTwo(object oPC)"):src.index("void K2AP_PerTick(int nGen)\n{")]
        order = [two.index(n) for n in ('"a_spawnkriea2"', '"a_door105per"', '"a_spawnhk50"')]
        self.assertEqual(order, sorted(order))
        self.assertIn('GetGlobalNumber("101PER_Kreia_Joined") == 0', two)                          # the HK-50 scene only after Kreia has joined
        self.assertNotIn('"a_hatchopen', src)                                                      # the entry script itself is never run through ExecuteScript


if __name__ == "__main__":
    unittest.main()
