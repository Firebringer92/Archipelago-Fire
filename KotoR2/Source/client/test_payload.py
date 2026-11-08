"""Test of the payload builder (tools/build_payload.py) on the real game files: it makes a flat folder of compiled scripts and area files, nothing else, the same
on a second run, and drops what an earlier run made that this one no longer does. Needs the game installed; run through tools/run_client_tests.py."""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from k2_patch import PAYLOAD_KEY_FILES, payload_files  # noqa: E402
import build_payload as BP  # noqa: E402

GAME = os.environ.get("K2_GAME_DIR") or r"C:\Program Files (x86)\Steam\steamapps\common\Knights of the Old Republic II"
HAVE_GAME = os.path.isfile(os.path.join(GAME, "swkotor2.exe"))


class TestSources(unittest.TestCase):
    def test_every_project_script_exists(self):
        for name in BP.PROJECT_SCRIPTS:
            self.assertTrue(os.path.isfile(os.path.join(ROOT, "nss", name + ".nss")), name)

    def test_the_key_files_the_path_report_asks_for_are_made_by_a_step(self):
        project = {n + ".ncs" for n in BP.PROJECT_SCRIPTS}
        other = {"k2se_rb.ncs", "a_bet3m4.ncs", "a_hatchopen.ncs", "ap_vd_do.ncs"}              # class rebuild, the two harness wrappers, a Vendor script
        self.assertTrue(set(PAYLOAD_KEY_FILES) <= project | other)


@unittest.skipUnless(HAVE_GAME, "needs the game files")
class TestBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = tempfile.mkdtemp()
        cls.report = BP.build(GAME, cls.out)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.out, ignore_errors=True)

    def test_no_problems_and_the_key_files_are_there(self):
        self.assertEqual(self.report["problems"], [])
        files = payload_files(self.out)
        for name in PAYLOAD_KEY_FILES:
            self.assertIn(name, files)

    def test_only_scripts_and_area_files_reach_override(self):
        files = payload_files(self.out)               # what the client would copy: regular files at the top of the folder
        self.assertGreater(len(files), 150)
        self.assertEqual([n for n in files if not n.endswith((".ncs", ".are"))], [])
        self.assertEqual([n for n in files if n.endswith(".nwnsc.ncs")], [])

    def test_the_two_harness_scripts_are_wrapped_with_their_originals(self):
        files = payload_files(self.out)
        for name in ("a_bet3m4", "a_hatchopen"):
            self.assertIn(name + ".ncs", files)
            self.assertIn(name + "_orig.ncs", files)
            self.assertLess(len(files[name + "_orig.ncs"]), 5000)       # the game's own small script, not the research harness

    def test_the_area_hooks_cover_the_modules_without_an_on_enter_script(self):
        areas = sorted(n for n in payload_files(self.out) if n.endswith(".are"))
        self.assertEqual(len(areas), 24)                  # tools/build_area_hooks.py EMPTY_MODULES

    def test_patching_a_copy_of_the_real_override_and_reverting_gives_it_back_byte_for_byte(self):
        from k2_patch import Patcher
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        game = os.path.join(root, "game")
        os.makedirs(os.path.join(game, "Modules"))
        open(os.path.join(game, "swkotor2.exe"), "wb").close()
        real = os.path.join(GAME, "Override")
        if not os.path.isdir(real):
            real = os.path.join(GAME, "override")
        shutil.copytree(real, os.path.join(game, "Override"), ignore=shutil.ignore_patterns("_k2ap_backup"))       # a patched game has our backup folder: not part of the scenario

        def snapshot():
            out = {}
            for base, _dirs, names in os.walk(os.path.join(game, "Override")):
                for n in names:
                    with open(os.path.join(base, n), "rb") as f:
                        out[os.path.relpath(os.path.join(base, n), game)] = hashlib.sha1(f.read()).hexdigest()      # hashes: a failure must not diff 100 MB
            return out
        before = snapshot()
        state = os.path.join(root, "K2SE", "ap")
        patcher = Patcher(game, state, running=lambda: False, config_path=os.path.join(root, "K2SE", "config.txt"))
        result = patcher.apply(payload_files(self.out), config=["ap_seed_guard=1"])
        self.assertEqual(result.errors, [])
        after = snapshot()
        self.assertGreater(len(after), len(before))
        for name in ("a_bet3m4.ncs", "a_hatchopen.ncs"):                  # the research harness (if this install has it) is replaced by the wrapper and put back below
            self.assertEqual(after[os.path.join("Override", name)], hashlib.sha1(payload_files(self.out)[name]).hexdigest())
        self.assertEqual(patcher.apply(payload_files(self.out)).created, [])   # the second patch writes nothing new
        reverted = patcher.revert()
        self.assertEqual(reverted.errors, [])
        now = snapshot()
        self.assertEqual(sorted(set(now) ^ set(before)), [])             # nothing left behind, nothing lost
        self.assertEqual([n for n in before if now[n] != before[n]], [])

    def test_a_second_run_is_identical_and_removes_a_stale_file(self):
        stale = os.path.join(self.out, "zz_stale.ncs")
        with open(stale, "wb") as f:
            f.write(b"x")
        with open(os.path.join(self.out, "_build", "files.json")) as f:
            names = json.load(f)
        with open(os.path.join(self.out, "_build", "files.json"), "w") as f:
            json.dump(names + ["zz_stale.ncs"], f)
        before = dict(self.report["files"])
        again = BP.build(GAME, self.out)
        self.assertEqual(again["problems"], [])
        self.assertEqual(again["files"], before)
        self.assertFalse(os.path.exists(stale))


if __name__ == "__main__":
    unittest.main()
