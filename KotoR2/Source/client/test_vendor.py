"""Tests of the Archipelago Vendor's data, scripts and builders (k2_vendor, tools/build_vendor.py). The part that reads the game's files runs only where the game is
installed. Run through tools/run_client_tests.py."""
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import k2_vendor as V  # noqa: E402
import build_vendor as BV  # noqa: E402

GAME = os.environ.get("K2_GAME_DIR") or r"C:\Program Files (x86)\Steam\steamapps\common\Knights of the Old Republic II"
HAVE_GAME = os.path.isfile(os.path.join(GAME, "swkotor2.exe"))
CFG = V.config()


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class TestScripts(unittest.TestCase):
    def test_five_generic_scripts_with_short_names(self):
        sources = BV.script_sources(CFG)
        self.assertEqual(sorted(sources), ["ap_vd_do", "ap_vd_greet", "ap_vd_menu", "ap_vd_no", "ap_vd_ok"])
        self.assertTrue(all(len(n) <= 16 for n in sources))

    def test_prices_and_limits_come_from_the_data(self):
        text = BV.script_sources(CFG)["ap_vd_do"]
        self.assertIn("return %d;" % CFG["skill_price"], text)
        self.assertIn("return %d;" % CFG["ability_price"], text)
        self.assertIn(">= %d) return FALSE;" % CFG["skill_limit"], text)
        for n, (amount, price) in enumerate(CFG["bundles"]):
            self.assertIn("nItem == %d) return %d;" % (n, price), text)
            self.assertIn("nItem == %d) return %d;" % (n, amount), text)
        self.assertIn("AdjustAlignment(oPC, ALIGNMENT_DARK_SIDE, %d);" % CFG["alignment_step"], text)

    def test_the_skill_and_ability_lists_match_the_game_script_indices(self):
        self.assertEqual(CFG["skills"], ["Computer Use", "Demolitions", "Stealth", "Awareness", "Persuade", "Repair", "Security", "Treat Injury"])
        self.assertEqual(CFG["abilities"], ["Strength", "Dexterity", "Constitution", "Intelligence", "Wisdom", "Charisma"])

    def test_the_spawn_include_uses_the_same_waypoint_and_tag_as_the_data(self):
        text = read("nss/k2ap_vendor.nss")
        self.assertIn('"%s"' % CFG["hawk_module"].lower(), text)
        self.assertIn('"%s"' % CFG["hawk_spot"], text)
        self.assertIn('"apvendor"', text)
        self.assertIn("vAt.x + %s" % CFG["offset"], text)

    def test_the_locker_guard_keeps_the_passes_and_receipts(self):
        text = read("nss/k2ap_gate.nss")
        for tag in ("ap_vp_skill", "ap_vp_abil", "ap_vp_align", "ap_vp_supply", "ap_vd_skill", "ap_vd_abil"):
            self.assertIn('"%s"' % tag, text)

    def test_the_dispatcher_has_the_pass_action(self):
        self.assertIn('sAction == "pass"', read("nss/k2se_disp.nss"))
        self.assertIn('"ap_vp_" + sArgs', read("nss/k2se_disp.nss"))


class TestBuilt(unittest.TestCase):
    def test_items(self):
        from pykotor.resource.generics.uti import read_uti
        files = V.build_items()
        self.assertEqual(sorted(files), ["ap_vd_abil.uti", "ap_vd_skill.uti", "ap_vp_abil.uti", "ap_vp_align.uti", "ap_vp_skill.uti", "ap_vp_supply.uti"])
        for name, data in files.items():
            uti = read_uti(data)
            self.assertEqual((uti.tag + ".uti", bool(uti.plot), len(uti.properties)), (name, True, 0))

    def test_the_conversation_reads_back_with_its_parameters(self):
        from pykotor.resource.generics.dlg import read_dlg
        dlg = read_dlg(V.build_dlg(CFG))
        greet = dlg.starters[0].node
        self.assertEqual(str(dlg.starters[0].active1), "ap_vd_greet")
        menus = [(str(l.active1), l.active1_param1) for l in greet.links if str(l.active1) == "ap_vd_menu"]
        self.assertEqual(menus, [("ap_vd_menu", 0), ("ap_vd_menu", 1), ("ap_vd_menu", 2), ("ap_vd_menu", 3)])
        seen = set()

        def walk(node, depth=0):
            if id(node) in seen or depth > 40:
                return
            seen.add(id(node))
            for l in node.links:
                walk(l.node, depth + 1)
        walk(greet)
        dos = sorted({(n.script1_param1, n.script1_param2) for n in _entries(seen_nodes(greet)) if str(n.script1) == "ap_vd_do"})
        expected = sorted([(0, i) for i in range(8)] + [(1, i) for i in range(6)] + [(2, 0), (2, 1)] + [(3, i) for i in range(3)] + [(4, i) for i in range(3)])
        self.assertEqual(dos, expected)


def seen_nodes(root):
    out, stack, ids = [], [root], set()
    while stack:
        n = stack.pop()
        if id(n) in ids:
            continue
        ids.add(id(n))
        out.append(n)
        stack.extend(l.node for l in n.links)
    return out


def _entries(nodes):
    from pykotor.resource.generics.dlg import DLGEntry
    return [n for n in nodes if isinstance(n, DLGEntry)]


@unittest.skipUnless(HAVE_GAME, "needs the game files")
class TestRealGame(unittest.TestCase):
    def test_files_build_and_the_creature_is_a_plot_vendor(self):
        from pykotor.resource.formats.gff import read_gff
        files, problems = V.build_files(GAME)
        self.assertEqual(problems, [])
        self.assertIn("apvendor.utc", files)
        self.assertIn("ap_vendor.dlg", files)
        root = read_gff(files["apvendor.utc"]).root
        self.assertEqual((root.get_string("Tag"), str(root.get_resref("Conversation")), root.get_uint8("Plot")), ("apvendor", "ap_vendor", 1))

    def test_the_scripts_compile(self):
        import tempfile
        import shutil
        import k2compile
        work = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, work, True)
        k2compile.prepare_include_dir(work, GAME)
        for name, source in BV.script_sources(CFG).items():
            with open(os.path.join(work, name + ".nss"), "w", newline="\n") as f:
                f.write(source)
            ok, message = k2compile.compile_script(work, name)
            self.assertTrue(ok, "%s: %s" % (name, message))


if __name__ == "__main__":
    unittest.main()
