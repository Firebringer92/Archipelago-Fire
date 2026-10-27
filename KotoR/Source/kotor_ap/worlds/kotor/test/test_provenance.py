"""
check_provenance.py is what stops a copy of the game's data from being published, so it has to be shown to fail on the things it exists to catch.
Each test builds a small folder or zip and runs the real checker with the real rules (scripts/provenance.json).
"""
import json
import os
import sys
import tempfile
import unittest
import zipfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
import check_provenance as cp  # noqa: E402


def write(root, rel, data=b"x"):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data if isinstance(data, bytes) else data.encode("utf-8"))


def problems_for_tree(files):
    with tempfile.TemporaryDirectory() as tmp:
        for rel, data in files.items():
            write(tmp, rel, data)
        return cp.check_tree(tmp, cp.Rules())[0]


def problems_for_zip(files):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "r.zip")
        with zipfile.ZipFile(path, "w") as z:
            for rel, data in files.items():
                z.writestr(rel, data)
        return cp.check_zip(path, cp.Rules())[0]


CLEAN = {
    "Docs/README.md": "# readme",
    "Source/scripts/tool.py": "print('hi')",
    "Source/extender/scripts_src/ap_thing.nss": "void main(){}",
    "Source/extender/raw_override_files/ap_item.uti": b"GFF",
    "Source/extender/raw_override_files/ap_dlg.dlg": b"GFF",
}


class TestRepositoryRules(unittest.TestCase):
    def test_a_clean_tree_passes(self):
        self.assertEqual(problems_for_tree(CLEAN), [])

    def test_game_data_files_fail(self):
        for name in ("N_DarthMalak.mdl", "N_DarthMalak.mdx", "w_lghtsbr_010.tga", "po_malak.tpc", "appearance.2da", "dialog.tlk", "swpc_tex_gui.erf", "global.jrl", "sounds.wav"):
            bad = dict(CLEAN, **{"Source/extender/raw_override_files/" + name: b"x"})
            found = problems_for_tree(bad)
            self.assertTrue(any(name in p for p in found), name)

    def test_a_file_no_rule_describes_fails(self):
        found = problems_for_tree(dict(CLEAN, **{"Source/extender/raw_override_files/mystery.bin": b"x"}))
        self.assertTrue(any("mystery.bin" in p and "no rule" in p for p in found))

    def test_a_template_not_named_ap_fails(self):
        for name in ("k_hen_dialog.dlg", "p_bastilla.utc", "g_i_medeqpmnt01.uti", "n_darkjedim.utp"):
            found = problems_for_tree(dict(CLEAN, **{"Source/extender/raw_override_files/" + name: b"GFF"}))
            self.assertTrue(any(name in p and "ap_" in p for p in found), name)

    def test_a_program_must_be_registered_with_its_hash(self):
        found = problems_for_tree(dict(CLEAN, **{"Source/extender/build_new/other.dll": b"MZ"}))
        self.assertTrue(any("other.dll" in p and "not listed" in p for p in found))
        found = problems_for_tree(dict(CLEAN, **{"Source/tools/nwnsc/nwnsc.exe": b"not the real compiler", "Source/tools/nwnsc/LICENSE.txt": "licence"}))
        self.assertTrue(any("nwnsc.exe" in p and "SHA-256" in p for p in found))

    def test_a_data_table_with_prose_fails(self):
        table = json.dumps({"Some Item": {"base": "Blaster_Pistol", "description": "A long passage copied from the game."}})
        found = problems_for_tree(dict(CLEAN, **{"Source/kotor_ap/worlds/kotor/gear_items.json": table}))
        self.assertTrue(any("description" in p for p in found))
        ok = json.dumps({"Some Item": {"base": "Blaster_Pistol", "cost": 5}})
        self.assertEqual(problems_for_tree(dict(CLEAN, **{"Source/kotor_ap/worlds/kotor/gear_items.json": ok})), [])


class TestReleaseZipRules(unittest.TestCase):
    NOTICES = "THIRD_PARTY_NOTICES.txt"

    def test_a_clean_zip_passes(self):
        self.assertEqual(problems_for_zip({self.NOTICES: "x", "scripts/tool.py": "x", "extender/scripts_src/ap_a.nss": "x"}), [])

    def test_game_files_in_a_zip_fail(self):
        for name in ("dist/Override/N_DarthMalak.mdl", "dist/Override/appearance.2da", "dist/Override/apo_0001.ncs", "extender/scripts_src/nwscript.nss",
                     "extender/scripts_src/k_inc_utility.nss", "dist/Override/p_bastilla.utc"):
            found = problems_for_zip({self.NOTICES: "x", name: b"x"})
            self.assertTrue(any(name in p for p in found), name)

    def test_the_two_own_apo_stubs_are_allowed(self):
        self.assertEqual(problems_for_zip({self.NOTICES: "x", "dist/Override/apo_0029.ncs": b"x", "dist/Override/apo_0034.ncs": b"x"}), [])

    def test_an_unregistered_program_in_a_zip_fails(self):
        found = problems_for_zip({self.NOTICES: "x", "tools/other/tool.exe": b"MZ"})
        self.assertTrue(any("tool.exe" in p for p in found))

    def test_a_game_file_inside_the_world_zip_fails(self):
        import io
        inner = io.BytesIO()
        with zipfile.ZipFile(inner, "w") as z:
            z.writestr("kotor/__init__.py", "x")
            z.writestr("kotor/portrait.tga", b"x")
        found = problems_for_zip({"kotor.apworld": inner.getvalue()})
        self.assertTrue(any("portrait.tga" in p for p in found))

    def test_the_model_tool_folder_is_exempt_from_the_extension_rule(self):
        self.assertEqual(problems_for_zip({self.NOTICES: "x", "tools/mdlops/readme.tga": b"x"}), [])


class TestReleaseComparisonAndHistory(unittest.TestCase):
    def test_history_paths_with_game_data_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "paths.txt")
            with open(path, "w") as f:
                f.write("\n".join(["KotoR/Source/scripts/tool.py", "KotoR/Source/extender/raw_override_files/N_DarthMalak.mdl",
                                   "KotoR/Source/extender/scripts_src/apo_0001.ncs"]))
            found, count = cp.check_paths(path, cp.Rules())
            self.assertEqual(count, 3)
            self.assertEqual(len(found), 2)
            with open(path, "w") as f:
                f.write("\n".join(["KotoR/Source/scripts/tool.py", "KotoR/Docs/README.md"]))
            self.assertEqual(cp.check_paths(path, cp.Rules())[0], [])

    def test_the_comparison_flags_only_files_that_are_not_plain_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            old, new = os.path.join(tmp, "old.zip"), os.path.join(tmp, "new.zip")
            with zipfile.ZipFile(old, "w") as z:
                z.writestr("scripts/a.py", "1")
            with zipfile.ZipFile(new, "w") as z:
                z.writestr("scripts/a.py", "2")
                z.writestr("scripts/b.py", "x")
                z.writestr("data/picture.png", "x")
            self.assertEqual(cp.compare_zips(old, new), 1)      # only the picture needs a human look


@unittest.skipUnless(os.path.isfile(os.path.join(REPO_ROOT, "extender", "scripts_src", "kse.nss")), "needs the full project folder")
class TestAgainstTheProject(unittest.TestCase):
    def test_every_registered_program_has_a_licence_entry(self):
        for entry in cp.Rules().manifest["binaries"]:
            self.assertTrue(entry.get("licence_file") or entry.get("licence_zip_path"), entry["path"])
            self.assertTrue(entry["origin"])


if __name__ == "__main__":
    unittest.main()
