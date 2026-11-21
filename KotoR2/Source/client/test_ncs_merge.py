"""Tests of tools/ncs_merge.py (joins compiled scripts without ExecuteScript). Needs the game's include files for the compiler; run through tools/run_client_tests.py."""
import os
import shutil
import struct
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import ncs_merge  # noqa: E402
import ncs_nops  # noqa: E402

GAME = os.environ.get("K2_GAME_DIR") or r"C:\Program Files (x86)\Steam\steamapps\common\Knights of the Old Republic II"
HAVE_GAME = os.path.isfile(os.path.join(GAME, "swkotor2.exe"))


@unittest.skipUnless(HAVE_GAME, "needs the game files for the compiler's include")
class TestMerge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import k2compile
        import tsl_data
        cls.work = tempfile.mkdtemp()
        k2compile.prepare_include_dir(cls.work, tsl_data.GAME)
        cls.k2compile = k2compile

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work, ignore_errors=True)

    def comp(self, name, source):
        with open(os.path.join(self.work, name + ".nss"), "w") as f:
            f.write(source)
        ok, message = self.k2compile.compile_script(self.work, name)
        self.assertTrue(ok, message)
        with open(os.path.join(self.work, name + ".ncs"), "rb") as f:
            return f.read()

    def calls(self, data):
        """[(opcode, target)] of the jumps and subroutine calls in the first instructions up to the first RETN of the stub."""
        out = []
        for pos, _ in ncs_nops.parse(data):
            if data[pos] in ncs_nops.JUMPS:
                out.append((data[pos], ncs_nops._target(data, pos)))
            if data[pos] == 0x20:
                break
        return out

    def test_a_script_is_kept_byte_for_byte_inside_the_merged_one(self):
        a = self.comp("m_a", 'void main() { SetGlobalNumber("m_a", 1); }\n')
        tail = self.comp("m_t", 'void main() { SetGlobalNumber("m_t", 1); }\n')
        out = ncs_merge.merge([(a, None)], post=tail)
        self.assertIn(a[ncs_merge.HEADER_LEN:], out)
        self.assertIn(tail[ncs_merge.HEADER_LEN:], out)
        self.assertEqual(struct.unpack_from(">I", out, 9)[0], len(out))
        self.assertTrue(ncs_merge.check(out))

    def test_the_stub_calls_the_original_then_the_tail_then_returns(self):
        a = self.comp("m_a2", 'void main() { SetGlobalNumber("m_a", 1); }\n')
        tail = self.comp("m_t2", 'void main() { SetGlobalNumber("m_t", 1); }\n')
        out = ncs_merge.merge([(a, None)], post=tail)
        stub = self.calls(out)
        self.assertEqual([op for op, _ in stub], [0x1E, 0x1E])
        self.assertEqual(out[13 + 12:13 + 14], bytes([0x20, 0x00]))             # RETN right after the two calls
        self.assertEqual(stub[0][1], 13 + 14)                                     # the original starts behind the stub

    def test_a_held_check_skips_everything(self):
        a = self.comp("m_a3", 'void main() { SetGlobalNumber("m_a", 1); }\n')
        pre = self.comp("m_p3", 'int StartingConditional() { return GetGlobalNumber("hold") == 1; }\n')
        out = ncs_merge.merge([(a, None)], pre=pre)
        calls = self.calls(out)
        self.assertEqual([op for op, _ in calls], [0x1E, 0x25, 0x1E])               # JSR pre, JNZ end, JSR original
        retn = next(p for p, _ in ncs_nops.parse(out) if out[p] == 0x20)
        self.assertEqual(calls[1][1], retn)                                       # a non-zero answer lands on the final RETN

    def test_two_originals_are_chosen_by_the_picker(self):
        a = self.comp("m_a4", 'void main() { SetGlobalNumber("m_a", 1); }\n')
        b = self.comp("m_b4", 'void main() { SetGlobalNumber("m_b", 1); }\n')
        pick = self.comp("m_k4", 'int StartingConditional() { return GetStringLowerCase(GetModuleName()) == "x"; }\n')
        out = ncs_merge.merge([(a, pick), (b, None)])
        self.assertIn(a[ncs_merge.HEADER_LEN:], out)
        self.assertIn(b[ncs_merge.HEADER_LEN:], out)
        self.assertEqual([op for op, _ in self.calls(out)], [0x1E, 0x1F, 0x1E, 0x1D, 0x1E])     # JSR picker, JZ, JSR a, JMP after, JSR b
        ncs_merge.check(out)

    def test_an_original_without_a_picker_must_be_last(self):
        a = self.comp("m_a5", 'void main() { }\n')
        with self.assertRaises(ncs_merge.MergeError):
            ncs_merge.merge([(a, None), (a, None)])

    def test_a_script_with_global_variables_merges_and_a_pre_check_must_return_an_int(self):
        with_globals = self.comp("m_g6", 'int g = 5;\nvoid main() { SetGlobalNumber("m_g", g); }\n')      # nwnsc starts it with the same stub: it merges
        self.assertTrue(ncs_merge.check(ncs_merge.merge([(with_globals, None)])))
        pre_void = self.comp("m_v6", 'void main() { }\n')
        with self.assertRaises(ncs_merge.MergeError):
            ncs_merge.merge([(pre_void, None)], pre=pre_void)                  # a pre-check must return an int

    def test_a_damaged_script_is_refused(self):
        a = self.comp("m_a7", 'void main() { }\n')
        with self.assertRaises(ncs_merge.MergeError):
            ncs_merge.merge([(a[:-1], None)])

    def test_the_games_own_entry_scripts_merge_and_decode(self):
        import build_area_wrappers as AW
        tail = AW.compile_source(self.work, "m_tail", AW.TAIL_SOURCE)
        seen = 0
        for name, mods in AW.area_scripts().items():
            variants = {}
            for m in mods:
                data = AW.script_bytes(name, m)
                if data is not None:
                    variants.setdefault(data, []).append(m)
            out = AW.merged(self.work, "m_" + name, [(d, ms) for d, ms in variants.items()], tail)
            for data in variants:
                self.assertIn(data[ncs_merge.HEADER_LEN:], out)           # the game's script, untouched
            seen += 1
        self.assertGreater(seen, 40)


if __name__ == "__main__":
    unittest.main()
