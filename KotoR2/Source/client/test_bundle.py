"""The player-bundle packager (tools/package_bundle.py): what it selects from the real project, and the whole pipeline on a small made-up project (so no
game, no built DLL and no Archipelago install is needed). Run through tools/run_client_tests.py."""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, "..", "tools")
sys.path.insert(0, TOOLS)
import package_bundle as P  # noqa: E402

REAL = P.ROOT
EXE = b"MZ-not-a-real-compiler"
MDLOPS_EXE = b"MZ-not-the-real-model-tool"
DLL = b"MZ-not-a-real-dll"


def sha(data):
    return hashlib.sha256(data).hexdigest()


class TestRealProject(unittest.TestCase):
    def test_client_files(self):
        names = P.client_files(REAL)
        self.assertIn("KotorTwoClient.py", names)
        self.assertIn("k2_status.py", names)
        self.assertIn("k2_gui.py", names)
        self.assertFalse([n for n in names if n.startswith("test_")])
        self.assertNotIn("fake_game.py", names)

    def test_tools_are_found_from_the_entry_point(self):
        tools = P.collect_tools(REAL)
        for needed in ("build_payload.py", "k2compile.py", "ncs_nops.py", "prepare_game_scripts.py", "build_droid_models.py"):       # the last one is imported inside a client function
            self.assertIn(needed, tools)
        for never in ("package_bundle.py", "package_world.py", "check_provenance.py", "check_capabilities.py", "stage_publish.py", "run_client_tests.py"):
            self.assertNotIn(never, tools)

    def test_scripts_leave_out_the_games_own_and_the_research(self):
        names = P.collect_scripts(REAL)
        self.assertIn("k2se_disp.nss", names)
        for left_out in ("nwscript_k2_vanilla.nss", "nwscript_k2se.nss", "k2se_classrb_data.nss", "a_bet3m4_research.nss", "k2se_poc_test.nss"):
            self.assertNotIn(left_out, names)

    def test_data_tables_named_by_the_code_are_found_and_none_stays_local(self):
        python = [os.path.join(REAL, "client", n) for n in P.client_files(REAL)] + [os.path.join(REAL, "tools", n) for n in P.collect_tools(REAL)]
        data = P.collect_data(REAL, python)
        self.assertIn("bazaar.json", data)
        self.assertIn("vendor.json", data)


class TestPipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = os.path.join(self.tmp, "project")
        self.files = {
            "client/KotorTwoClient.py": "import k2_one\n",
            "client/k2_one.py": "X = 1\n",
            "client/test_one.py": "import unittest\n",
            "client/fake_game.py": "Y = 2\n",
            "tools/build_payload.py": "import helper\nNAME = 'other.py'\n",
            "tools/helper.py": "DATA = 'table.json'\n",
            "tools/other.py": "Z = 3\n",
            "tools/unrelated.py": "W = 4\n",
            "tools/nwnsc/LICENSE.txt": "MIT licence text of the compiler\n",
            "tools/nwnsc/CREDITS.txt": "credits\n",
            "data/table.json": json.dumps({"a": 1}),
            "data/unused.json": json.dumps({"b": 2}),
            "nss/one.nss": "void main() {}\n",
            "nss/nwscript_k2se.nss": "// the game's own\n",
            "docs/README.md": "readme\n",
            "docs/SECURITY.md": "security\n",
            "docs/PROVENANCE.md": "provenance\n",
        }
        for rel, text in self.files.items():
            self.write(rel, text)
        self.write("tools/nwnsc/nwnsc.exe", EXE)
        for name in P.INSTALLER_ROOT_FILES + (P.INSTALLER_SCRIPT,):         # the installer's files (installer/ in the project)
            self.write("installer/" + name, ("rem " if name.endswith(".bat") else "# ") + name + "\n")
        for name in P.MDLOPS_FILES:                                      # a made-up MDLOps folder: the program, its source, licence, readme and tutorials
            self.write("tools/mdlops/" + name, MDLOPS_EXE if name == "mdlops.exe" else ("GPL licence text of the model tool\n" if name == "GPL.txt" else "file " + name + "\n"))
        self.dll = os.path.join(self.tmp, "version.dll")
        with open(self.dll, "wb") as f:
            f.write(DLL)
        with open(os.path.join(TOOLS, "provenance.json"), encoding="utf-8") as f:
            manifest = json.load(f)
        for b in manifest["binaries"]:
            if b.get("zip_path") == "tools/nwnsc/nwnsc.exe":
                b["sha256"] = sha(EXE)                                    # the made-up compiler stands in for the real one
            if b.get("zip_path") == "tools/mdlops/mdlops.exe":
                b["sha256"] = sha(MDLOPS_EXE)                             # and the made-up model tool for MDLOps
        self.manifest = manifest
        self.manifest_path = os.path.join(self.tmp, "provenance.json")
        self.save_manifest()
        self.out = os.path.join(self.tmp, "out", "bundle.zip")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, rel, content):
        path = os.path.join(self.root, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(content if isinstance(content, bytes) else content.encode("utf-8"))

    def save_manifest(self):
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(self.manifest, f)

    def build(self, **kw):
        kw.setdefault("run_smoke", False)
        return P.build(root=self.root, out=self.out, dll=self.dll, manifest_path=self.manifest_path, **kw)

    def names(self, path=None):
        with zipfile.ZipFile(path or self.out) as z:
            return z.namelist()

    def test_a_trial_build_has_what_the_code_needs_and_nothing_else(self):
        path, problems = self.build(dev=True)
        self.assertEqual(problems, [])
        names = self.names()
        self.assertEqual(sorted(n for n in names if n.startswith("client/")), ["client/KotorTwoClient.py", "client/k2_one.py"])
        self.assertEqual(sorted(n for n in names if n.startswith("tools/") and "nwnsc" not in n and "mdlops" not in n), ["tools/build_payload.py", "tools/helper.py", "tools/other.py"])
        self.assertEqual([n for n in names if n.startswith("data/")], ["data/table.json"])
        self.assertEqual([n for n in names if n.startswith("nss/")], ["nss/one.nss"])
        self.assertIn("extender/version.dll", names)
        self.assertIn("THIRD_PARTY_NOTICES.txt", names)
        self.assertIn("BUNDLE_MANIFEST.json", names)
        with zipfile.ZipFile(self.out) as z:
            manifest = json.loads(z.read("BUNDLE_MANIFEST.json"))
            self.assertTrue(manifest["dev"])
            self.assertEqual(manifest["version_dll_sha256"], sha(DLL))
            listed = {f["path"]: f["sha256"] for f in manifest["files"]}
            self.assertEqual(listed["extender/version.dll"], sha(DLL))
            self.assertEqual(sorted(listed), sorted(n for n in names if n != "BUNDLE_MANIFEST.json"))
            for name, digest in listed.items():
                self.assertEqual(sha(z.read(name)), digest, name)
            self.assertIn("Skywing", z.read("THIRD_PARTY_NOTICES.txt").decode())
            self.assertIn("Chuck Chargin", z.read("THIRD_PARTY_NOTICES.txt").decode())
            for name in P.INSTALLER_ROOT_FILES:
                self.assertIn(name, names)                                     # the batch files sit in the bundle's top folder
            self.assertIn("installer/install_bundle.py", names)
            self.assertEqual(sorted(n for n in names if n.startswith("tools/mdlops/")), sorted("tools/mdlops/" + m for m in P.MDLOPS_FILES))

    def test_a_release_build_needs_the_dll_to_be_recorded(self):
        path, problems = self.build()
        self.assertIsNone(path)
        self.assertFalse(os.path.exists(self.out))                         # nothing is left behind
        self.assertEqual(len(problems), 1)
        self.assertIn('"zip_path": "extender/version.dll"', problems[0])
        self.assertIn(sha(DLL), problems[0])
        self.manifest["binaries"].append(P.dll_entry(sha(DLL)))
        self.save_manifest()
        path, problems = self.build()
        self.assertEqual(problems, [])
        self.assertEqual(path, self.out)
        with zipfile.ZipFile(self.out) as z:
            self.assertFalse(json.loads(z.read("BUNDLE_MANIFEST.json"))["dev"])

    def test_a_changed_dll_is_refused_again(self):
        self.manifest["binaries"].append(P.dll_entry(sha(DLL)))
        self.save_manifest()
        with open(self.dll, "wb") as f:
            f.write(DLL + b"-rebuilt")
        path, problems = self.build()
        self.assertIsNone(path)
        self.assertIn(sha(DLL + b"-rebuilt"), problems[0])

    def test_the_same_inputs_give_the_same_bytes(self):
        def built():
            self.build(dev=True)
            with open(self.out, "rb") as f:
                return f.read()
        first = built()
        os.utime(os.path.join(self.root, "client", "k2_one.py"), (1, 1))         # a different file time must not matter
        self.assertEqual(built(), first)

    def test_a_table_that_stays_local_stops_the_build(self):
        self.write("data/k2se_addresses.csv", "a,b\n")
        self.write("tools/helper.py", "DATA = 'k2se_addresses.csv'\n")
        path, problems = self.build(dev=True)
        self.assertIsNone(path)
        self.assertIn("stay on the maintainer's machine", problems[0])

    def test_a_missing_compiler_or_dll_or_doc_is_a_plain_message(self):
        os.remove(os.path.join(self.root, "tools", "nwnsc", "nwnsc.exe"))
        path, problems = self.build(dev=True)
        self.assertIsNone(path)
        self.assertIn("tools/nwnsc/nwnsc.exe is missing", problems[0])
        self.write("tools/nwnsc/nwnsc.exe", EXE)
        os.remove(os.path.join(self.root, "docs", "SECURITY.md"))
        self.assertIn("docs/SECURITY.md is missing", self.build(dev=True)[1][0])
        self.write("docs/SECURITY.md", "security\n")
        os.remove(self.dll)
        self.assertIn("version.dll was not found", self.build(dev=True)[1][0])

    def test_a_path_of_the_maintainers_machine_is_refused(self):
        self.write("client/k2_one.py", 'PATH = r"C:\\Users\\Someone\\Documents\\game"\n')
        path, problems = self.build(dev=True)
        self.assertIsNone(path)
        self.assertTrue(any("path of the maintainer's machine" in p for p in problems), problems)

    def test_a_file_that_does_not_compile_is_refused(self):
        self.write("tools/other.py", "def broken(:\n")
        path, problems = self.build(dev=True)
        self.assertIsNone(path)
        self.assertTrue(any("does not compile" in p for p in problems), problems)

    def test_a_game_script_copy_is_refused(self):
        self.write("nss/nwscript.nss", "// a copy of the game's\n")           # not skipped by name: the provenance check on the zip must catch it
        path, problems = self.build(dev=True)
        self.assertIsNone(path)
        self.assertTrue(any("nwscript.nss" in p for p in problems), problems)

    def test_a_new_power_in_shipped_code_is_refused(self):
        self.write("client/k2_one.py", "import subprocess\nsubprocess.run(['x'])\n")
        path, problems = self.build(dev=True)
        self.assertIsNone(path)
        self.assertTrue(any(p.startswith("capabilities:") and "client/k2_one.py" in p for p in problems), problems)

    def test_the_smoke_test_catches_a_missing_module(self):
        core = os.path.join(self.tmp, "core")
        os.makedirs(core)
        open(os.path.join(core, "CommonClient.py"), "w").close()
        self.write("client/KotorTwoClient.py", "import k2_not_in_the_bundle\n")
        path, problems = self.build(dev=True, run_smoke=True, smoke_core=core)
        self.assertIsNone(path)
        self.assertTrue(any("smoke test" in p and "k2_not_in_the_bundle" in p for p in problems), problems)
        self.write("client/KotorTwoClient.py", "import k2_one\n")
        path, problems = self.build(dev=True, run_smoke=True, smoke_core=core)
        self.assertEqual(problems, [])
        self.assertEqual(path, self.out)

    def test_without_a_core_the_smoke_test_says_it_was_skipped(self):
        path, problems = self.build(dev=True, run_smoke=True)
        self.assertEqual(path, self.out)                                    # skipped, not failed
        self.assertTrue(problems[0].startswith("smoke test skipped"))


class TestCore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.core = os.path.join(self.tmp, "core")
        self.world = os.path.join(self.tmp, "world")
        for rel in P.CORE_FILES:
            self.put(self.core, rel, "x")
        for rel in P.CORE_TREES:
            self.put(self.core, rel + "/a.py", "x")
            self.put(self.core, rel + "/test/t.py", "x")
            self.put(self.core, rel + "/pic.png", "x")
        self.put(self.core, "requirements.txt", "colorama==0.4.6\nwebsockets==13.1  # ,<14\ncython==3.2.4\n# kivy==9\nkivymd>=2.0.1.dev0\nPymem==1.14.0\n")
        self.put(self.world, "Items.py", "x")
        self.put(self.world, "data/gates.json", "{}")
        self.put(self.world, "test/test_x.py", "x")
        self.put(self.world, "__pycache__/x.pyc", "x")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    @staticmethod
    def put(base, rel, text):
        path = os.path.join(base, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)

    def test_core_files_world_and_slim_requirements(self):
        files = P.collect_core(self.core, self.world)
        self.assertIn("core/CommonClient.py", files)
        self.assertIn("core/worlds/generic/a.py", files)
        self.assertIn("core/worlds/kotor2/Items.py", files)
        self.assertIn("core/worlds/kotor2/data/gates.json", files)
        for left_out in ("core/worlds/generic/test/t.py", "core/worlds/generic/pic.png", "core/worlds/kotor2/test/test_x.py", "core/worlds/kotor2/__pycache__/x.pyc"):
            self.assertNotIn(left_out, files)
        self.assertEqual(files["core/requirements.txt"].decode().splitlines(), ["colorama==0.4.6", "websockets==13.1  # ,<14", "kivymd>=2.0.1.dev0"])

    def test_a_core_that_lacks_a_file_is_a_plain_message(self):
        os.remove(os.path.join(self.core, "NetUtils.py"))
        with self.assertRaises(P.BundleError) as e:
            P.collect_core(self.core, self.world)
        self.assertIn("has no NetUtils.py", str(e.exception))


if __name__ == "__main__":
    unittest.main()
