"""The "no message from the game" warning must not fire while the game files are being patched (the game is usually not running yet then);
its silence timer starts when patching is done."""
import os
import threading
import time
import unittest

KOTOR_CLIENT = os.path.join(os.path.dirname(__file__), "..", "..", "..", "KotorClient.py")


def _context():
    import KotorClient
    ctx = KotorClient.KotorContext.__new__(KotorClient.KotorContext)   # no connection, no UI: only the fields the check reads
    ctx._patching_depth = 0
    ctx._patching_lock = threading.Lock()
    ctx._last_game_event_time = time.time()
    ctx._staleness_warned = False
    return ctx


@unittest.skipUnless(os.path.exists(KOTOR_CLIENT), "client not next to this world")
class TestStaleWarning(unittest.TestCase):
    def test_a_warning_is_due_after_thirty_seconds_of_silence(self):
        ctx = _context()
        self.assertIsNone(ctx._staleness_due())
        ctx._last_game_event_time = time.time() - 31
        self.assertGreater(ctx._staleness_due(), 30)

    def test_no_warning_while_patching_however_long_it_takes(self):
        ctx = _context()
        ctx._last_game_event_time = time.time() - 300
        with ctx._patching():
            self.assertIsNone(ctx._staleness_due())

    def test_the_silence_timer_starts_when_patching_ends(self):
        ctx = _context()
        ctx._last_game_event_time = time.time() - 300
        with ctx._patching():
            pass
        self.assertIsNone(ctx._staleness_due())          # the 300 s of silence during patching do not count
        ctx._last_game_event_time = time.time() - 31     # 31 s of silence after it does
        self.assertIsNotNone(ctx._staleness_due())

    def test_overlapping_patch_runs_hold_it_until_the_last_ends(self):
        ctx = _context()
        ctx._last_game_event_time = time.time() - 300
        with ctx._patching():
            with ctx._patching():
                pass
            self.assertIsNone(ctx._staleness_due())
            self.assertEqual(ctx._patching_depth, 1)
        self.assertEqual(ctx._patching_depth, 0)

    def test_a_failed_patch_still_releases_the_hold(self):
        ctx = _context()
        with self.assertRaises(RuntimeError):
            with ctx._patching():
                raise RuntimeError("a patch step failed")
        self.assertEqual(ctx._patching_depth, 0)

    def test_a_warning_already_given_is_not_repeated(self):
        ctx = _context()
        ctx._last_game_event_time = time.time() - 300
        ctx._staleness_warned = True
        self.assertIsNone(ctx._staleness_due())

    def test_all_three_patching_paths_use_the_guard(self):
        with open(KOTOR_CLIENT, encoding="utf-8") as f:
            source = f.read()
        self.assertIn("with self._patching():\n            self._apply_module_rim_patches_in_order_body(gate_key, force)", source.replace("\r\n", "\n"))
        self.assertIn("with self.ctx._patching():\n            ok, msg = revert_all_game_files()", source.replace("\r\n", "\n"))
        self.assertIn("with self.ctx._patching():\n            ok, msg = apply_all_patches()", source.replace("\r\n", "\n"))
