"""
build_scripts.py compiles the repository's NWScript sources into the compiled scripts the release zips carry. It has to tell the scripts the game runs from the include
files they share, and it must not leave a half-written or stale compiled file behind when a script does not compile.
"""
import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
import build_scripts  # noqa: E402


def write(folder, name, text):
    with open(os.path.join(folder, name), "w") as f:
        f.write(text)


class TestEntryPoints(unittest.TestCase):
    def test_only_scripts_the_game_can_run_are_picked(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "ap_run.nss", "void main() { }\n")
            write(tmp, "ap_cond.nss", "int StartingConditional()\n{\n    return TRUE;\n}\n")
            write(tmp, "ap_include.nss", "int Helper(int n) { return n; }\n")
            write(tmp, "ap_commented.nss", "// void main() { }\nint Helper() { return 1; }\n")
            write(tmp, "kse.nss", "void main() { }\n")
            write(tmp, "nwscript.nss", "void main() { }\n")
            write(tmp, "k_inc_utility.nss", "void main() { }\n")
            write(tmp, "notes.txt", "void main() { }\n")
            self.assertEqual(build_scripts.entry_points(tmp), ["ap_cond", "ap_run"])
            self.assertEqual(build_scripts.entry_points(tmp, only=["ap_run"]), ["ap_run"])


@unittest.skipUnless(os.path.isfile(os.path.join(REPO_ROOT, "tools", "nwnsc", "nwnsc.exe"))
                     and os.path.isfile(os.path.join(REPO_ROOT, "extender", "scripts_src", "nwscript.nss")), "needs nwnsc and the game's nwscript.nss")
class TestBuild(unittest.TestCase):
    def test_a_good_script_compiles_and_a_bad_one_leaves_nothing(self):
        src_dir = os.path.join(REPO_ROOT, "extender", "scripts_src")
        with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as out:
            for name in ("nwscript.nss", "kse.nss"):
                with open(os.path.join(src_dir, name), "rb") as f, open(os.path.join(src, name), "wb") as g:
                    g.write(f.read())
            write(src, "ap_good.nss", '#include "kse"\nvoid main() { KSE_Diag(1, "AP|PING|x"); }\n')
            write(src, "ap_bad.nss", "void main() { int x = ; }\n")
            with open(os.path.join(out, "ap_bad.ncs"), "wb") as f:
                f.write(b"stale")
            built, failed = build_scripts.build(src, out)
            self.assertEqual(built, ["ap_good"])
            self.assertEqual([n for n, _why in failed], ["ap_bad"])
            self.assertTrue(os.path.isfile(os.path.join(out, "ap_good.ncs")))
            with open(os.path.join(out, "ap_bad.ncs"), "rb") as f:
                self.assertEqual(f.read(), b"stale")          # a failed compile does not touch an existing file
            self.assertFalse(os.path.exists(os.path.join(out, "ap_bad.ncs.building")))


if __name__ == "__main__":
    unittest.main()
