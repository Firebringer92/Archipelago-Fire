"""Tests of the module-file patching (k2_modules) and the Bazaar token placement (k2_bazaar_tokens). They build small stand-in module files, so they run without the game;
one extra test runs on a scratch copy of real module files where the game is installed. Run through tools/run_client_tests.py."""
import hashlib
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import k2_modules as M  # noqa: E402
import k2_bazaar_tokens as TK  # noqa: E402

GAME = os.environ.get("K2_GAME_DIR") or r"C:\Program Files (x86)\Steam\steamapps\common\Knights of the Old Republic II"
HAVE_GAME = os.path.isfile(os.path.join(GAME, "swkotor2.exe"))


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def make_utp(container=True, plot=False, script="k_plc_treasure"):
    from pykotor.common.misc import ResRef
    from pykotor.resource.formats.gff import GFF, GFFContent, GFFList, bytes_gff
    gff = GFF(GFFContent.UTP)
    root = gff.root
    root.set_uint8("HasInventory", 1 if container else 0)
    root.set_uint8("Plot", 1 if plot else 0)
    root.set_uint8("Static", 0)
    root.set_uint8("Useable", 1)
    root.set_resref("OnOpen", ResRef(script))
    root.set_list("ItemList", GFFList())
    return bytes_gff(gff)


def make_module(path, templates, instances):
    """A module file holding the given UTP templates {resref: bytes} and a GIT whose placeables use the given template resrefs."""
    from pykotor.common.misc import ResRef
    from pykotor.resource.formats.gff import GFF, GFFContent, GFFList, bytes_gff
    from pykotor.resource.formats.rim import RIM, write_rim
    from pykotor.resource.type import ResourceType
    git = GFF(GFFContent.GIT)
    placeables = GFFList()
    for resref in instances:
        placeables.add(9).set_resref("TemplateResRef", ResRef(resref))
    git.root.set_list("Placeable List", placeables)
    rim = RIM()
    rim.set_data("mod", ResourceType.GIT, bytes_gff(git))
    for resref, data in templates.items():
        rim.set_data(resref, ResourceType.UTP, data)
    write_rim(rim, path)


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.mods = os.path.join(self.dir, "modules")
        self.state = os.path.join(self.dir, "state")
        os.makedirs(self.mods)
        self.store = M.ModuleStore(self.mods, self.state)

    def module(self, name, containers=12):
        templates = {"chest%d" % i: make_utp() for i in range(containers)}
        templates.update({"locked": make_utp(plot=True), "box": make_utp(script="my_own_script"), "crate": make_utp(container=False)})
        instances = ["chest%d" % i for i in range(containers)] + ["locked", "box", "crate"]
        make_module(os.path.join(self.mods, name + ".rim"), templates, instances)


def set_flag(root):
    root.set_uint8("X", 1)
    return True


class TestStore(Base):
    def test_edit_backs_up_once_and_restore_puts_the_original_back(self):
        self.module("aaa")
        path = self.store.path("aaa")
        original = sha(path)
        self.assertTrue(self.store.edit_gff("aaa", None, "git", set_flag))
        patched = sha(path)
        self.assertTrue(self.store.edit_gff("aaa", None, "git", lambda root: root.set_uint8("Y", 2) or True))      # a second edit must not replace the backup with the patched file
        self.assertNotEqual(sha(path), original)
        self.assertNotEqual(sha(path), patched)
        restored, skipped = self.store.restore_all()
        self.assertEqual((restored, skipped), (["aaa.rim"], []))
        self.assertEqual(sha(path), original)
        self.assertFalse(os.path.exists(os.path.join(self.state, "module_backups", "aaa.rim")))

    def test_no_change_means_no_write_and_no_backup(self):
        self.module("aaa")
        before = sha(self.store.path("aaa"))
        self.assertFalse(self.store.edit_gff("aaa", None, "git", lambda root: False))
        self.assertEqual(sha(self.store.path("aaa")), before)
        self.assertEqual(self.store.restore_all(), ([], []))

    def test_a_file_changed_by_something_else_is_left_alone(self):
        self.module("aaa")
        self.store.edit_gff("aaa", None, "git", set_flag)
        self.module("aaa", containers=2)                                                    # a game update replaces the file
        updated = sha(self.store.path("aaa"))
        restored, skipped = self.store.restore_all()
        self.assertEqual((restored, skipped), ([], ["aaa.rim"]))
        self.assertEqual(sha(self.store.path("aaa")), updated)
        self.assertFalse(os.path.exists(os.path.join(self.state, "module_backups", "aaa.rim")))      # the stale backup is dropped, it must not come back later

    def test_the_manifest_survives_a_new_store(self):
        self.module("aaa")
        original = sha(self.store.path("aaa"))
        self.store.edit_gff("aaa", None, "git", set_flag)
        again = M.ModuleStore(self.mods, self.state)
        self.assertEqual(again.restore_all()[0], ["aaa.rim"])
        self.assertEqual(sha(self.store.path("aaa")), original)

    def test_a_missing_resource_is_not_an_error(self):
        self.module("aaa")
        self.assertFalse(self.store.edit_gff("aaa", "nothing", "utp", lambda root: True))


