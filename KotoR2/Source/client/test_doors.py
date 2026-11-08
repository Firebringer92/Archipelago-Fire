"""Tests of the area randomizer's game side (k2_doors): stand-in module files without the game; the real doors and a real shuffle where the game is installed.
Run through tools/run_client_tests.py."""
import hashlib
import json
import os
import random
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
import k2_doors as D  # noqa: E402
import k2_modules as M  # noqa: E402
from test_shop import make_rim  # noqa: E402

GAME = os.environ.get("K2_GAME_DIR") or r"C:\Program Files (x86)\Steam\steamapps\common\Knights of the Old Republic II"
HAVE_GAME = os.path.isfile(os.path.join(GAME, "swkotor2.exe"))


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def make_git(doors, triggers):
    from pykotor.common.misc import ResRef
    from pykotor.resource.formats.gff import GFF, GFFContent, GFFList, bytes_gff
    gff = GFF(GFFContent.GIT)
    for name, rows in (("Door List", doors), ("TriggerList", triggers)):
        lst = GFFList()
        for template, module, waypoint in rows:
            s = lst.add(8)
            s.set_resref("TemplateResRef", ResRef(template))
            s.set_resref("LinkedToModule", ResRef(module))
            s.set_string("LinkedTo", waypoint)
        gff.root.set_list(name, lst)
    return bytes_gff(gff)


def make_utd(locked, key):
    from pykotor.resource.formats.gff import GFF, GFFContent, bytes_gff
    gff = GFF(GFFContent.UTD)
    gff.root.set_uint8("Locked", locked)
    gff.root.set_uint8("KeyRequired", key)
    return bytes_gff(gff)


def links_of(store, module):
    from pykotor.resource.formats.gff import read_gff
    git = next(d for (r, e), d in store.resources(module).items() if e == "git")
    root = read_gff(git).root
    out = {}
    for name in ("Door List", "TriggerList"):
        for i, s in enumerate(root.get_list(name)):
            if s.exists("LinkedToModule"):
                out[(name, i)] = (str(s.get_resref("LinkedToModule")), s.get_string("LinkedTo"))
    return out


