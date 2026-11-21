"""Tests of the droid model builder (tools/build_droid_models.py): the CONFIGs, the appearance rows that host the models, and (where the game and MDLOps exist) a real
build whose files are read back. The builds read the game's files and run MDLOps, so they skip with a message where either is missing. Run through
tools/run_client_tests.py."""
import ast
import math
import os
import re
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import build_droid_models as B  # noqa: E402

GAME = os.environ.get("K2_GAME_DIR") or B.DEFAULT_GAME_DIR
HAVE_GAME = os.path.isfile(os.path.join(GAME, "swkotor2.exe"))
HAVE_MDLOPS = B.mdlops_exe() is not None
try:
    import numpy as np
    import pykotor  # noqa: F401
    HAVE_LIBS = True
except ImportError:
    HAVE_LIBS = False
SKIP_GAME = "the KotOR 2 install was not found (set K2_GAME_DIR)"
SKIP_MDLOPS = "MDLOps was not found (set K2_MDLOPS_DIR to the folder that holds mdlops.exe)"
SKIP_LIBS = "pykotor and numpy are needed"


class TestConfigs(unittest.TestCase):
    def test_every_model_has_its_own_name_and_row(self):
        self.assertEqual(set(B.CONFIGS), {"assassin", "mining", "war", "protocol"})
        self.assertEqual(set(B.ORDER), set(B.CONFIGS))                 # the appearance.2da edit and "all" cover every model
        self.assertEqual(len(B.ORDER), len(set(B.ORDER)))
        self.assertEqual(len({c["new"] for c in B.CONFIGS.values()}), 4)
        self.assertEqual(len({c["host_row"] for c in B.CONFIGS.values()}), 4)
        self.assertEqual(len({c["label"] for c in B.CONFIGS.values()}), 4)
        for cfg in B.CONFIGS.values():
            self.assertLessEqual(len(cfg["new"]), 16, "a resource name is at most 16 characters")
            self.assertEqual(cfg["new"], cfg["new"].lower())
            self.assertNotEqual(cfg["host_row"], cfg["source_row"])
            self.assertNotIn(cfg["host_row"], range(91, 166), "rows 91 to 165 are the player's body rows (portraits.2da), never hosts")

    def test_the_host_rows_are_the_ones_the_world_and_the_droid_module_hand_out(self):
        # The world hands the four Battle Droid looks out (worlds/kotor2/__init__.py PLAYER_BATTLE_LOOKS) and client/k2_droid.py lists the rows that need a model
        # (HUMAN_RIG_ROWS): both must name exactly the host rows of CONFIGS (plus the HK-50 body, game row 538, which needs no model). If one of these fails, that file still
        # carries an older row number: change it to the number in CONFIGS, not the other way round (the old 91 and 92 are the player's own body rows).
        hosts = {c["host_row"]: c["new"] for c in B.CONFIGS.values()}
        with open(os.path.join(ROOT, "worlds", "kotor2", "__init__.py"), encoding="utf-8") as fh:
            world = fh.read()
        m = re.search(r"(?m)^PLAYER_BATTLE_LOOKS\s*=\s*\(([^)]*)\)", world)
        self.assertIsNotNone(m, "PLAYER_BATTLE_LOOKS (a tuple of appearance rows) is missing from the world")
        looks = {int(x) for x in m.group(1).replace(" ", "").split(",") if x}
        self.assertEqual(looks, set(hosts) | {538}, "the world hands out %s, the builder hosts %s" % (sorted(looks), sorted(hosts)))
        with open(os.path.join(ROOT, "client", "k2_droid.py"), encoding="utf-8") as fh:
            mod = fh.read()
        m = re.search(r"(?m)^HUMAN_RIG_ROWS\s*=\s*(\{[^}]*\})", mod)
        self.assertIsNotNone(m, "HUMAN_RIG_ROWS is missing from client/k2_droid.py")
        self.assertEqual(ast.literal_eval(m.group(1)), hosts)

    def test_every_mapped_donor_bone_is_used_once(self):
        for key, cfg in B.CONFIGS.items():
            donors = [d.lower() for d in cfg["map"].values()]
            self.assertEqual(len(donors), len(set(donors)), key)
            for chain in cfg["repose"]:
                self.assertIn(chain["start"], cfg["map"], key)
                self.assertIn(chain["donor_start"].lower(), donors, key)

    def test_the_skin_anchors_and_hand_hooks_name_known_nodes(self):
        for key, cfg in B.CONFIGS.items():
            for anchor in cfg["skin_anchor"].values():
                self.assertIn(anchor, cfg["map"], key)
            self.assertEqual(set(cfg["hook_hand_nodes"]), {"rhand", "lhand"}, key)
            for chain in cfg["repose"]:
                self.assertIn(chain["end"], cfg["map"], key)

    def test_only_the_mining_droid_builds_a_hand_and_its_skin_is_anchored_on_it(self):
        self.assertEqual([k for k, c in B.CONFIGS.items() if c.get("mirror_hand")], ["mining"])
        mh = B.CONFIGS["mining"]["mirror_hand"]
        self.assertEqual(mh["target"], "lhand_g")
        self.assertIn(mh["target"], B.CONFIGS["mining"]["map"])
        for new_skin in mh["skins"].values():
            self.assertEqual(B.CONFIGS["mining"]["skin_anchor"][new_skin], mh["target"])
        self.assertEqual(len(set(mh["names"].values())), len(mh["names"]))
        self.assertIn("rbullet", B.CONFIGS["mining"]["drop_nodes"])            # the cannon's muzzle dummy
        self.assertEqual(B.CONFIGS["mining"]["hook_follow"], {"handconjure": "lhand"})

    def test_the_war_droid_drops_its_blaster_and_the_protocol_droid_its_hand_copy(self):
        self.assertIn("RptBlstr", B.CONFIGS["war"]["drop_nodes"])
        self.assertIn("ShadowGeo", B.CONFIGS["protocol"]["drop_nodes"])
        for key, source in (("war", 66), ("protocol", 63)):
            self.assertEqual(B.CONFIGS[key]["source_row"], source)
        self.assertEqual(B.CONFIGS["war"]["resource"].lower(), "c_drdwar")
        self.assertEqual(B.CONFIGS["protocol"]["resource"].lower(), "c_drdprot")


