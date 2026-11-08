"""Tests of the enemy randomizer's game side (k2_enemies): stand-in module files without the game; the real pool and module files where the game is installed.
Run through tools/run_client_tests.py."""
import hashlib
import json
import math
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import k2_enemies as E  # noqa: E402
import k2_modules as M  # noqa: E402
from test_shop import make_rim  # noqa: E402

GAME = os.environ.get("K2_GAME_DIR") or r"C:\Program Files (x86)\Steam\steamapps\common\Knights of the Old Republic II"
HAVE_GAME = os.path.isfile(os.path.join(GAME, "swkotor2.exe"))


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def make_git(existing):
    from pykotor.common.misc import ResRef
    from pykotor.resource.formats.gff import GFF, GFFContent, GFFList, bytes_gff
    gff = GFF(GFFContent.GIT)
    lst = GFFList()
    for resref in existing:
        s = lst.add(4)
        s.set_single("XPosition", 1.0)
        s.set_single("YPosition", 2.0)
        s.set_single("ZPosition", 3.0)
        s.set_single("XOrientation", 0.0)
        s.set_single("YOrientation", 1.0)
        s.set_resref("TemplateResRef", ResRef(resref))
    gff.root.set_list("Creature List", lst)
    return bytes_gff(gff)


def make_utc(tag):
    from pykotor.common.misc import ResRef
    from pykotor.resource.formats.gff import GFF, GFFContent, bytes_gff
    gff = GFF(GFFContent.UTC)
    gff.root.set_string("Tag", tag)
    gff.root.set_resref("TemplateResRef", ResRef(tag))
    gff.root.set_uint8("Plot", 0)
    return bytes_gff(gff)


def creatures(store, module):
    from pykotor.resource.formats.gff import read_gff
    git = next(d for (r, e), d in store.resources(module).items() if e == "git")
    return [(str(s.get_resref("TemplateResRef")), s.acquire("XPosition", 0.0), s.acquire("YPosition", 0.0), s.acquire("ZPosition", 0.0),
             s.acquire("XOrientation", 0.0), s.acquire("YOrientation", 0.0)) for s in read_gff(git).root.get_list("Creature List")]


