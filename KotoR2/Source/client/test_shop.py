"""Tests of the shop randomizer's game side (k2_shop): stand-in module files without the game; the real stores and the empty script where the game is installed.
Run through tools/run_client_tests.py."""
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
import k2_modules as M  # noqa: E402
import k2_shop as S  # noqa: E402

GAME = os.environ.get("K2_GAME_DIR") or r"C:\Program Files (x86)\Steam\steamapps\common\Knights of the Old Republic II"
HAVE_GAME = os.path.isfile(os.path.join(GAME, "swkotor2.exe"))


def make_utm(tag="shop", items=("old_a", "old_b")):
    from pykotor.common.misc import ResRef
    from pykotor.resource.formats.gff import GFF, GFFContent, GFFList, bytes_gff
    gff = GFF(GFFContent.UTM)
    root = gff.root
    root.set_resref("ResRef", ResRef(tag))
    root.set_string("Tag", tag)
    root.set_uint8("BuySellFlag", 3)
    lst = GFFList()
    for n, resref in enumerate(items):
        e = lst.add(0)
        e.set_resref("InventoryRes", ResRef(resref))
        e.set_uint16("Repos_PosX", n)
        e.set_uint16("Repos_Posy", 0)
    root.set_list("ItemList", lst)
    return bytes_gff(gff)


def make_rim(path, resources):
    from pykotor.resource.formats.rim import RIM, write_rim
    from pykotor.resource.type import ResourceType
    rim = RIM()
    for (resref, ext), data in resources.items():
        rim.set_data(resref, ResourceType.from_extension(ext), data)
    write_rim(rim, path)


def stock_of(store, module, utm):
    from pykotor.resource.formats.gff import read_gff
    root = read_gff(store.resources(module, "_s")[(utm, "utm")]).root
    return [(str(e.get_resref("InventoryRes")), e.get_uint16("Repos_PosX"), e.get_uint16("Repos_Posy"), e.get_uint8("Infinite") if e.exists("Infinite") else 0)
            for e in root.get_list("ItemList")]


