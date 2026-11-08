"""Tests of the loot randomizer's game side (k2_loot): stand-in module files without the game; a scratch copy of the real module files where the game is installed.
Run through tools/run_client_tests.py."""
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
import k2_loot as L  # noqa: E402
import k2_modules as M  # noqa: E402
from test_shop import make_rim  # noqa: E402

GAME = os.environ.get("K2_GAME_DIR") or r"C:\Program Files (x86)\Steam\steamapps\common\Knights of the Old Republic II"
HAVE_GAME = os.path.isfile(os.path.join(GAME, "swkotor2.exe"))
POOL = ["pool_%02d" % n for n in range(40)]


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def make_template(kind, entries):
    """entries: [(resref, dropable or None)]"""
    from pykotor.common.misc import ResRef
    from pykotor.resource.formats.gff import GFF, GFFContent, GFFList, bytes_gff
    gff = GFF(GFFContent.UTP if kind == "utp" else GFFContent.UTC)
    lst = GFFList()
    for n, (resref, dropable) in enumerate(entries):
        e = lst.add(0)
        e.set_resref("InventoryRes", ResRef(resref))
        e.set_uint16("Repos_PosX", n)
        e.set_uint16("Repos_Posy", 0)
        if dropable is not None:
            e.set_uint8("Dropable", dropable)
    gff.root.set_list("ItemList", lst)
    return bytes_gff(gff)


def read_list(store, module, resref, ext):
    from pykotor.resource.formats.gff import read_gff
    root = read_gff(store.resources(module, "_s")[(resref, ext)]).root
    return [(str(e.get_resref("InventoryRes")), e.get_uint8("Dropable") if e.exists("Dropable") else None) for e in root.get_list("ItemList")]


class TestLoot(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.mods = os.path.join(self.dir, "modules")
        os.makedirs(self.mods)
        for name in ("aaa", "start"):
            make_rim(os.path.join(self.mods, name + "_s.rim"), {
                ("chest", "utp"): make_template("utp", [("pool_01", None), ("quest_item", None), ("pool_02", None)]),
                ("empty", "utp"): make_template("utp", []),
                ("plain", "utp"): make_template("utp", [("quest_item", None)]),
                ("guard", "utc"): make_template("utc", [("pool_03", 1), ("pool_04", 0), ("quest_item", 1)]),
                ("pack", "utc"): make_template("utc", [("quest_item", 0)]),
            })
        make_rim(os.path.join(self.mods, "aaa.rim"), {("chest", "utp"): make_template("utp", [("pool_01", None)])})        # a main file: never touched
        self.store = M.ModuleStore(self.mods, os.path.join(self.dir, "state"))
        self.plan = {"mode": "replace", "pool": POOL, "seed": 123, "skip_modules": ["start"]}

    def test_replace_swaps_only_pool_items_in_containers(self):
        changed, problems = L.loot_files(self.store, self.plan)
        self.assertEqual(problems, [])
        chest = read_list(self.store, "aaa", "chest", "utp")
        self.assertEqual(len(chest), 3)
        self.assertIn(chest[0][0], POOL)
        self.assertEqual(chest[1][0], "quest_item")
        self.assertIn(chest[2][0], POOL)
        self.assertEqual(read_list(self.store, "aaa", "plain", "utp"), [("quest_item", None)])
        self.assertEqual(read_list(self.store, "aaa", "empty", "utp"), [])

    def test_a_creature_keeps_its_gear_but_drops_the_pick(self):
        L.loot_files(self.store, self.plan)
        guard = read_list(self.store, "aaa", "guard", "utc")
        self.assertEqual(guard[:3], [("pool_03", 0), ("pool_04", 0), ("quest_item", 1)])        # the droppable gear no longer drops; the quest item still does
        self.assertEqual(len(guard), 4)
        self.assertIn(guard[3][0], POOL)
        self.assertEqual(guard[3][1], 1)
        self.assertEqual(read_list(self.store, "aaa", "pack", "utc"), [("quest_item", 0)])

    def test_skipped_modules_and_main_files_are_untouched(self):
        before = {f: sha(os.path.join(self.mods, f)) for f in ("start_s.rim", "aaa.rim")}
        L.loot_files(self.store, self.plan)
        self.assertEqual(before, {f: sha(os.path.join(self.mods, f)) for f in before})

    def test_bonus_adds_one_pick_where_there_is_gear(self):
        L.loot_files(self.store, dict(self.plan, mode="bonus"))
        chest = read_list(self.store, "aaa", "chest", "utp")
        self.assertEqual([c[0] for c in chest[:3]], ["pool_01", "quest_item", "pool_02"])
        self.assertEqual(len(chest), 4)
        self.assertIn(chest[3][0], POOL)
        self.assertEqual(len(read_list(self.store, "aaa", "plain", "utp")), 1)                  # no gear: no bonus
        self.assertEqual(len(read_list(self.store, "aaa", "empty", "utp")), 0)
        self.assertEqual(len(read_list(self.store, "aaa", "guard", "utc")), 4)
        self.assertEqual(len(read_list(self.store, "aaa", "pack", "utc")), 2)                   # a creature that carries anything gets one

    def test_picks_are_the_same_for_the_same_seed_and_differ_between_seeds(self):
        def snapshot():
            return [read_list(self.store, "aaa", r, e) for r, e in (("chest", "utp"), ("guard", "utc"))]
        L.loot_files(self.store, self.plan)
        first = snapshot()
        self.store.restore_all()
        L.loot_files(self.store, self.plan)
        self.assertEqual(first, snapshot())
        self.store.restore_all()
        L.loot_files(self.store, dict(self.plan, seed=124))
        self.assertNotEqual(first, snapshot())

    def test_restore_gives_the_files_back(self):
        path = os.path.join(self.mods, "aaa_s.rim")
        before = sha(path)
        L.loot_files(self.store, self.plan)
        self.assertNotEqual(sha(path), before)
        self.assertEqual(self.store.restore_all()[1], [])
        self.assertEqual(sha(path), before)

    def test_an_empty_plan_changes_nothing(self):
        self.assertEqual(L.loot_files(self.store, {}), (0, []))


@unittest.skipUnless(HAVE_GAME, "needs the game files")
class TestRealGame(unittest.TestCase):
    def test_the_whole_game_applies_to_a_scratch_copy_and_restores_exactly(self):
        with open(os.path.join(ROOT, "data", "shop_pool.json"), encoding="utf-8") as f:
            pool = json.load(f)["pool"]
        scratch = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, scratch, True)
        mods = os.path.join(scratch, "modules")
        os.makedirs(mods)
        for f in os.listdir(os.path.join(GAME, "modules")):
            if f.lower().endswith("_s.rim"):
                shutil.copy2(os.path.join(GAME, "modules", f), mods)
        before = {f: sha(os.path.join(mods, f)) for f in os.listdir(mods)}
        store = M.ModuleStore(mods, os.path.join(scratch, "state"))
        for mode in ("replace", "bonus"):
            changed, problems = L.loot_files(store, {"mode": mode, "pool": pool, "seed": 7, "skip_modules": ["101PER"]})
            self.assertEqual(problems, [])
            self.assertGreater(changed, 50)
            self.assertEqual(sha(os.path.join(mods, "101PER_s.rim")), before["101PER_s.rim"])
            self.assertEqual(store.restore_all()[1], [])
            self.assertEqual({f: sha(os.path.join(mods, f)) for f in os.listdir(mods)}, before)


if __name__ == "__main__":
    unittest.main()