@unittest.skipUnless(HAVE_LIBS, SKIP_LIBS)
class TestMath(unittest.TestCase):
    def test_a_rotation_survives_the_axis_angle_round_trip(self):
        m = B.rot((0.3, -0.5, 0.8, 1.1))
        self.assertTrue(np.allclose(B.rot(B.axis_angle(m)), m, atol=1e-9))
        self.assertTrue(np.allclose(B.rot((0, 0, 1, math.pi)), B.rot(B.axis_angle(B.rot((0, 0, 1, math.pi)))), atol=1e-9))

    def test_the_ascii_check_finds_a_repeated_name_a_missing_parent_and_a_bad_number(self):
        def model(*nodes):
            body = "".join("node dummy %s\n  parent %s\n  position  0 0 0\n  orientation  0 0 1 0\nendnode\n" % n for n in nodes)
            return "newmodel x\nbeginmodelgeom x\n" + body + "endmodelgeom x\n"
        self.assertEqual(B.check_ascii(model(("root", "NULL"), ("a", "root")), "x"), [])
        self.assertTrue(any("twice" in p for p in B.check_ascii(model(("root", "NULL"), ("a", "root"), ("A", "root")), "x")))
        self.assertTrue(any("missing parent" in p for p in B.check_ascii(model(("root", "NULL"), ("a", "gone")), "x")))
        self.assertTrue(any("before its parent" in p for p in B.check_ascii(model(("root", "NULL"), ("a", "b"), ("b", "root")), "x")))
        self.assertTrue(any("non-finite" in p for p in B.check_ascii(model(("root", "NULL")).replace("position  0 0 0", "position  nan 0 0"), "x")))

    def test_the_scaling_touches_only_the_geometry(self):
        text = "  bmin -1 -2 -3\n  radius 2\n  verts 2\n    1 2 3\n    4 5 6\n  faces 1\n    0 1 0 1 0 0 0\n"
        out = B.scale_mesh_text(text, 0.5)
        self.assertIn("bmin -0.5 -1 -1.5", out)
        self.assertIn("radius 1", out)
        self.assertIn("    0.5 1 1.5", out)
        self.assertIn("    0 1 0 1 0 0 0", out)

    def test_a_skin_loses_its_weights_block(self):
        out = B.strip_weights("  verts 1\n    0 0 0\n  weights 2\n    a 1\n    b 0.5 c 0.5\n  faces 0\n")
        self.assertNotIn("weights", out)
        self.assertNotIn("b 0.5", out)
        self.assertIn("faces 0", out)

    def test_a_noisy_identity_rotation_is_written_as_an_exact_identity(self):
        self.assertEqual(B.axis_angle(B.rot((0.6, 0.1, -0.8, 5e-6))), (0.0, 0.0, 1.0, 0.0))

    def test_a_repeated_node_name_is_renamed_and_the_children_follow_the_right_copy(self):
        def node(name, parent):
            return "node trimesh %s\n  parent %s\n  position  0 0 0\n  orientation  0 0 1 0\nendnode\n" % (name, parent)
        geo = "\n" + node("root", "NULL") + node("leg", "root") + node("box", "leg") + node("foot", "box") + node("thigh", "root") + node("box", "thigh") + node("kid", "box")
        out, renamed = B.unique_node_names(geo)
        self.assertEqual(renamed, [("box", "box_2")])
        nodes, order = B.parse_nodes(out)
        self.assertEqual(order, ["root", "leg", "box", "foot", "thigh", "box_2", "kid"])
        self.assertEqual((nodes["foot"].parent, nodes["box_2"].parent, nodes["kid"].parent), ("box", "thigh", "box_2"))
        self.assertEqual(B.check_ascii("newmodel x\nbeginmodelgeom x\n" + out + "endmodelgeom x\n", "x"), [])
        self.assertEqual(B.unique_node_names(out), (out, []))                     # nothing left to rename

    def test_a_mirrored_mesh_is_the_reflection_with_every_triangle_turned_around(self):
        # a tetrahedron, wound outward (its signed volume is positive)
        rest = ("  bmin 0 0 0\n  bmax 1 1 1\n  average 0.25 0.25 0.25\n  radius 1\n  verts 4\n    0 0 0\n    1 0 0\n    0 1 0\n    0 0 1\n"
                "  faces 4\n    0 2 1 1 0 2 1 0\n    0 1 3 1 0 1 3 0\n    1 2 3 2 1 2 3 0\n    0 3 2 4 0 3 2 0\n  tverts 4\n    0 0\n    1 0\n    0 1\n    1 1\n")
        T = np.diag([-1.0, 1.0, 1.0, 1.0])
        T[:3, 3] = [5.0, 0.0, 0.0]
        out = B.mirror_mesh_text(rest, T)
        nodes, _ = B.parse_nodes("node trimesh m\n  parent NULL\n" + rest + "endnode\nnode trimesh n\n  parent NULL\n" + out + "endnode\n")

        def volume(node):
            v = np.array([[float(x) for x in ln.split()[:3]] for ln in node.rest.split("verts 4\n")[1].splitlines()[:4]])
            f = [[int(x) for x in ln.split()[:3]] for ln in node.rest.split("faces 4\n")[1].splitlines()[:4]]
            return sum(np.linalg.det(np.array([v[a], v[b], v[c]])) for a, b, c in f) / 6
        # a signed volume taken about the origin: the mirrored copy sits 5 along x, so compare through the same translation
        self.assertGreater(volume(nodes["m"]), 0)
        pts = np.array([[5, 0, 0], [4, 0, 0], [5, 1, 0], [5, 0, 1]], dtype=float)
        self.assertTrue(np.allclose(B.mesh_points(nodes["n"], np.eye(4)), pts))
        moved = B.mesh_points(nodes["n"], np.eye(4)) - np.array([5.0, 0, 0])
        f = [[int(x) for x in ln.split()[:3]] for ln in out.split("faces 4\n")[1].splitlines()[:4]]
        self.assertGreater(sum(np.linalg.det(np.array([moved[a], moved[b], moved[c]])) for a, b, c in f) / 6, 0)   # still outward: the winding was reversed
        self.assertIn("bmin 4 0 0", out)
        self.assertIn("bmax 5 1 1", out)
        self.assertIn("average 4.75 0.25 0.25", out)
        self.assertIn("    0 1 2 1 0 1 2 0", out)           # the first face: vertices 2 and 3 swapped, and their UV indices with them
        self.assertIn("  tverts 4\n    0 0\n    1 0\n", out)  # the UVs themselves are not touched
        with self.assertRaises(RuntimeError):
            B.mirror_mesh_text(rest, np.eye(4))             # not a reflection