class TestDoors(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.mods = os.path.join(self.dir, "modules")
        os.makedirs(self.mods)
        make_rim(os.path.join(self.mods, "aaa.rim"), {("aaa", "git"): make_git([("door_a", "bbb", "from_aaa"), ("door_b", "ccc", "from_aaa")], [("trig", "ccc", "from_aaa_t")])})
        make_rim(os.path.join(self.mods, "aaa_s.rim"), {("door_a", "utd"): make_utd(1, 1), ("door_b", "utd"): make_utd(0, 0)})
        self.store = M.ModuleStore(self.mods, os.path.join(self.dir, "state"))
        self.plan = {"links": [
            {"door": "aaa:Door List:0", "module": "aaa", "list": "Door List", "index": 0, "kind": "door", "to_module": "CCC", "to_waypoint": "from_new"},
            {"door": "aaa:TriggerList:0", "module": "aaa", "list": "TriggerList", "index": 0, "kind": "trigger", "to_module": "bbb", "to_waypoint": "from_other"}]}

    def test_links_are_rewritten_and_only_the_planned_ones(self):
        written, problems = D.door_files(self.store, self.plan)
        self.assertEqual((written, problems), (2, []))
        links = links_of(self.store, "aaa")
        self.assertEqual(links[("Door List", 0)], ("ccc", "from_new"))
        self.assertEqual(links[("Door List", 1)], ("ccc", "from_aaa"))                        # not in the plan: untouched
        self.assertEqual(links[("TriggerList", 0)], ("bbb", "from_other"))

    def test_a_relinked_door_is_unlocked_and_other_doors_are_not_touched(self):
        from pykotor.resource.formats.gff import read_gff
        D.door_files(self.store, self.plan)
        res = self.store.resources("aaa", "_s")
        a, b = read_gff(res[("door_a", "utd")]).root, read_gff(res[("door_b", "utd")]).root
        self.assertEqual((a.get_uint8("Locked"), a.get_uint8("KeyRequired")), (0, 0))
        self.assertEqual((b.get_uint8("Locked"), b.get_uint8("KeyRequired")), (0, 0))        # was already open

    def test_a_locked_door_that_is_not_relinked_stays_locked(self):
        from pykotor.resource.formats.gff import read_gff
        plan = {"links": [self.plan["links"][1]]}
        D.door_files(self.store, plan)
        a = read_gff(self.store.resources("aaa", "_s")[("door_a", "utd")]).root
        self.assertEqual((a.get_uint8("Locked"), a.get_uint8("KeyRequired")), (1, 1))

    def test_problems_are_reported_and_the_rest_goes_on(self):
        plan = {"links": self.plan["links"] + [
            {"door": "x", "module": "zzz", "list": "Door List", "index": 0, "kind": "door", "to_module": "aaa", "to_waypoint": "w"},
            {"door": "y", "module": "aaa", "list": "Door List", "index": 9, "kind": "door", "to_module": "aaa", "to_waypoint": "w"},
            {"door": "z", "module": "aaa", "list": "Nope", "index": 0, "kind": "door", "to_module": "aaa", "to_waypoint": "w"}]}
        written, problems = D.door_files(self.store, plan)
        self.assertEqual(written, 2)
        self.assertEqual(len(problems), 3)

    def test_restore_gives_everything_back(self):
        before = {f: sha(os.path.join(self.mods, f)) for f in os.listdir(self.mods)}
        D.door_files(self.store, self.plan)
        self.assertNotEqual(sha(os.path.join(self.mods, "aaa.rim")), before["aaa.rim"])
        self.assertEqual(self.store.restore_all()[1], [])
        self.assertEqual({f: sha(os.path.join(self.mods, f)) for f in os.listdir(self.mods)}, before)

    def test_an_empty_plan_changes_nothing(self):
        self.assertEqual(D.door_files(self.store, {}), (0, []))


@unittest.skipUnless(HAVE_GAME, "needs the game files")
class TestRealGame(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(ROOT, "data", "doors.json"), encoding="utf-8") as f:
            self.data = json.load(f)
        self.scratch = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.scratch, True)
        self.mods = os.path.join(self.scratch, "modules")
        os.makedirs(self.mods)
        for m in self.data["modules"]:
            for suffix in ("", "_s"):
                shutil.copy2(os.path.join(GAME, "modules", "%s%s.rim" % (m, suffix)), self.mods)
        self.store = M.ModuleStore(self.mods, os.path.join(self.scratch, "state"))

    def test_the_data_matches_the_game(self):
        """Every pair is a real coupled pair: each door's vanilla link leads to the other's module and arrives at the waypoint stored for the other."""
        doors = self.data["doors"]
        for a, b in self.data["pairs"]:
            for here, there in ((a, b), (b, a)):
                d, o = doors[here], doors[there]
                vanilla = links_of(self.store, d["module"])[(d["list"], d["index"])]
                self.assertEqual(vanilla[0].lower(), o["module"].lower(), here)
                self.assertEqual(vanilla[1], o["arrive"], here)

    def test_a_real_shuffle_applies_and_restores_exactly(self):
        from worlds.kotor2 import DoorShuffle as S
        before = {f: sha(os.path.join(self.mods, f)) for f in os.listdir(self.mods)}
        pairs = S.shuffle(self.data, random.Random(11))
        doors = self.data["doors"]
        links = []
        for a, b in pairs:
            for here, there in ((a, b), (b, a)):
                d = doors[here]
                links.append({"door": here, "module": d["module"], "list": d["list"], "index": d["index"], "kind": d["kind"],
                              "to_module": doors[there]["module"], "to_waypoint": doors[there]["arrive"]})
        written, problems = D.door_files(self.store, {"links": links})
        self.assertEqual(problems, [])
        self.assertEqual(written, len(doors))
        for l in links:
            self.assertEqual(links_of(self.store, l["module"])[(l["list"], l["index"])], (l["to_module"].lower(), l["to_waypoint"]), l["door"])
        self.assertEqual(self.store.restore_all()[1], [])
        self.assertEqual({f: sha(os.path.join(self.mods, f)) for f in os.listdir(self.mods)}, before)


if __name__ == "__main__":
    unittest.main()
