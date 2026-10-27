"""
Nothing in the download may be a copy or an edit of the game's own files: build_game_assets.py makes those on the player's machine.
These tests keep it that way: the recipes are well formed, the dialog edit adds exactly one link, and the packaged zips hold no game-format files.
The tests that read a real KOTOR install are skipped when there is none.
"""
import glob
import json
import os
import sys
import tempfile
import unittest
import zipfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
SCRIPTS = os.path.join(REPO_ROOT, "scripts")
GAME_DIR = os.environ.get("KOTOR_GAME_DIR") or r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"      # the tests that read the game are skipped without an install
sys.path.insert(0, SCRIPTS)

# What may never appear in a release zip (outside tools/mdlops, which is the model tool itself): game-format models, textures, portraits,
# the journal and 2DA tables.
BANNED_EXTENSIONS = (".mdl", ".mdx", ".tga", ".tpc", ".txi", ".jrl", ".2da")
# Compiled stubs of our own that happen to carry the preserved-script prefix.
OWN_APO_FILES = {"apo_0029.ncs", "apo_0034.ncs"}


class TestRecipes(unittest.TestCase):
    def test_preserved_recipe_is_well_formed(self):
        with open(os.path.join(SCRIPTS, "preserved_originals.json"), encoding="utf-8") as f:
            recipe = json.load(f)
        self.assertGreater(len(recipe), 100)
        for target, step in recipe.items():
            self.assertTrue(target.startswith("apo_"), target)
            self.assertIn("resref", step)
            self.assertIn("from", step)
            for offset, value in step.get("patch", []):
                self.assertIsInstance(offset, int)
                self.assertTrue(0 <= value <= 255)

    def test_cutstart_fix_adds_one_unconditional_link(self):
        from pykotor.resource.formats.gff import GFF, GFFList, GFFStruct
        import dialog_fixes
        links = GFFList()
        for index, active in ((10, "k_tall"), (8, "k_medium"), (6, "k_small")):
            link = links.add(len(links))
            link.set_uint32("Index", index)
            link.set_resref("Active", active)
        dialog_fixes._add_unconditional(links, "k_medium")
        self.assertEqual(len(links), 4)
        self.assertEqual(links[3].get_uint32("Index"), 8)
        self.assertEqual(str(links[3].get_resref("Active")), "")
        with self.assertRaises(ValueError):       # a second one would be a different fix
            dialog_fixes._add_unconditional(links, "k_tall")
        with self.assertRaises(ValueError):
            dialog_fixes._add_unconditional(GFFList(), "k_tall")

    def test_saber_colors_use_the_names_the_world_expects(self):
        import saber_colors
        from worlds.kotor import Items  # noqa: F401 -- the gear table names the crystals
        gear = os.path.join(REPO_ROOT, "Archipelago", "worlds", "kotor", "gear_items.json")
        with open(gear, encoding="utf-8") as f:
            table = json.load(f)
        for label, spec in saber_colors.COLORS.items():
            self.assertIn(saber_colors.template_names(spec)["crystal"], table, label)

    def test_gear_table_carries_no_game_text(self):
        gear = os.path.join(REPO_ROOT, "Archipelago", "worlds", "kotor", "gear_items.json")
        with open(gear, encoding="utf-8") as f:
            table = json.load(f)
        self.assertFalse([k for k, v in table.items() if "description" in v], "item descriptions are the game's own text")


class TestPackagedZips(unittest.TestCase):
    def _zips(self):
        return glob.glob(os.path.join(REPO_ROOT, "dist", "KOTOR-AP-PlayerBundle-v0.2*.zip"))

    def test_bundle_has_no_game_format_files(self):
        zips = self._zips()
        if not zips:
            self.skipTest("no PlayerBundle zip built")
        for path in zips:
            with zipfile.ZipFile(path) as z:
                bad = [n for n in z.namelist() if n.lower().endswith(BANNED_EXTENSIONS) and not n.startswith("tools/mdlops/")]
                bad += [n for n in z.namelist() if os.path.basename(n).lower().startswith("apo_") and os.path.basename(n).lower() not in OWN_APO_FILES]
                bad += [n for n in z.namelist() if os.path.basename(n).lower() in ("nwscript.nss", "k_inc_utility.nss", "k_inc_debug.nss")]      # the game's own, written from the player's install
                self.assertEqual(bad, [], os.path.basename(path))

    def test_bundle_has_no_third_party_artwork_or_build_leftovers(self):
        zips = self._zips()
        if not zips:
            self.skipTest("no PlayerBundle zip built")
        for path in zips:
            with zipfile.ZipFile(path) as z:
                bad = [n for n in z.namelist() if os.path.basename(n).lower().startswith("discord")
                       or n.lower().endswith((".obj", ".pdb", ".ilk"))
                       or (n.startswith("worlds/generic/") and n.lower().endswith(".png"))]
                self.assertEqual(bad, [], os.path.basename(path))

    def test_notices_credit_mdlops_and_its_download_page(self):
        zips = self._zips()
        if not zips:
            self.skipTest("no PlayerBundle zip built")
        for path in zips:
            with zipfile.ZipFile(path) as z:
                text = z.read("THIRD_PARTY_NOTICES.txt").decode("utf-8")
                for need in ("Chuck Chargin Jr.", "ndix UR", "deadlystream.com/files/file/779-mdlops"):
                    self.assertIn(need, text)
                names = set(z.namelist())
                for need in ("tools/mdlops/KotOR_Tutorial.txt", "tools/mdlops/Quick_tutorial.txt", "tools/mdlops/replacer_tutorial.txt", "tools/mdlops/icon.bmp"):
                    self.assertIn(need, names)

    def test_bundle_carries_the_script_compiler_and_its_licence(self):
        zips = self._zips()
        if not zips:
            self.skipTest("no PlayerBundle zip built")
        for path in zips:
            with zipfile.ZipFile(path) as z:
                names = set(z.namelist())
                for need in ("tools/nwnsc/nwnsc.exe", "tools/nwnsc/LICENSE.txt", "tools/nwnsc/CREDITS.txt"):
                    self.assertIn(need, names)
                self.assertFalse([n for n in names if os.path.basename(n).lower() == "nwnnsscomp.exe"], "the old compiler is not redistributed")
                text = z.read("THIRD_PARTY_NOTICES.txt").decode("utf-8")
                for need in ("nwnsc", "Skywing", "Edward T. Smith", "Open Knights"):
                    self.assertIn(need, text)

    def test_bundle_carries_the_model_tool_and_its_licence(self):
        zips = self._zips()
        if not zips:
            self.skipTest("no PlayerBundle zip built")
        for path in zips:
            with zipfile.ZipFile(path) as z:
                names = set(z.namelist())
                for need in ("tools/mdlops/mdlops.exe", "tools/mdlops/GPL.txt", "scripts/build_game_assets.py", "scripts/preserved_originals.json"):
                    self.assertIn(need, names)