@unittest.skipUnless(HAVE_LIBS, SKIP_LIBS)
@unittest.skipUnless(HAVE_GAME, SKIP_GAME)
class TestAppearanceRows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from pykotor.resource.formats.twoda import read_2da
        from pykotor.extract.installation import Installation
        from pykotor.resource.type import ResourceType
        import logging
        logging.disable(logging.CRITICAL)
        # the game's own table (chitin): a seed patched into this machine's game folder leaves its edited appearance.2da in Override, which would not be the table the rows are for
        base = B._resource(Installation(GAME), "appearance", ResourceType.TwoDA)
        cls.original = read_2da(base)
        data, cls.plan = B.appearance_rows(GAME, base)
        cls.table = read_2da(data)

    def test_the_hosts_are_unused_placeholders_in_the_game_file(self):
        for blank in (82, 29):                                                         # the two completely blank rows of the table
            self.assertEqual(self.original.get_row(blank).get_string("race"), "")
            self.assertEqual(self.original.get_row(blank).get_string("label"), "")
            self.assertEqual(self.original.get_row(blank).get_string("modela"), "")
        self.assertEqual(self.original.get_row(58).get_string("race").lower(), "c_notready")      # Droid_Nul
        self.assertEqual(self.original.get_row(380).get_string("label"), "Twilek_Jedi_Male")      # a cut body row: no race, no creature or table uses it
        self.assertEqual(self.original.get_row(380).get_string("race"), "")
        self.assertEqual({c["host_row"] for c in B.CONFIGS.values()}, {82, 58, 29, 380})

    def test_no_host_row_is_one_of_the_players_body_rows(self):
        # portraits.2da gives the character generator the appearance rows of the player (columns appearancenumber, appearance_s, appearance_l; rows 91 and up are the P_FEM/P_MAL
        # body types). A droid hosted there would replace the player's own body.
        for cfg in B.CONFIGS.values():
            self.assertFalse(self.original.get_row(cfg["host_row"]).get_string("label").startswith("P_"), cfg["host_row"])
        self.assertEqual(self.original.get_row(91).get_string("label"), "P_FEM_A_SML_01")        # why 91 and 92 are not hosts
        self.assertEqual(self.original.get_row(92).get_string("label"), "P_FEM_A_MED_01")

    def test_no_host_row_is_a_look_of_the_generated_or_extra_companions(self):
        # row 27 (Smuggler_01, unused by the game itself) is one of the looks the generated companions draw from, which is why it is not a host
        import json
        with open(os.path.join(ROOT, "data", "extra_companions.json"), encoding="utf-8") as fh:
            data = json.load(fh)
        used = set()

        def walk(node, key=""):
            if isinstance(node, dict):
                for k, v in node.items():
                    walk(v, k)
            elif isinstance(node, list):
                for v in node:
                    walk(v, key)
            elif isinstance(node, int) and not isinstance(node, bool) and ("appearance" in key or "look" in key):
                used.add(node)
        walk(data)
        self.assertIn(27, used)                                                                     # the scan reads the pool
        self.assertEqual(used & {c["host_row"] for c in B.CONFIGS.values()}, set())

    def test_each_host_row_points_at_its_model_and_keeps_the_droids_settings(self):
        for key, cfg in B.CONFIGS.items():
            row, src = self.table.get_row(cfg["host_row"]), self.original.get_row(cfg["source_row"])
            self.assertEqual(row.get_string("race"), cfg["new"])
            self.assertEqual(row.get_string("modeltype"), "F")
            self.assertEqual(row.get_string("label"), cfg["label"])
            for h in self.table.get_headers():
                if h in cfg.get("row_cells", {}):                          # a setting the human-rig body needs different from the creature row's
                    self.assertEqual(row.get_string(h), cfg["row_cells"][h], "%s column %s" % (key, h))
                elif h not in ("label", "race", "modeltype"):
                    self.assertEqual(row.get_string(h), src.get_string(h), "%s column %s" % (key, h))
            self.assertEqual(self.plan[key]["row"], cfg["host_row"])
            self.assertEqual(self.plan[key]["previous"]["race"], self.original.get_row(cfg["host_row"]).get_string("race"))

    def test_each_row_keeps_the_texture_of_its_source_row(self):
        for key, texture in (("mining", "C_MK2_DRD"), ("war", ""), ("protocol", ""), ("assassin", "")):
            self.assertEqual(self.table.get_row(B.CONFIGS[key]["host_row"]).get_string("racetex"), texture, key)

    def test_no_other_row_changes_and_the_height_stays(self):
        hosts = {c["host_row"] for c in B.CONFIGS.values()}
        self.assertEqual(self.table.get_height(), self.original.get_height())
        for i in range(self.original.get_height()):
            if i not in hosts:
                for h in self.original.get_headers():
                    self.assertEqual(self.table.get_row(i).get_string(h), self.original.get_row(i).get_string(h))

    def test_no_creature_template_in_the_base_game_uses_a_host_row(self):
        # every creature template of the game's archives and of every module (the module archives hold most of them)
        from pykotor.extract.installation import Installation
        from pykotor.resource.formats.gff import read_gff
        from pykotor.resource.type import ResourceType
        inst = Installation(GAME)
        hosts = {c["host_row"] for c in B.CONFIGS.values()}
        used = {}
        sources = [("chitin", inst.chitin_resources())] + [(m, inst.module_resources(m)) for m in inst.module_names()]
        scanned = 0
        for where, resources in sources:
            for res in resources:
                if res.restype() == ResourceType.UTC:
                    scanned += 1
                    row = read_gff(res.data()).root.get_uint16("Appearance_Type")
                    if row in hosts:
                        used[where + ":" + res.resname()] = row
        self.assertGreater(scanned, 1500)                                      # the scan really saw the game's templates
        self.assertEqual(used, {})

    def test_no_game_table_refers_to_a_host_row(self):
        # the tables that name an appearance row: the portraits of the player (appearancenumber/appearance_s/appearance_l), body bags, polymorph, force shields, racial types
        from pykotor.extract.installation import Installation
        from pykotor.resource.formats.twoda import read_2da
        from pykotor.resource.type import ResourceType
        hosts = {str(c["host_row"]) for c in B.CONFIGS.values()}
        seen_tables, hits = set(), []
        for res in Installation(GAME).chitin_resources():
            if res.restype() != ResourceType.TwoDA or res.resname().lower() == "appearance":
                continue
            table = read_2da(res.data())
            for column in table.get_headers():
                if "appear" in column.lower():
                    seen_tables.add(res.resname().lower())
                    hits += [(res.resname(), column, i) for i in range(table.get_height()) if table.get_row(i).get_string(column).strip() in hosts]
        self.assertTrue({"portraits", "bodybag"} <= seen_tables, seen_tables)
        self.assertEqual(hits, [])


