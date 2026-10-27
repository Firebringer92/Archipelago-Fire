"""A Bazaar item created from its template must be ONE item. The token patch puts "one token" into each container by naming the template; a template with a
stack size of 99 made each container hold 99 (found in a playtest)."""
import os
import sys
import unittest

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "scripts")
GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"


@unittest.skipUnless(os.path.isdir(SCRIPTS), "scripts folder not next to this world")
class TestBazaarItems(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.abspath(SCRIPTS))
        import generate_bazaar_jawa as jawa
        cls.jawa = jawa

    def test_the_default_stack_is_one(self):
        self.assertEqual(self.jawa.ITEM_STACK_SIZE, 1)

    @unittest.skipUnless(os.path.isdir(GAME_DIR), "no game install to read the base items from")
    def test_each_built_item_is_a_single_item(self):
        from pykotor.extract.installation import Installation
        from pykotor.resource.formats.gff import read_gff
        installation = Installation(GAME_DIR)
        built = {
            self.jawa.BUY_RESREF: self.jawa.build_item(installation, self.jawa.BUY_RESREF, "x", "y"),
            self.jawa.SWAP_RESREF: self.jawa.build_item(installation, self.jawa.SWAP_RESREF, "x", "y"),
            self.jawa.TOKEN_RESREF: self.jawa.build_item(installation, self.jawa.TOKEN_RESREF, "x", "y", base=self.jawa.TOKEN_LOOK_TEMPLATE),
        }
        for resref, data in built.items():
            with self.subTest(item=resref):
                self.assertEqual(read_gff(data).root.get_uint16("StackSize"), 1)
