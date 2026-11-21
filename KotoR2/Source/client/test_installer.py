"""Tests of the player installer (installer/install_bundle.py) against a scratch bundle, a scratch game folder and scratch AppData folders. No game, no network:
the pip step, the payload build and the seed revert are replaced. Run through tools/run_client_tests.py."""
import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "installer"))
import install_bundle as I  # noqa: E402

DLL = b"MZ-our-extension"


class Rig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.bundle = os.path.join(self.tmp, "bundle")
        self.game = os.path.join(self.tmp, "game")
        self.local = os.path.join(self.tmp, "local")
        self.machine = os.path.join(self.tmp, "machine")
        for rel in ("extender/version.dll", "client/KotorTwoClient.py", "core/CommonClient.py", "tools/build_payload.py", "tools/nwnsc/nwnsc.exe", "tools/mdlops/mdlops.exe"):
            self.put(os.path.join(self.bundle, *rel.split("/")), DLL if rel.endswith("version.dll") else b"x")
        self.put(os.path.join(self.game, "swkotor2.exe"), b"exe")
        self.saved = (I.BUNDLE, os.environ.get("LOCALAPPDATA"), os.environ.get("PROGRAMDATA"), I.game_running, I.pip_install, I.build_payload, I.revert_seed)
        I.BUNDLE = self.bundle
        os.environ["LOCALAPPDATA"], os.environ["PROGRAMDATA"] = self.local, self.machine
        I.game_running = lambda: False
        self.calls = []
        I.pip_install = lambda: self.calls.append("pip")
        I.build_payload = lambda game_dir: self.calls.append("payload")
        I.revert_seed = lambda game_dir: self.calls.append("revert") or []
        I.WARNINGS.clear()

    def tearDown(self):
        I.BUNDLE, la, pd, I.game_running, I.pip_install, I.build_payload, I.revert_seed = self.saved
        for key, value in (("LOCALAPPDATA", la), ("PROGRAMDATA", pd)):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(self.tmp, ignore_errors=True)

    @staticmethod
    def put(path, data):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data if isinstance(data, bytes) else data.encode("utf-8"))

    def read(self, *parts):
        with open(os.path.join(*parts), encoding="utf-8") as f:
            return f.read()

    def run_quiet(self, fn, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            try:
                fn(*args)
            except SystemExit as e:
                return out.getvalue(), e.code
        return out.getvalue(), 0

    def config(self):
        return os.path.join(self.local, "K2SE", "config.txt")


class TestPreflight(Rig):
    def test_the_first_game_folder_is_named_for_what_it_is(self):
        k1 = os.path.join(self.tmp, "k1")
        self.put(os.path.join(k1, "swkotor.exe"), b"exe")
        text, code = self.run_quiet(I.install, k1)
        self.assertEqual(code, 1)
        self.assertIn("KOTOR 1 folder", text)
        self.assertEqual(self.calls, [])

    def test_a_folder_without_the_game_and_a_missing_folder_say_so(self):
        text, code = self.run_quiet(I.install, os.path.join(self.tmp, "empty"))
        self.assertEqual(code, 1)
        self.assertIn("does not exist", text)
        os.makedirs(os.path.join(self.tmp, "empty"))
        text, code = self.run_quiet(I.install, os.path.join(self.tmp, "empty"))
        self.assertIn("swkotor2.exe is not in it", text)

    def test_an_incomplete_download_lists_what_is_missing_and_nothing_is_touched(self):
        os.remove(os.path.join(self.bundle, "tools", "mdlops", "mdlops.exe"))
        text, code = self.run_quiet(I.install, self.game)
        self.assertEqual(code, 1)
        self.assertIn("mdlops.exe", text)
        self.assertFalse(os.path.exists(os.path.join(self.game, "version.dll")))
        self.assertEqual(self.calls, [])

    def test_a_running_game_stops_the_install(self):
        I.game_running = lambda: True
        text, code = self.run_quiet(I.install, self.game)
        self.assertEqual(code, 1)
        self.assertIn("KOTOR 2 is running", text)

    def test_the_microsoft_store_python_is_refused(self):
        real = sys.executable
        sys.executable = r"C:\Users\x\AppData\Local\Microsoft\WindowsApps\python3.12.exe"
        try:
            text, code = self.run_quiet(I.install, self.game)
        finally:
            sys.executable = real
        self.assertEqual(code, 1)
        self.assertIn("Microsoft Store", text)


class TestInstall(Rig):
    def test_install_puts_everything_in_place(self):
        text, code = self.run_quiet(I.install, self.game)
        self.assertEqual(code, 0, text)
        self.assertEqual(self.calls, ["pip", "payload"])
        with open(os.path.join(self.game, "version.dll"), "rb") as f:
            self.assertEqual(f.read(), DLL)
        config = self.read(self.config())
        self.assertIn("disp_enable=1", config)
        self.assertIn("disp_period=3", config)
        self.assertEqual(self.read(self.local, "KotorTwoAP", "install_path.txt"), os.path.join(self.bundle, "client"))
        self.assertEqual(self.read(self.machine, "KotorTwoAP", "core_path.txt"), os.path.join(self.bundle, "core"))
        self.assertEqual(self.read(self.local, "KotorTwoAP", "python_path.txt"), sys.executable)
        self.assertEqual(self.read(self.local, "K2SE", "ap", "game_dir.txt"), os.path.normpath(self.game))
        self.assertTrue(os.path.isfile(I.manifest_path()))

    def test_running_it_again_changes_nothing(self):
        self.run_quiet(I.install, self.game)
        first = self.read(self.config())
        text, code = self.run_quiet(I.install, self.game)
        self.assertEqual(code, 0)
        self.assertIn("already ours", text)
        self.assertEqual(self.read(self.config()), first)

    def test_the_game_folder_is_found_in_the_usual_place_when_none_is_given(self):
        saved = I.STEAM_DEFAULTS
        I.STEAM_DEFAULTS = (os.path.join(self.tmp, "nowhere"), self.game)
        try:
            self.assertEqual(I.find_game_dir(None), self.game)
            self.assertEqual(I.find_game_dir(r"C:\somewhere"), r"C:\somewhere")          # a given folder is checked by the preflight, not replaced
            I.STEAM_DEFAULTS = (os.path.join(self.tmp, "nowhere"),)
            self.assertIsNone(I.find_game_dir(None))
        finally:
            I.STEAM_DEFAULTS = saved

    def test_a_dll_that_is_not_ours_is_kept_and_comes_back(self):
        self.put(os.path.join(self.game, "version.dll"), b"MZ-another-mod")
        self.run_quiet(I.install, self.game)
        with open(os.path.join(self.game, "version_before_k2ap.dll"), "rb") as f:
            self.assertEqual(f.read(), b"MZ-another-mod")
        with open(os.path.join(self.game, "version.dll"), "rb") as f:
            self.assertEqual(f.read(), DLL)
        self.run_quiet(I.uninstall)
        with open(os.path.join(self.game, "version.dll"), "rb") as f:
            self.assertEqual(f.read(), b"MZ-another-mod")
        self.assertFalse(os.path.exists(os.path.join(self.game, "version_before_k2ap.dll")))

    def test_a_failed_step_leaves_a_record_so_the_install_can_be_undone(self):
        def boom():
            raise SystemExit(1)
        I.pip_install = boom
        self.run_quiet(I.install, self.game)
        self.assertTrue(os.path.isfile(I.manifest_path()))                 # the extension was already copied
        text, code = self.run_quiet(I.uninstall)
        self.assertEqual(code, 0, text)
        self.assertFalse(os.path.exists(os.path.join(self.game, "version.dll")))


class TestConfig(Rig):
    def test_switches_in_the_seeds_block_are_not_counted_and_old_values_come_back(self):
        self.put(self.config(), "stage=0\ndisp_enable=0\n# --- k2ap begin (written by the Archipelago client; do not edit) ---\ndisp_period=9\nap_goal=0\n# --- k2ap end ---\n")
        record = I.set_config()
        text = self.read(self.config())
        self.assertIn("disp_enable=1", text)
        self.assertNotIn("disp_enable=0", text)
        self.assertIn("disp_period=9", text)                               # the block's own line is left alone
        self.assertIn("disp_period=3", text.split("# --- k2ap end ---")[1])  # and the real switch is added outside it
        I.unset_config(record)
        after = self.read(self.config())
        self.assertIn("disp_enable=0", after)
        self.assertNotIn("disp_period=3", after)
        self.assertIn("ap_goal=0", after)

    def test_a_missing_config_is_created(self):
        record = I.set_config()
        self.assertEqual(record, {"disp_enable": None, "disp_period": None})
        self.assertEqual(self.read(self.config()).split(), ["disp_enable=1", "disp_period=3"])


class TestUninstall(Rig):
    def test_uninstall_undoes_the_install(self):
        self.run_quiet(I.install, self.game)
        self.calls.clear()
        text, code = self.run_quiet(I.uninstall)
        self.assertEqual(code, 0, text)
        self.assertEqual(self.calls, ["revert"])
        self.assertFalse(os.path.exists(os.path.join(self.game, "version.dll")))
        self.assertFalse(os.path.exists(os.path.join(self.local, "KotorTwoAP", "install_path.txt")))
        self.assertFalse(os.path.exists(os.path.join(self.machine, "KotorTwoAP", "core_path.txt")))
        self.assertFalse(os.path.exists(I.manifest_path()))
        self.assertIn("Uninstall complete", text)
        self.assertNotIn("disp_enable", self.read(self.config()))

    def test_without_a_record_it_says_what_to_do_by_hand(self):
        text, code = self.run_quiet(I.uninstall)
        self.assertEqual(code, 1)
        self.assertIn("no record", text)
        self.assertIn("/k2_unpatch", text)

    def test_a_running_game_stops_the_uninstall(self):
        self.run_quiet(I.install, self.game)
        I.game_running = lambda: True
        text, code = self.run_quiet(I.uninstall)
        self.assertEqual(code, 1)
        self.assertTrue(os.path.isfile(os.path.join(self.game, "version.dll")))


class TestFiles(unittest.TestCase):
    def test_the_batch_files_have_windows_line_endings_and_the_paths_they_need(self):
        folder = os.path.join(HERE, "..", "installer")
        for name in ("Install.bat", "Uninstall.bat", "Start_KOTOR2_Client.bat"):
            with open(os.path.join(folder, name), "rb") as f:
                data = f.read()
            self.assertIn(b"\r\n", data, name)
            self.assertNotIn(b"\n", data.replace(b"\r\n", b""), name)           # a label (goto) fails in a batch file with bare line feeds
        with open(os.path.join(folder, "Install.bat"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn(r"core\requirements.txt", text)
        self.assertIn(r"installer\install_bundle.py", text)
        self.assertIn("swkotor2.exe", text)
        with open(os.path.join(folder, "Start_KOTOR2_Client.bat"), encoding="utf-8") as f:
            start = f.read()
        self.assertIn(r"%LOCALAPPDATA%\KotorTwoAP\python_path.txt", start)       # the marker folder the Launcher reads (worlds/kotor2/ClientLauncher.py)
        self.assertIn("KotorTwoClient.py", start)


if __name__ == "__main__":
    unittest.main()
