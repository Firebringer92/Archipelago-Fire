"""Tests of the Master gates' dialogue patch (k2_dialogues) and of the module store's handling of conversation archives (.erf): stand-in archives without the game;
the real three conversations where the game is installed. Run through tools/run_client_tests.py."""
import hashlib
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import k2_dialogues as D  # noqa: E402
import k2_modules as M  # noqa: E402

GAME = os.environ.get("K2_GAME_DIR") or r"C:\Program Files (x86)\Steam\steamapps\common\Knights of the Old Republic II"
HAVE_GAME = os.path.isfile(os.path.join(GAME, "swkotor2.exe"))


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def make_dlg(nodes):
    """nodes: [(list name, script, global string, parameter)]"""
    from pykotor.common.misc import ResRef
    from pykotor.resource.formats.gff import GFF, GFFContent, GFFList, bytes_gff
    gff = GFF(GFFContent.DLG)
    lists = {"EntryList": GFFList(), "ReplyList": GFFList()}
    for name, script, glob, param in nodes:
        s = lists[name].add(len(lists[name]))
        s.set_resref("Script", ResRef(script))
        s.set_string("ActionParamStrA", glob)
        s.set_int32("ActionParam1", param)
    for name, lst in lists.items():
        gff.root.set_list(name, lst)
    return bytes_gff(gff)


def make_erf(path, resources):
    from pykotor.resource.formats.erf import ERF, ERFType, write_erf
    from pykotor.resource.type import ResourceType
    erf = ERF(ERFType.ERF)
    for name, data in resources.items():
        erf.set_data(name, ResourceType.DLG, data)
    write_erf(erf, path, ResourceType.ERF)


def scripts(store, module, name):
    from pykotor.resource.formats.gff import read_gff
    root = read_gff(store.resources(module, "_dlg")[(name, "dlg")]).root
    return [(lst, str(n.get_resref("Script"))) for lst in ("EntryList", "ReplyList") for n in root.get_list(lst)]


class TestPatch(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.mods = os.path.join(self.dir, "modules")
        os.makedirs(self.mods)
        nodes = [("EntryList", "a_global_inc", "000_Jedi_Found", 1), ("EntryList", "a_global_inc", "Other_Global", 1), ("EntryList", "a_other", "", 0),
                 ("ReplyList", "a_global_inc", "000_Jedi_Found", 1)]
        for module, name in (("303NAR", "zezkaiel"), ("506OND", "kavar"), ("602DAN", "vrook")):
            make_erf(os.path.join(self.mods, module + "_dlg.erf"), {name: make_dlg(nodes), "another": make_dlg(nodes)})
        self.store = M.ModuleStore(self.mods, os.path.join(self.dir, "state"))

    def test_only_the_jedi_count_nodes_of_the_masters_conversations_change(self):
        count, problems = D.master_dialogue_files(self.store, {"NAR3", "DXN3", "DAN2"})
        self.assertEqual((count, problems), (6, []))
        self.assertEqual(scripts(self.store, "303NAR", "zezkaiel"), [("EntryList", "ap_jedi_inc"), ("EntryList", "a_global_inc"), ("EntryList", "a_other"),
                                                                    ("ReplyList", "ap_jedi_inc")])
        self.assertEqual([s for _, s in scripts(self.store, "303NAR", "another")], ["a_global_inc", "a_global_inc", "a_other", "a_global_inc"])      # others: untouched

    def test_only_active_gates_are_patched(self):
        count, _ = D.master_dialogue_files(self.store, {"DAN2"})
        self.assertEqual(count, 2)
        self.assertEqual(scripts(self.store, "303NAR", "zezkaiel")[0], ("EntryList", "a_global_inc"))
        self.assertEqual(scripts(self.store, "602DAN", "vrook")[0], ("EntryList", "ap_jedi_inc"))

    def test_restore_gives_the_archives_back_byte_for_byte(self):
        before = {f: sha(os.path.join(self.mods, f)) for f in os.listdir(self.mods)}
        D.master_dialogue_files(self.store, {"NAR3", "DXN3", "DAN2"})
        self.assertNotEqual(sha(os.path.join(self.mods, "303NAR_dlg.erf")), before["303NAR_dlg.erf"])
        self.assertEqual(self.store.restore_all()[1], [])
        self.assertEqual({f: sha(os.path.join(self.mods, f)) for f in os.listdir(self.mods)}, before)

    def test_a_missing_archive_or_conversation_is_reported(self):
        os.remove(os.path.join(self.mods, "506OND_dlg.erf"))
        make_erf(os.path.join(self.mods, "602DAN_dlg.erf"), {"someone": make_dlg([])})
        count, problems = D.master_dialogue_files(self.store, {"NAR3", "DXN3", "DAN2"})
        self.assertEqual(count, 2)
        self.assertEqual(len(problems), 2)

    def test_the_main_listing_ignores_conversation_archives(self):
        self.assertEqual(self.store.modules(""), [])
        self.assertEqual(self.store.modules("_dlg"), ["303NAR", "506OND", "602DAN"])


@unittest.skipUnless(HAVE_GAME, "needs the game files")
class TestRealGame(unittest.TestCase):
    def test_the_real_conversations_have_the_seven_nodes_and_restore_exactly(self):
        scratch = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, scratch, True)
        mods = os.path.join(scratch, "modules")
        os.makedirs(mods)
        backups = os.path.join(os.environ.get("LOCALAPPDATA", ""), "K2SE", "ap", "module_backups")
        for module in D.MASTERS:
            name = module + "_dlg.erf"
            saved = os.path.join(backups, name)          # a game this client has patched holds our edits: the original is the backup it made
            shutil.copy2(saved if os.path.isfile(saved) else os.path.join(GAME, "modules", name), mods)
        before = {f: sha(os.path.join(mods, f)) for f in os.listdir(mods)}
        store = M.ModuleStore(mods, os.path.join(scratch, "state"))
        count, problems = D.master_dialogue_files(store, {"NAR3", "DXN3", "DAN2"})
        self.assertEqual((count, problems), (7, []))
        for module, (conversation, _) in D.MASTERS.items():
            self.assertTrue(any(s == "ap_jedi_inc" for _, s in scripts(store, module, conversation)))
        self.assertEqual(store.restore_all()[1], [])
        self.assertEqual({f: sha(os.path.join(mods, f)) for f in os.listdir(mods)}, before)
        # a second patch after the restore gives the same bytes as the first
        D.master_dialogue_files(store, {"NAR3", "DXN3", "DAN2"})
        first = {f: sha(os.path.join(mods, f)) for f in os.listdir(mods)}
        store.restore_all()
        D.master_dialogue_files(store, {"NAR3", "DXN3", "DAN2"})
        self.assertEqual({f: sha(os.path.join(mods, f)) for f in os.listdir(mods)}, first)


if __name__ == "__main__":
    unittest.main()