@unittest.skipUnless(os.path.isfile(os.path.join(SCRIPTS, "..", "tools", "nwnsc", "nwnsc.exe")), "needs tools/nwnsc")
class TestScriptCompiler(unittest.TestCase):
    def test_compiles_a_script_that_includes_the_extender_header(self):
        import nwnnsscomp_path
        src_dir = os.path.join(REPO_ROOT, "extender", "scripts_src")
        if not os.path.isfile(os.path.join(src_dir, "nwscript.nss")):
            self.skipTest("nwscript.nss has not been written from a KOTOR install yet")
        with tempfile.TemporaryDirectory() as tmp:
            nss, ncs = os.path.join(tmp, "t.nss"), os.path.join(tmp, "t.ncs")
            with open(nss, "w") as f:
                f.write('#include "kse"\nvoid main() { if (KSE_GetVersion() <= 0) return; KSE_Diag(1, "AP|PING|test"); }\n')
            result = nwnnsscomp_path.compile_nss(nss, ncs, cwd=src_dir, timeout=60)
            self.assertTrue(os.path.isfile(ncs), result.stdout + result.stderr)
            with open(ncs, "rb") as f:
                self.assertEqual(f.read(8), b"NCS V1.0")

    def test_a_script_with_an_error_leaves_no_output(self):
        import nwnnsscomp_path
        with tempfile.TemporaryDirectory() as tmp:
            nss, ncs = os.path.join(tmp, "bad.nss"), os.path.join(tmp, "bad.ncs")
            with open(nss, "w") as f:
                f.write("void main() { int x = ; }\n")
            nwnnsscomp_path.compile_nss(nss, ncs, cwd=tmp, timeout=60)
            self.assertFalse(os.path.isfile(ncs))


@unittest.skipUnless(os.path.isfile(os.path.join(GAME_DIR, "chitin.key")), "needs a KOTOR install")
class TestBuildFromRealGame(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import build_game_assets
        cls.module = build_game_assets
        cls.game = build_game_assets.GameData(GAME_DIR)

    def test_preserved_scripts_cover_the_recipe(self):
        files = self.module.preserved_scripts(self.game)
        with open(os.path.join(SCRIPTS, "preserved_originals.json"), encoding="utf-8") as f:
            self.assertEqual(len(files), len(json.load(f)))

    def test_dialog_fixes_change_one_link_each(self):
        try:
            import dlg_semantic_diff as d      # a development tool that is not part of the published repository
        except ImportError:
            self.skipTest("dlg_semantic_diff.py is not available")
        import dialog_fixes
        built = dialog_fixes.cutstart_dialogs(self.game)
        for resref, module in (("cut00_convers", "STUNT_00_s.rim"), ("tar02_carth022", "tar_m02af_s.rim"), ("m01aa_c01", "end_m01aa_s.rim")):
            vanilla = d.summarize(self.game.resource(module, resref, "dlg"))
            changed = d.summarize(built[f"{resref}.dlg"])
            diffs = [x for x in d.compare(vanilla, changed) if ".text" not in x]
            self.assertEqual(len(diffs), 1, (resref, diffs))

    def test_saber_models_are_the_games_violet_saber_with_a_new_texture(self):
        import saber_colors
        files = saber_colors.build(self.game)
        cyan = files["w_lghtsbr_010.mdl"]
        violet = self.game.resource("chitin", "w_lghtsbr_005", "mdl") or b""
        self.assertEqual(len(cyan), len(violet))
        self.assertIn(b"w_lsabrecyan01", cyan)
        self.assertNotIn(b"w_lsabrepurp01", cyan)

    def test_no_output_is_empty(self):
        for name, fn in self.module.CATEGORIES.items():
            files = fn(self.game)
            self.assertTrue(files, name)
            self.assertTrue(all(len(v) > 0 for v in files.values()), name)


if __name__ == "__main__":
    unittest.main()
