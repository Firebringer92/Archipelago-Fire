"""The client refuses a seed made by a different KOTOR world release (the item and location ids can differ between releases)."""
import os
import unittest

KOTOR_CLIENT = os.path.join(os.path.dirname(__file__), "..", "..", "..", "KotorClient.py")


@unittest.skipUnless(os.path.exists(KOTOR_CLIENT), "client not next to this world")
class TestWorldVersionCheck(unittest.TestCase):
    def test_the_same_release_is_accepted(self):
        import KotorClient
        from worlds.kotor import WORLD_VERSION
        self.assertIsNone(KotorClient.world_version_problem({"world_version": WORLD_VERSION}))

    def test_another_release_is_refused_with_both_numbers(self):
        import KotorClient
        problem = KotorClient.world_version_problem({"world_version": "0.1.9"})
        self.assertIn("0.1.9", problem)
        self.assertIn(KotorClient.WORLD_VERSION, problem)

    def test_a_seed_with_no_version_is_refused(self):
        import KotorClient
        self.assertIn("older version", KotorClient.world_version_problem({}))

    def test_every_seed_carries_the_world_version(self):
        from worlds.kotor import WORLD_VERSION
        from test.bases import WorldTestBase

        class T(WorldTestBase):
            game = "KotOR"
            def runTest(self): pass
        t = T()
        t.setUp()
        self.assertEqual(t.world.fill_slot_data()["world_version"], WORLD_VERSION)
