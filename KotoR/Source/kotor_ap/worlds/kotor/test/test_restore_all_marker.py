"""
Reverting the game files (/ap_restore_all) also drops the client's record of what it patched, so the next connect patches again instead of
skipping patches whose files were just reverted.
"""
import json
import os
import tempfile
import types
import unittest
from unittest import mock

KOTOR_CLIENT = os.path.join(os.path.dirname(__file__), "..", "..", "..", "KotorClient.py")


@unittest.skipUnless(os.path.exists(KOTOR_CLIENT), "client not next to this world")
class TestRestoreAllClearsMarker(unittest.TestCase):
    def setUp(self):
        import KotorClient
        self.module = KotorClient
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.marker = os.path.join(self.dir.name, "_patched_seeds.json")
        with open(self.marker, "w", encoding="utf-8") as f:
            json.dump({"additional_enemies": "abc", "__game_dir__": self.module.GAME_DIR}, f)
        patcher = mock.patch.object(self.module, "PATCHED_SEEDS_MARKER_PATH", self.marker)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _revert(self, returncode):
        run = mock.Mock(return_value=types.SimpleNamespace(returncode=returncode, stdout="Restored 3 file(s)", stderr=""))
        with mock.patch.object(self.module.subprocess, "run", run):
            return self.module.revert_all_game_files()

    def test_the_record_is_gone_after_a_revert(self):
        ok, _ = self._revert(0)
        self.assertTrue(ok)
        self.assertFalse(os.path.exists(self.marker))
        self.assertIsNone(self.module._load_patched_seed("additional_enemies"))

    def test_the_record_is_gone_after_a_partial_failure_too(self):
        ok, _ = self._revert(1)
        self.assertFalse(ok)
        self.assertFalse(os.path.exists(self.marker))

    def test_a_missing_record_is_fine(self):
        os.remove(self.marker)
        ok, _ = self._revert(0)
        self.assertTrue(ok)

    def _gate(self, calls, key="additional_enemies", gate="abc"):
        def apply_fn():
            calls.append(key)
            return True, "done"
        stand_in = types.SimpleNamespace(_patch_failures=0)
        self.module.KotorContext._apply_seed_patch_if_new(stand_in, key, gate, apply_fn)

    def test_the_patch_is_skipped_while_the_record_matches_and_runs_again_after_a_revert(self):
        calls = []
        self._gate(calls)
        self.assertEqual(calls, [], "an unchanged record skips the patch (the reason the revert has to drop it)")
        self._revert(0)
        self._gate(calls)
        self.assertEqual(calls, ["additional_enemies"], "after a revert the next connect must patch again")
        self._gate(calls)
        self.assertEqual(calls, ["additional_enemies"], "and records it, so the connect after that skips")

    def test_a_patch_all_records_what_it_applied_so_the_next_connect_does_not_repeat_it(self):
        self._revert(0)
        m = self.module
        results = {name: (True, "done") for name in (
            "apply_item_suppression", "apply_story_gates", "apply_door_randomizer", "apply_additional_enemies", "apply_bazaar_tokens",
            "apply_boss_datapads", "apply_droid_assets")}
        results["apply_bazaar_tokens"] = (False, "boom")
        patches = [mock.patch.object(m, name, return_value=value) for name, value in results.items()]
        patches += [mock.patch.object(m, "_run_patch_script", return_value=(True, "")),
                    mock.patch.object(m, "regenerate_makejedi_suppressor", return_value=(True, "")),
                    mock.patch.object(m, "_last_patch_gate_key", "gate-1")]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        m.apply_all_patches()
        for key in ("loot_disturb", "item_suppression", "story_gates", "door_randomizer", "additional_enemies"):
            self.assertEqual(m._load_patched_seed(key), "gate-1", key)
        self.assertIsNone(m._load_patched_seed("bazaar_tokens"), "a patch that failed is not recorded")

    def test_a_patch_all_before_any_connect_records_nothing(self):
        self._revert(0)
        m = self.module
        patches = [mock.patch.object(m, name, return_value=(True, "")) for name in (
            "apply_item_suppression", "apply_story_gates", "apply_door_randomizer", "apply_additional_enemies", "apply_bazaar_tokens",
            "apply_boss_datapads", "apply_droid_assets")]
        patches += [mock.patch.object(m, "_run_patch_script", return_value=(True, "")),
                    mock.patch.object(m, "regenerate_makejedi_suppressor", return_value=(True, "")),
                    mock.patch.object(m, "_last_patch_gate_key", None)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        m.apply_all_patches()
        self.assertFalse(os.path.exists(self.marker))


if __name__ == "__main__":
    unittest.main()