class TestEnemies(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.mods = os.path.join(self.dir, "modules")
        os.makedirs(self.mods)
        make_rim(os.path.join(self.mods, "aaa.rim"), {("aaa", "git"): make_git(["old_one"])})
        make_rim(os.path.join(self.mods, "aaa_s.rim"), {("beast_a", "utc"): make_utc("beast_a"), ("beast_b", "utc"): make_utc("beast_b")})
        make_rim(os.path.join(self.mods, "bbb.rim"), {("bbb", "git"): make_git([])})
        self.store = M.ModuleStore(self.mods, os.path.join(self.dir, "state"))
        self.plan = {"spawns": [
            {"module": "aaa", "x": 10.0, "y": 20.0, "z": 1.5, "angle": 0.0, "template": "beast_a", "source": "aaa"},
            {"module": "aaa", "x": 11.0, "y": 21.0, "z": 1.5, "angle": math.pi / 2, "template": "beast_b", "source": "aaa"},
            {"module": "bbb", "x": 5.0, "y": 6.0, "z": 0.5, "angle": 1.0, "template": "beast_a", "source": "aaa"}]}

    def test_creatures_are_added_and_copies_have_their_own_name_and_tag(self):
        from pykotor.resource.formats.gff import read_gff
        files, added, problems = E.enemy_files(self.dir, self.store, self.plan)
        self.assertEqual((added, problems), (3, []))
        self.assertEqual(sorted(files), ["apen001.utc", "apen002.utc", "apen003.utc"])
        root = read_gff(files["apen001.utc"]).root
        self.assertEqual((root.get_string("Tag"), str(root.get_resref("TemplateResRef"))), ("apen001", "apen001"))
        aaa = creatures(self.store, "aaa")
        self.assertEqual(aaa[0][0], "old_one")                                              # what was there stays, untouched
        self.assertEqual([c[0] for c in aaa[1:]], ["apen001", "apen002"])
        self.assertAlmostEqual(aaa[1][1], 10.0)
        self.assertAlmostEqual(aaa[2][5], 1.0)                                              # angle pi/2: facing +y
        self.assertAlmostEqual(math.hypot(aaa[2][4], aaa[2][5]), 1.0)
        self.assertEqual([c[0] for c in creatures(self.store, "bbb")], ["apen003"])

    def test_missing_templates_and_modules_are_reported_and_skipped(self):
        plan = {"spawns": self.plan["spawns"] + [{"module": "aaa", "x": 0, "y": 0, "z": 0, "angle": 0, "template": "nope", "source": "aaa"},
                                                  {"module": "zzz", "x": 0, "y": 0, "z": 0, "angle": 0, "template": "beast_a", "source": "aaa"}]}
        files, added, problems = E.enemy_files(self.dir, self.store, plan)
        self.assertEqual(added, 3)
        self.assertEqual(len(files), 3)
        self.assertEqual(len(problems), 2)

    def test_restore_gives_the_modules_back(self):
        before = {f: sha(os.path.join(self.mods, f)) for f in os.listdir(self.mods)}
        E.enemy_files(self.dir, self.store, self.plan)
        self.assertNotEqual(sha(os.path.join(self.mods, "aaa.rim")), before["aaa.rim"])
        self.assertEqual(self.store.restore_all()[1], [])
        self.assertEqual({f: sha(os.path.join(self.mods, f)) for f in os.listdir(self.mods)}, before)

    def test_the_names_do_not_depend_on_the_order_of_the_plan(self):
        first, _, _ = E.enemy_files(self.dir, self.store, self.plan)
        self.store.restore_all()
        reverse = {"spawns": list(reversed(self.plan["spawns"]))}
        second, _, _ = E.enemy_files(self.dir, self.store, reverse)
        self.assertEqual(first, second)

    def test_an_empty_plan_changes_nothing(self):
        self.assertEqual(E.enemy_files(self.dir, self.store, {}), ({}, 0, []))


@unittest.skipUnless(HAVE_GAME, "needs the game files")
class TestRealGame(unittest.TestCase):
    def test_every_pool_template_can_be_read_and_the_whole_plan_applies_and_restores(self):
        import random
        with open(os.path.join(ROOT, "data", "enemies.json"), encoding="utf-8") as f:
            data = json.load(f)
        scratch = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, scratch, True)
        mods = os.path.join(scratch, "modules")
        os.makedirs(mods)
        for m in data["modules"]:
            for suffix in ("", "_s"):
                shutil.copy2(os.path.join(GAME, "modules", "%s%s.rim" % (m, suffix)), mods)
        for info in data["pool"].values():
            if info["source"] != "global":
                for suffix in ("", "_s"):
                    target = os.path.join(mods, "%s%s.rim" % (info["source"], suffix))
                    if not os.path.exists(target):
                        shutil.copy2(os.path.join(GAME, "modules", "%s%s.rim" % (info["source"], suffix)), mods)
        before = {f: sha(os.path.join(mods, f)) for f in os.listdir(mods)}
        store = M.ModuleStore(mods, os.path.join(scratch, "state"))
        rng = random.Random(5)
        spawns = []
        for module, info in data["modules"].items():
            for x, y, z in info["points"]:
                template = rng.choice(sorted(data["pool"]))
                spawns.append({"module": module, "x": x, "y": y, "z": z, "angle": 1.0, "template": template, "source": data["pool"][template]["source"]})
        spawns += [{"module": "101PER", "x": 0, "y": 0, "z": 0, "angle": 0, "template": t, "source": i["source"]} for t, i in sorted(data["pool"].items())]
        files, added, problems = E.enemy_files(GAME, store, {"spawns": spawns})
        self.assertEqual(problems, [])                                                      # all 91 pool templates were found at their stated source
        self.assertEqual(added, len(spawns))
        self.assertEqual(len(files), len(spawns))
        self.assertTrue(all(len(n) <= 20 for n in files))
        self.assertEqual(store.restore_all()[1], [])
        self.assertEqual({f: sha(os.path.join(mods, f)) for f in os.listdir(mods)}, before)


if __name__ == "__main__":
    unittest.main()