@unittest.skipUnless(HAVE_LIBS, SKIP_LIBS)
@unittest.skipUnless(HAVE_GAME, SKIP_GAME)
@unittest.skipUnless(HAVE_MDLOPS, SKIP_MDLOPS)
class TestBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import logging
        from pykotor.extract.installation import Installation
        cls.out = tempfile.TemporaryDirectory(prefix="k2droid_test_")
        cls.files, cls.problems = B.build(GAME, cls.out.name, "all")
        # the assembled ascii of every model (what was compiled), for geometry checks on the vertices themselves
        logging.disable(logging.CRITICAL)
        inst, exe = Installation(GAME), B.mdlops_exe()
        reserved = B._animated_names(inst)
        cls.nodes, cls.glob, cls.notes = {}, {}, {}
        with tempfile.TemporaryDirectory(prefix="k2droid_asm_") as work:
            donor = B.decompile(inst, exe, B.DONOR, os.path.join(work, "donor"))
            for key, cfg in B.CONFIGS.items():
                droid = B.decompile(inst, exe, cfg["resource"], os.path.join(work, key))
                text, cls.notes[key] = B.assemble(cfg, droid, donor, reserved)
                _, _, geo, _ = B.split_geometry(text)
                cls.nodes[key], _ = B.parse_nodes(geo)
                cls.glob[key] = B.global_mats(cls.nodes[key])

    @classmethod
    def tearDownClass(cls):
        cls.out.cleanup()

    # ------------------------------------------------------------------ helpers
    def _read(self, key):
        cfg = B.CONFIGS[key]
        return B.read_compiled(self.files[cfg["new"] + ".mdl"], self.files[cfg["new"] + ".mdx"])

    def _name(self, key, lower):
        return next(n for n in self.nodes[key] if n.lower() == lower.lower())

    def _pts(self, key, name):
        """the vertices of a node of the assembled model, in model space"""
        return B.mesh_points(self.nodes[key][name], self.glob[key][name])

    def _faces(self, key, name):
        m = re.search(r"(?m)^[ \t]*faces[ \t]+(\d+)\s*\n((?:[ \t]+\d+(?:[ \t]+\d+){7}[ \t]*\n)+)", self.nodes[key][name].rest)
        return [[int(x) for x in ln.split()[:3]] for ln in m.group(2).strip().splitlines()[: int(m.group(1))]]

    def _outward(self, key, name):
        """the share of a piece's triangles that face away from the piece's middle (1.0 for a convex piece wound outward, 0.0 for one wound inside out)"""
        p = self._pts(key, name)
        middle = p.mean(axis=0)
        out = total = 0
        for a, b, c in self._faces(key, name):
            n = np.cross(p[b] - p[a], p[c] - p[a])
            if np.linalg.norm(n) < 1e-12:
                continue
            total += 1
            out += float(np.dot(n, (p[a] + p[b] + p[c]) / 3 - middle)) > 0
        return out / total

    def _hand(self, key, side):
        """the node names of one hand of the assembled model: the palm, everything below it, and (the mining droid) the finger skin that rides on it"""
        nodes = self.nodes[key]
        if key == "mining":
            return {"r": ["rhand_g_ap", "RafngrB_g_ap", "RafngrT_g_ap", "RbfngrB_g_ap", "RbfngrT_g_ap", "RcfngrB_g_ap", "RcfngrT_g_ap", "fingers"],
                    "l": ["lhand_g_ap", "LafngrB_g_ap", "LafngrT_g_ap", "LbfngrB_g_ap", "LbfngrT_g_ap", "LcfngrB_g_ap", "LcfngrT_g_ap", "lfingers"]}[side]
        palm = B.CONFIGS[key]["hook_hand_nodes"]["rhand" if side == "r" else "lhand"][0]
        palm = palm if palm in nodes else palm + B.SUFFIX
        below, stack = [], [palm]
        while stack:
            cur = stack.pop()
            below.append(cur)
            stack += [n for n, v in nodes.items() if v.parent == cur]
        return below

    def _box(self, key, names):
        p = np.vstack([self._pts(key, n) for n in names])
        return p.min(axis=0), p.max(axis=0)

    def _at(self, key, name):
        return self.glob[key][self._name(key, name)][:3, 3]

    @staticmethod
    def _quat(q):
        x, y, z, w = q.x, q.y, q.z, q.w
        return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                         [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                         [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])

    def _compiled_globals(self, key):
        out = {}

        def walk(node, parent):
            m = np.eye(4)
            m[:3, :3] = self._quat(node.orientation)
            m[:3, 3] = [node.position.x, node.position.y, node.position.z]
            out[node.name.lower()] = parent @ m
            for c in node.children:
                walk(c, out[node.name.lower()])
        walk(self._read(key).root, np.eye(4))
        return out

    # ------------------------------------------------------------------ the files
    def test_the_build_reports_no_problem(self):
        self.assertEqual(self.problems, [])

    def test_every_model_comes_out_as_mdl_and_mdx_and_is_written_to_the_out_folder(self):
        self.assertEqual(sorted(self.files), sorted("%s.%s" % (c["new"], e) for c in B.CONFIGS.values() for e in ("mdl", "mdx")))
        self.assertEqual(len(self.files), 8)
        for cfg in B.CONFIGS.values():
            for ext in ("mdl", "mdx"):
                name = "%s.%s" % (cfg["new"], ext)
                self.assertGreater(len(self.files[name]), 10000, name)
                with open(os.path.join(self.out.name, name), "rb") as fh:
                    self.assertEqual(fh.read(), self.files[name])

    def test_the_models_read_back_with_the_human_supermodel_and_no_animations_of_their_own(self):
        for key, cfg in B.CONFIGS.items():
            model = self._read(key)
            self.assertEqual(model.supermodel, "S_Female02", key)
            self.assertEqual(len(model.anims), 0, key)
            names = [n.name.lower() for n in model.all_nodes()]
            self.assertEqual(len(names), len(set(names)), key + ": repeated node names")
            self.assertEqual(len(names), len(self.nodes[key]), key + ": the compiled model has the nodes of the ascii")
            for bone in cfg["map"].values():
                self.assertIn(bone.lower(), names, key)
            for hook in ("rhand", "lhand", "headconjure", "camerahook", "impact", "talkdummy", "handconjure"):
                self.assertIn(hook, names, key)

    def test_the_mdx_holds_only_finite_numbers(self):
        for key, cfg in B.CONFIGS.items():
            data = self.files[cfg["new"] + ".mdx"]
            self.assertEqual(len(data) % 4, 0, key)
            values = np.frombuffer(data, dtype="<f4")
            self.assertTrue(np.isfinite(values).all(), key)
            self.assertLessEqual(float(np.abs(values).max()), 1.0e7, key)       # the largest value in a vertex block is its 10000000 end marker

    def test_the_compiled_models_put_every_node_where_the_assembled_ascii_does(self):
        # the round trip: MDLOps' binary, read back, has the same global transform for every node (hooks, hands, bones) as the ascii that was compiled
        for key in B.CONFIGS:
            compiled = self._compiled_globals(key)
            self.assertEqual(set(compiled), {n.lower() for n in self.nodes[key]}, key)
            worst = max(float(np.abs(compiled[n.lower()] - self.glob[key][n]).max()) for n in self.nodes[key])
            self.assertLess(worst, 1e-4, key)

    def test_the_compiled_meshes_have_the_bounds_of_the_assembled_ascii_and_those_hold_the_vertices(self):
        # the binary's bounding box of each mesh (in the node's own space) is the ascii's bmin/bmax widened to take in the node's origin (which is how MDLOps compiles it), and the
        # ascii's box contains every vertex it lists (the mirrored hand's boxes were recomputed from its mirrored vertices; the droid's and the donor's own boxes are kept)
        for key in B.CONFIGS:
            checked = 0
            for node in self._read(key).all_nodes():
                if node.mesh is None:
                    continue
                name = self._name(key, node.name)
                rest = self.nodes[key][name].rest
                v = B.mesh_points(self.nodes[key][name], np.eye(4))
                lo = np.array([float(x) for x in re.search(r"(?m)^\s*bmin\s+(\S+)\s+(\S+)\s+(\S+)", rest).groups()])
                hi = np.array([float(x) for x in re.search(r"(?m)^\s*bmax\s+(\S+)\s+(\S+)\s+(\S+)", rest).groups()])
                got = np.array([[node.mesh.bb_min.x, node.mesh.bb_min.y, node.mesh.bb_min.z], [node.mesh.bb_max.x, node.mesh.bb_max.y, node.mesh.bb_max.z]])
                self.assertTrue(np.allclose(got, [np.minimum(lo, 0), np.maximum(hi, 0)], atol=2e-4), "%s %s: the compiled box is not the ascii's" % (key, name))
                self.assertTrue(np.all(v >= lo - 2e-4) and np.all(v <= hi + 2e-4), "%s %s: a vertex lies outside the stated box" % (key, name))
                checked += 1
            self.assertGreater(checked, 20, key)

    def test_the_build_is_repeatable(self):
        for key in ("mining", "protocol"):
            files, problems = B.build(GAME, None, key)
            self.assertEqual(problems, [])
            new = B.CONFIGS[key]["new"]
            self.assertEqual(files[new + ".mdl"], self.files[new + ".mdl"])

    def test_a_missing_tool_or_game_is_a_problem_not_an_exception(self):
        files, problems = B.build(os.path.join(ROOT, "no_such_game_folder"), None, "all")
        self.assertEqual(files, {})
        self.assertTrue(problems)
        files, problems = B.build(GAME, None, "no_such_model")
        self.assertEqual(files, {})
        self.assertTrue(any("unknown model" in p for p in problems))

    # ------------------------------------------------------------------ the pieces each model keeps and loses
    def test_the_assassin_and_the_war_droid_lose_only_the_held_blaster_and_its_helpers(self):
        assassin = {n.name.lower() for n in self._read("assassin").all_nodes()}
        for gone in ("rptblstr", "rhdold", "rbullet"):
            self.assertNotIn(gone, assassin)
        war = {n.name.lower() for n in self._read("war").all_nodes()}
        for gone in ("rptblstr", "dummy01", "dummy02", "rbullet", "spark", "auroralight01"):          # the blaster, its helpers and the droid's spark emitter and light
            self.assertNotIn(gone, war)
        for kept in ("belly", "chest", "neck", "groin", "r_upperarm", "l_upperarm", "rhanddrd", "lhanddrd", "rfngr01", "rlfngr01", "rfngr02", "rlfngr02", "ruthmb", "rthmb",
                     "lfngr1", "llfngr1", "lfngr02", "llfngr02", "luthmb", "lthmb", "r_foot", "l_foot"):
            self.assertIn(kept, war)
        # the war droid's own handconjure was a muzzle dummy under the blaster, out at the arm: the model's is the donor's, in front of the chest
        self.assertLess(abs(self._at("war", "handconjure")[0]), 0.2)
        self.assertGreater(self._at("war", "handconjure")[1], 0.5)

    def test_the_mining_droid_keeps_every_piece_but_the_cannon(self):
        mining = {n.name.lower() for n in self._read("mining").all_nodes()}
        for kept in ("rpod", "lpod", "leftuprarm", "ruprarm", "lfoor_t", "rfoot_t", "waist01", "waist", "fingers", "neck"):
            self.assertIn(kept, mining)
        for renamed in ("pelvis_g_ap", "torso_g_ap", "head_g_ap", "rhand_g_ap", "rafngrb_g_ap"):      # a droid piece named like a donor bone is renamed, not dropped
            self.assertIn(renamed, mining)
        self.assertNotIn("rbullet", mining)                                                            # the cannon's muzzle dummy
        for new in ("lhand_g_ap", "lafngrb_g_ap", "lafngrt_g_ap", "lbfngrb_g_ap", "lbfngrt_g_ap", "lcfngrb_g_ap", "lcfngrt_g_ap", "lfingers"):   # the new left hand
            self.assertIn(new, mining)

    def test_the_protocol_droid_renames_its_repeated_names_and_drops_the_hand_copy(self):
        protocol = {n.name.lower() for n in self._read("protocol").all_nodes()}
        self.assertNotIn("shadowgeo", protocol)
        for kept in ("rwr_box", "rwr_box_2", "lwr_box", "lwr_box_2", "rhnd", "rfngr1", "rfngr2", "ruthmb", "rlfngr1", "rlfngr2", "rthmb", "rhand2", "lhand2", "lfngr1", "lfngr2",
                     "luthmb", "lthmb", "rfoot", "lfoot", "reye", "leye", "l4rm", "r4rm"):
            self.assertIn(kept, protocol)
        self.assertTrue(any("Rwr_box->Rwr_box_2" in n and "Lwr_box->Lwr_box_2" in n for n in self.notes["protocol"]))

    # ------------------------------------------------------------------ the hands
    def test_the_hand_hooks_of_every_model_sit_inside_their_hand(self):
        # the weapon hooks (rhand, lhand) lie within the bounding box of the hand they are for: the palm and every finger and thumb piece, in the model's rest pose
        for key in B.CONFIGS:
            for hook, side in (("rhand", "r"), ("lhand", "l")):
                lo, hi = self._box(key, self._hand(key, side))
                p = self._at(key, hook)
                self.assertTrue(np.all(p >= lo - 1e-6) and np.all(p <= hi + 1e-6), "%s %s hook %s outside the hand %s..%s" % (key, hook, np.round(p, 3).tolist(), np.round(lo, 3).tolist(), np.round(hi, 3).tolist()))
                self.assertGreater(abs(p[0]), 0.4, key)                                        # out at the arm, not at the body
                self.assertEqual(p[0] > 0, side == "r", key)                                   # the right hook on the right (+x)
                self.assertLess(p[2], 1.2, key)                                                # an arm that hangs, not one left up in a T-pose (the human rest hand is at 0.94)
                plo, phi = self._box(key, self._hand(key, side)[:1])                           # and in the palm itself (the first piece)
                self.assertTrue(np.all(p >= plo - 1e-6) and np.all(p <= phi + 1e-6), "%s %s hook is not inside the palm %s..%s" % (key, hook, np.round(plo, 3).tolist(), np.round(phi, 3).tolist()))

    def test_the_two_hooks_of_every_model_mirror_each_other_about_the_body(self):
        for key in B.CONFIGS:
            r, l = self._at(key, "rhand"), self._at(key, "lhand")
            self.assertLess(abs(r[0] + l[0]), 0.06, key)                                       # the same distance from the centre line (the arms are posed independently)
            self.assertLess(abs(r[1] - l[1]), 0.06, key)
            self.assertLess(abs(r[2] - l[2]), 0.06, key)

    def test_the_mining_hooks_lie_in_the_hands_and_not_at_the_end_of_the_cannon(self):
        # the Mining Mk II's cannon ended about 0.5 m below the wrist; the hooks are within 0.2 m of the wrist, in the middle of the hand
        for hook, wrist in (("rhand", "rhand_g_ap"), ("lhand", "lhand_g_ap")):
            self.assertLess(float(np.linalg.norm(self._at("mining", hook) - self._at("mining", wrist))), 0.2, hook)
        self.assertTrue(np.allclose(self._at("mining", "handconjure"), self._at("mining", "lhand"), atol=1e-4))      # the muzzle effect point moved into the hand

    def test_the_mining_droids_left_hand_is_the_mirror_image_of_its_right_hand(self):
        pairs = list(zip(self._hand("mining", "r"), self._hand("mining", "l")))
        self.assertEqual(len(pairs), 8)

        def handed(p):
            """the sign of the volume of the first four independent vertices: it changes when a shape is mirrored"""
            for i in range(len(p) - 3):
                d = float(np.linalg.det(np.array([p[i + 1] - p[i], p[i + 2] - p[i], p[i + 3] - p[i]])))
                if abs(d) > 1e-9:
                    return d
            return 0.0
        for right, left in pairs:
            r, l = self._pts("mining", right), self._pts("mining", left)
            self.assertEqual(len(r), len(l), (right, left))
            self.assertGreater(len(r), 10, right)
            # the same vertices in the same order: every distance between two of them is the same (a mirror image is congruent) ...
            dr = np.linalg.norm(r[:, None, :] - r[None, :, :], axis=2)
            dl = np.linalg.norm(l[:, None, :] - l[None, :, :], axis=2)
            self.assertLess(float(np.abs(dr - dl).max()), 2e-4, (right, left))
            # ... and the handedness is the opposite
            self.assertLess(handed(r) * handed(l), 0, (right, left))
        # the hand lies on the left of the body, as the right one lies on the right, as wide, as tall and as low
        rlo, rhi = self._box("mining", self._hand("mining", "r"))
        llo, lhi = self._box("mining", self._hand("mining", "l"))
        self.assertLess(lhi[0], -0.5)
        self.assertGreater(rlo[0], 0.5)
        self.assertLess(abs((rhi[0] - rlo[0]) - (lhi[0] - llo[0])), 0.02)
        self.assertLess(abs((rhi[2] - rlo[2]) - (lhi[2] - llo[2])), 0.02)
        self.assertLess(abs(rlo[2] - llo[2]), 0.03)                                            # the cannon's barrel reached 0.2 m lower than the fingers do
        self.assertLess(abs((rlo[0] + rhi[0]) / 2 + (llo[0] + lhi[0]) / 2), 0.05)              # the middles are mirror images about the centre line

    def test_the_mirrored_pieces_are_wound_like_their_originals(self):
        # a mirror image is only right-side-out when every triangle's winding was reversed: as many triangles of each piece face away from its middle as on its right-hand source
        for right, left in zip(self._hand("mining", "r"), self._hand("mining", "l")):
            a, b = self._outward("mining", right), self._outward("mining", left)
            self.assertTrue(a > 0.7 or a < 0.3, (right, a))                                   # the source's winding is clearly one way, so the comparison means something
            self.assertLess(abs(a - b), 0.05, "%s faces away from its middle in %.0f%% of its triangles, its mirror %s in %.0f%%" % (right, 100 * a, left, 100 * b))
        # the cannon geometry is gone: the left palm has the right palm's vertices and faces, not the cannon's 74 vertices
        self.assertEqual(len(self._pts("mining", "lhand_g_ap")), len(self._pts("mining", "rhand_g_ap")))
        self.assertEqual(len(self._faces("mining", "lhand_g_ap")), len(self._faces("mining", "rhand_g_ap")))

    def test_the_left_hand_hangs_on_the_left_wrist_and_no_lower_than_the_right_hand(self):
        left_low, right_low = self._box("mining", self._hand("mining", "l"))[0][2], self._box("mining", self._hand("mining", "r"))[0][2]
        self.assertLess(abs(left_low - right_low), 0.03)
        # the palm's origin is the joint the donor's left hand bone sits on
        self.assertLess(float(np.linalg.norm(self._at("mining", "lhand_g_ap") - self._at("mining", "lhand_g"))), 1e-3)

    def test_the_new_left_hand_turns_with_the_left_arm(self):
        # the palm hangs on the donor's left hand bone, the finger pieces on the palm, the skin of the fingers became a rigid piece on the hand bone
        nodes = self.nodes["mining"]
        self.assertEqual(nodes["lhand_g_ap"].parent.lower(), "lhand_g")
        self.assertEqual(nodes["lfingers"].parent.lower(), "lhand_g")
        self.assertEqual(nodes["lfingers"].kind, "trimesh")
        self.assertNotIn("weights", nodes["lfingers"].rest)
        for finger in ("LafngrB_g_ap", "LbfngrB_g_ap", "LcfngrB_g_ap"):
            self.assertEqual(nodes[finger].parent, "lhand_g_ap")
        for finger in ("LafngrT_g_ap", "LbfngrT_g_ap", "LcfngrT_g_ap"):
            self.assertEqual(nodes[finger].parent, finger.replace("T_g", "B_g"))


if __name__ == "__main__":
    for flag, text in ((HAVE_LIBS, SKIP_LIBS), (HAVE_GAME, SKIP_GAME), (HAVE_MDLOPS, SKIP_MDLOPS)):
        if not flag:
            print("skipping part of the droid model tests: " + text)
    unittest.main()