class TestTokens(Base):
    def setUp(self):
        super().setUp()
        self.names = ["m%02d" % i for i in range(1, 13)]
        for name in self.names:
            self.module(name)
        old = TK.ELIGIBLE_MODULES
        TK.ELIGIBLE_MODULES = self.names
        self.addCleanup(setattr, TK, "ELIGIBLE_MODULES", old)

    def test_only_ordinary_containers_qualify(self):
        cands = TK.find_candidates(self.dir, self.store, self.names)
        self.assertEqual(len(cands["m01"]), 12)                                              # not the plot one, the one with its own script, nor the non-container
        self.assertTrue(all(resref.startswith("chest") for _, resref, _ in cands["m01"]))

    def test_the_plan_is_capped_deterministic_and_seeded(self):
        cands = TK.find_candidates(self.dir, self.store, self.names)
        a = TK.plan_tokens(cands, "seed one")
        self.assertEqual(len(a), 100)
        self.assertTrue(all(sum(1 for c in a if c["module"] == m) <= 10 for m in self.names))

        def key(plan):
            return [(c["module"], c["index"], c["clone"]) for c in plan]
        self.assertEqual(key(a), key(TK.plan_tokens(cands, "seed one")))
        self.assertNotEqual(key(a), key(TK.plan_tokens(cands, "seed two")))
        self.assertEqual(sorted(c["clone"] for c in a), ["apbz%03d" % n for n in range(1, 101)])
        self.assertTrue(all(len(c["clone"]) <= 16 for c in a))

    def test_fewer_containers_than_tokens_is_reported(self):
        for name in self.names[3:]:
            os.remove(os.path.join(self.mods, name + ".rim"))
        files, problems = TK.token_files(self.dir, self.store, "s")
        self.assertEqual(len(files), 30)
        self.assertEqual(len(problems), 1)
        self.assertIn("30 of the 100", problems[0])

    def test_clones_hold_one_token_and_the_instances_point_at_them(self):
        from pykotor.resource.formats.gff import read_gff
        files, problems = TK.token_files(self.dir, self.store, "seed one")
        self.assertEqual(problems, [])
        self.assertEqual(len(files), 100)
        clone = read_gff(next(iter(files.values()))).root
        self.assertEqual([str(i.get_resref("InventoryRes")) for i in clone.get_list("ItemList")], ["ap_bz_token"])
        used = 0
        for name in self.names:
            git = next(d for (r, e), d in self.store.resources(name).items() if e == "git")
            used += sum(1 for p in read_gff(git).root.get_list("Placeable List") if str(p.get_resref("TemplateResRef")).startswith("apbz"))
        self.assertEqual(used, 100)

    def test_restoring_gives_back_every_original_and_a_second_run_matches(self):
        before = {n: sha(self.store.path(n)) for n in self.names}
        first, _ = TK.token_files(self.dir, self.store, "seed one")
        self.assertEqual(self.store.restore_all()[1], [])
        self.assertEqual({n: sha(self.store.path(n)) for n in self.names}, before)
        second, _ = TK.token_files(self.dir, self.store, "seed one")
        self.assertEqual(first, second)

    def test_the_same_seed_gives_identical_module_files(self):
        TK.token_files(self.dir, self.store, "seed one")
        one = {n: sha(self.store.path(n)) for n in self.names}
        self.store.restore_all()
        TK.token_files(self.dir, self.store, "seed one")
        self.assertEqual({n: sha(self.store.path(n)) for n in self.names}, one)


@unittest.skipUnless(HAVE_GAME, "needs the game files")
class TestRealModules(Base):
    def test_a_real_module_is_patched_and_restored_exactly(self):
        for suffix in ("", "_s"):
            src = os.path.join(GAME, "modules", "202TEL%s.rim" % suffix)
            if os.path.exists(src):
                shutil.copy2(src, self.mods)
        before = {f: sha(os.path.join(self.mods, f)) for f in os.listdir(self.mods)}
        old = TK.ELIGIBLE_MODULES
        TK.ELIGIBLE_MODULES = ["202TEL"]
        try:
            files, _ = TK.token_files(GAME, self.store, "real")
        finally:
            TK.ELIGIBLE_MODULES = old
        self.assertTrue(0 < len(files) <= 10)
        self.assertNotEqual(sha(os.path.join(self.mods, "202TEL.rim")), before["202TEL.rim"])
        self.store.restore_all()
        self.assertEqual({f: sha(os.path.join(self.mods, f)) for f in os.listdir(self.mods)}, before)


if __name__ == "__main__":
    unittest.main()
