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
    def test_gated_module_asks_the_gate_first(self):
        src = W.wrapper_source("a_load262", {"006EBO": "FIN2"}, [("a_load262_orig_3", ["006EBO"]), ("a_load262_orig_2", ["261TEL"])], None)
        self.assertIn('if (sMod == "006ebo")', src)
        gate_call = src.index('K2AP_GateOpen("FIN2", "endgame", "Endgame", 2)')
        self.assertLess(gate_call, src.index('ExecuteScript("a_load262_orig_3"'))
        # another module that carries its own copy still runs its own original, ungated
        self.assertIn('if (sMod == "261tel") { ExecuteScript("a_load262_orig_2", OBJECT_SELF); return; }', src)

    def test_default_original_runs_everywhere_else(self):
        src = W.wrapper_source("a_dhagon", {"502OND": "DXN2"}, [("a_dhagon_orig", ["502OND"])], "a_dhagon_orig")
        self.assertTrue(src.rstrip().endswith('ExecuteScript("a_dhagon_orig", OBJECT_SELF);\n}'))

    def test_locker_guard_runs_the_original_then_returns_the_tokens(self):
        src = W.guard_source("my_clear_inv", [("my_clear_inv_orig", ["202TEL"])], None)
        self.assertLess(src.index('ExecuteScript("my_clear_inv_orig"'), src.index("K2AP_TokensFromLockers();"))
        self.assertIn("my_clear_inv", W.GUARDED)

    def test_turret_skips_run_only_when_the_seed_says_so(self):
        for name, bodies in W.TURRETS.items():
            src = W.replace_source(name, bodies, [(name + "_orig", list(bodies))], None)
            module = next(iter(bodies)).lower()
            self.assertIn('if (sMod == "%s" && (K2AP_SkipTurrets()))' % module, src)
            self.assertIn('if (sMod == "%s") { ExecuteScript("%s_orig"' % (module, name), src)       # the seed off: the original, as before
        self.assertIn('"107PER_MG_DEAD", 25', W.TURRETS["a_load003ebo"]["106PER"])
        self.assertIn("int K2AP_SkipTurrets()", k2_seed.nss_include())

    def test_trigger_gates_only_hold_the_party_leader_and_the_right_branch(self):
        src = W.wrapper_source("tr_enclave_cam", {"605DAN": W.GATED["tr_enclave_cam"]["605DAN"]}, [("tr_enclave_cam_orig", ["605DAN"])], None)
        self.assertIn('if (GetIsPartyLeader(GetEnteringObject()) && GetGlobalNumber("650DAN_Rebuilt") != 0)', src)
        self.assertLess(src.index("650DAN_Rebuilt"), src.index('K2AP_GateOpen("FIN1"'))       # the gate is asked only inside that branch
        self.assertEqual(W.GATED["tr_vash"]["702KOR"][0], "KOR2")

    def test_academy_door_stays_open_until_vash_is_found(self):
        src = W.replace_source("tr_exit702_end", {"701KOR": ""}, [("tr_exit702_end_orig", ["701KOR"])], None, W.HOLD["tr_exit702_end"])
        self.assertIn('GetGlobalNumber("702KOR_Vash") != 1', src)
        self.assertLess(src.index("return;"), src.index('ExecuteScript("tr_exit702_end_orig"'))

    def test_every_wrapper_reports_what_it_did(self):
        sources = [W.wrapper_source("a_load262", {"006EBO": "FIN2"}, [("a_load262_orig", ["006EBO"])], None),
                   W.guard_source("my_clear_inv", [("my_clear_inv_orig", ["202TEL"])], None),
                   W.replace_source("a_505turret", W.TURRETS["a_505turret"], [("a_505turret_orig", ["504OND"])], None),
                   W.replace_source("tr_exit702_end", {"701KOR": ""}, [("o", ["701KOR"])], None, W.HOLD["tr_exit702_end"])]
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
        src = W.wrapper_source("a_to851", {"222TEL": "FIN3"}, [("a_to851_orig", ["222TEL"])], "a_to851_orig")
        self.assertIn('"FIN3", "endgame", "Endgame", %d)' % GATES["FIN3"]["tokens_needed"], src)


if __name__ == "__main__":
    unittest.main()