class TestStores(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.mods = os.path.join(self.dir, "modules")
        os.makedirs(self.mods)
        make_rim(os.path.join(self.mods, "aaa_s.rim"), {("shop1", "utm"): make_utm("shop1"), ("shop2", "utm"): make_utm("shop2")})
        self.store = M.ModuleStore(self.mods, os.path.join(self.dir, "state"))
        self.plan = {"stores": [{"module": "aaa", "utm": "shop1", "tag": "t1", "stock": ["x%02d" % n for n in range(23)]}],
                     "silence": ["a_stock_one", "a_stock_two"]}

    def test_the_stock_is_replaced_in_a_grid_and_is_infinite(self):
        files, problems = S.shop_files(self.store, self.plan)
        self.assertEqual(problems, [])
        stock = stock_of(self.store, "aaa", "shop1")
        self.assertEqual([s[0] for s in stock], ["x%02d" % n for n in range(23)])
        self.assertEqual([(s[1], s[2]) for s in stock][:12], [(n, 0) for n in range(10)] + [(0, 1), (1, 1)])
        self.assertTrue(all(s[3] == 1 for s in stock))
        self.assertEqual([s[0] for s in stock_of(self.store, "aaa", "shop2")], ["old_a", "old_b"])           # a store not in the plan keeps its stock

    def test_the_stock_scripts_are_replaced_by_the_empty_script(self):
        files, _ = S.shop_files(self.store, self.plan)
        self.assertEqual(files, {"a_stock_one.ncs": S.EMPTY_SCRIPT, "a_stock_two.ncs": S.EMPTY_SCRIPT})

    def test_restore_gives_the_original_stock_back(self):
        before = open(os.path.join(self.mods, "aaa_s.rim"), "rb").read()
        S.shop_files(self.store, self.plan)
        self.assertNotEqual(open(os.path.join(self.mods, "aaa_s.rim"), "rb").read(), before)
        self.assertEqual(self.store.restore_all()[1], [])
        self.assertEqual(open(os.path.join(self.mods, "aaa_s.rim"), "rb").read(), before)

    def test_a_missing_store_or_module_is_reported_and_the_rest_goes_on(self):
        plan = {"stores": [{"module": "nope", "utm": "shop1", "tag": "a", "stock": ["x"]}, {"module": "aaa", "utm": "missing", "tag": "b", "stock": ["x"]},
                           {"module": "aaa", "utm": "shop2", "tag": "c", "stock": ["y"]}], "silence": []}
        files, problems = S.shop_files(self.store, plan)
        self.assertEqual(len(problems), 2)
        self.assertEqual([s[0] for s in stock_of(self.store, "aaa", "shop2")], ["y"])

    def test_an_empty_plan_changes_nothing(self):
        self.assertEqual(S.shop_files(self.store, {}), ({}, []))


class TestShopData(unittest.TestCase):
    def test_every_stock_script_is_listed_and_the_dealers_are_left_alone(self):
        with open(os.path.join(ROOT, "data", "shops.json"), encoding="utf-8") as f:
            shops = json.load(f)
        self.assertEqual(len(shops["stores"]), 18)
        self.assertEqual(sorted(s["tag"] for s in shops["stores"] if s["leave_alone"]), ["DahniStore", "m_207_001", "patostore"])
        self.assertEqual(len(shops["stock_scripts"]), 16)
        self.assertTrue(all(len(n) <= 16 for n in shops["stock_scripts"]))
        with open(os.path.join(ROOT, "data", "shop_pool.json"), encoding="utf-8") as f:
            pool = json.load(f)
        self.assertGreater(len(pool["pool"]), 500)
        self.assertEqual(len(set(pool["pool"])), len(pool["pool"]))
        self.assertTrue(set(pool["staples"]).isdisjoint(pool["pool"]))


@unittest.skipUnless(HAVE_GAME, "needs the game files")
class TestRealGame(unittest.TestCase):
    def test_the_empty_script_is_what_the_compiler_makes(self):
        import k2compile
        work = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, work, True)
        k2compile.prepare_include_dir(work, GAME)
        with open(os.path.join(work, "stub.nss"), "w") as f:
            f.write("void main()\n{\n}\n")
        ok, message = k2compile.compile_script(work, "stub")
        self.assertTrue(ok, message)
        with open(os.path.join(work, "stub.ncs"), "rb") as f:
            self.assertEqual(f.read(), S.EMPTY_SCRIPT)

    def test_every_listed_store_exists_and_every_stock_script_is_in_the_game(self):
        with open(os.path.join(ROOT, "data", "shops.json"), encoding="utf-8") as f:
            shops = json.load(f)
        store = M.ModuleStore(os.path.join(GAME, "modules"), os.path.join(tempfile.mkdtemp(), "state"))
        for s in shops["stores"]:
            self.assertIn((s["utm"].lower(), "utm"), store.resources(s["module"], "_s"), s)
        found = set()
        for f in os.listdir(os.path.join(GAME, "modules")):
            if f.lower().endswith("_s.rim"):
                found |= {r for (r, e) in store.resources(f[:-6], "_s") if e == "ncs" and r.startswith("a_stock")}
        self.assertEqual(sorted(found), sorted(shops["stock_scripts"]))

    def test_the_whole_plan_applies_to_a_scratch_copy_and_restores_exactly(self):
        import hashlib
        with open(os.path.join(ROOT, "data", "shops.json"), encoding="utf-8") as f:
            shops = json.load(f)
        scratch = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, scratch, True)
        mods = os.path.join(scratch, "modules")
        os.makedirs(mods)
        for m in sorted({s["module"] for s in shops["stores"]}):
            shutil.copy2(os.path.join(GAME, "modules", m + "_s.rim"), mods)
        sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
        before = {f: sha(os.path.join(mods, f)) for f in os.listdir(mods)}
        store = M.ModuleStore(mods, os.path.join(scratch, "state"))
        plan = {"stores": [dict(module=s["module"], utm=s["utm"], tag=s["tag"], stock=["g_i_medeqpmnt01"] * 3) for s in shops["stores"] if not s["leave_alone"]],
                "silence": shops["stock_scripts"]}
        files, problems = S.shop_files(store, plan)
        self.assertEqual(problems, [])
        self.assertEqual(len(files), 16)
        for s in plan["stores"]:
            self.assertEqual(len(stock_of(store, s["module"], s["utm"])), 3)
        store.restore_all()
        self.assertEqual({f: sha(os.path.join(mods, f)) for f in os.listdir(mods)}, before)


if __name__ == "__main__":
    unittest.main()
