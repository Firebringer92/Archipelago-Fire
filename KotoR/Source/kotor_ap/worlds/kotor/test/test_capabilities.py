"""
The capability check (scripts/check_capabilities.py) keeps the code in the download limited in what it can do: running programs, opening connections, deleting files and importing by name
must be listed in scripts/capabilities.json with a reason, and eval, exec, pickle, marshal, ctypes, the registry and shell=True are never allowed. These tests check the checker
on small sources, and the manifest itself.
"""
import json
import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
SCRIPTS = os.path.join(REPO_ROOT, "scripts")
sys.path.insert(0, SCRIPTS)
import check_capabilities as cc  # noqa: E402


def kinds(source):
    return {(k, n) for (k, n) in cc.uses_of(source)}


class TestWhatIsDetected(unittest.TestCase):
    def test_a_process_is_found_however_it_is_written(self):
        for source in ("import subprocess\nsubprocess.run(['x'])", "from subprocess import run\nrun(['x'])", "import subprocess as sp\nsp.Popen(['x'])",
                       "from subprocess import check_output as co\nco(['x'])", "import os\nos.system('x')", "import asyncio\nasyncio.create_subprocess_exec('x')"):
            with self.subTest(source=source):
                self.assertTrue(any(k == "process" for k, _n in kinds(source)), source)

    def test_importing_subprocess_for_its_exception_class_is_not_a_power(self):
        self.assertEqual(kinds("import subprocess\ntry:\n    pass\nexcept subprocess.TimeoutExpired:\n    pass"), set())

    def test_deleting_is_found_for_os_shutil_and_path_objects(self):
        for source in ("import os\nos.remove('x')", "import shutil\nshutil.rmtree('x')", "from os import unlink as u\nu('x')", "from pathlib import Path\nPath('x').unlink()"):
            with self.subTest(source=source):
                self.assertTrue(any(k == "delete" for k, _n in kinds(source)), source)

    def test_network_use_is_found(self):
        for source in ("import socket", "import urllib.request", "from http import client\nimport http.client", "import asyncio\nasyncio.open_connection('h', 1)",
                       "import requests"):
            with self.subTest(source=source):
                self.assertTrue(any(k == "network" for k, _n in kinds(source)), source)

    def test_importing_by_name_is_found_but_reading_package_data_is_not(self):
        self.assertTrue(any(k == "dynamic_import" for k, _n in kinds("import importlib\nimportlib.import_module('x')")))
        self.assertTrue(any(k == "dynamic_import" for k, _n in kinds("__import__('x')")))
        self.assertEqual(kinds("import importlib.resources\nfrom importlib import resources\nfrom importlib import metadata"), set())

    def test_the_forbidden_things_are_found(self):
        for source in ("eval('1')", "exec('x')", "import pickle", "import marshal", "import ctypes", "import winreg", "from os import execv",
                       "import subprocess\nsubprocess.run('x', shell=True)", "import subprocess\nsubprocess.run('x', shell=flag)"):
            with self.subTest(source=source):
                self.assertTrue(any(k == "forbidden" for k, _n in kinds(source)), source)

    def test_things_that_only_look_alike_are_left_alone(self):
        for source in ("import re\nre.compile('x')", "import ast\nast.literal_eval('1')", "import subprocess\nsubprocess.run(['x'], shell=False)", "d = {}\nd.remove = 1"):
            with self.subTest(source=source):
                self.assertEqual({k for k, _n in kinds(source) if k == "forbidden"}, set(), source)


MANIFEST = {"process": {"a.py": "runs the compiler"}, "network": {}, "delete": {}, "dynamic_import": {}}


class TestTheCheck(unittest.TestCase):
    def test_a_listed_use_passes_and_an_unlisted_one_fails_naming_the_file(self):
        ok, _ = cc.check({"a.py": "import subprocess\nsubprocess.run(['x'])"}, MANIFEST, tree_mode=True)
        self.assertEqual(ok, [])
        problems, _ = cc.check({"a.py": "import subprocess\nsubprocess.run(['x'])", "b.py": "import os\nos.remove('x')"}, MANIFEST, tree_mode=True)
        self.assertEqual(len(problems), 1)
        self.assertIn("b.py:2", problems[0])
        self.assertIn("[delete]", problems[0])

    def test_a_listed_file_cannot_use_a_different_power(self):
        problems, _ = cc.check({"a.py": "import subprocess\nsubprocess.run(['x'])\nimport socket"}, MANIFEST, tree_mode=True)
        self.assertEqual(len(problems), 1)
        self.assertIn("[network]", problems[0])

    def test_a_forbidden_use_fails_even_when_the_file_is_listed(self):
        problems, _ = cc.check({"a.py": "import subprocess\nsubprocess.run('x', shell=True)"}, MANIFEST, tree_mode=True)
        self.assertTrue(any("never allowed" in p for p in problems))

    def test_an_entry_nobody_needs_any_more_fails_in_the_repository_but_not_in_a_zip(self):
        problems, _ = cc.check({"a.py": "x = 1"}, MANIFEST, tree_mode=True)
        self.assertTrue(any("no longer uses it" in p for p in problems))
        problems, _ = cc.check({"a.py": "x = 1"}, MANIFEST, tree_mode=False)
        self.assertEqual(problems, [])
        problems, _ = cc.check({}, MANIFEST, tree_mode=True)
        self.assertTrue(any("no such file" in p for p in problems))

    def test_a_file_that_cannot_be_parsed_is_reported(self):
        problems, _ = cc.check({"a.py": "def broken(:"}, MANIFEST, tree_mode=False)
        self.assertTrue(any("cannot be parsed" in p for p in problems))


class TestPaths(unittest.TestCase):
    def test_the_repository_and_development_names_become_the_names_in_the_zip(self):
        self.assertEqual(cc.normalize(r"Source\kotor_ap\KotorClient.py"), "KotorClient.py")
        self.assertEqual(cc.normalize("Source/scripts/client_files.py"), "scripts/client_files.py")
        self.assertEqual(cc.normalize(r"Archipelago\worlds\kotor\Items.py"), "worlds/kotor/Items.py")
        self.assertEqual(cc.normalize("Source/kotor_ap/worlds/kotor/Items.py"), "worlds/kotor/Items.py")

    def test_archipelagos_own_files_are_not_ours_to_list(self):
        for name in ("CommonClient.py", "worlds/AutoWorld.py", "rule_builder/options.py"):
            self.assertFalse(cc.is_ours(name), name)
        for name in ("KotorClient.py", "scripts/install_playerbundle.py", "worlds/kotor/__init__.py"):
            self.assertTrue(cc.is_ours(name), name)


class TestTheManifest(unittest.TestCase):
    def setUp(self):
        with open(cc.DEFAULT_MANIFEST, encoding="utf-8") as f:
            self.data = json.load(f)

    def test_it_lists_only_known_powers(self):
        self.assertEqual(set(self.data["allowed"]), set(cc.POWERS))

    def test_every_entry_has_a_real_reason(self):
        for power, files in self.data["allowed"].items():
            for path, reason in files.items():
                with self.subTest(power=power, path=path):
                    self.assertIsInstance(reason, str)
                    self.assertGreaterEqual(len(reason.split()), 5, "say what it does and why, in a sentence")
                    self.assertTrue(path.endswith(".py"))
                    self.assertEqual(cc.normalize(path), path, "paths are written as they are in the download")


if __name__ == "__main__":
    unittest.main()
