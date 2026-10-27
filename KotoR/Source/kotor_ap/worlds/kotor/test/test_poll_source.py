"""Checks on the generated heartbeat poll source (extender/scripts_src/ap_poll_shared.nss, written by scripts/generate_poll_shared.py)."""
import os
import re
import unittest

POLL = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "extender", "scripts_src", "ap_poll_shared.nss")


@unittest.skipUnless(os.path.exists(POLL), "generated poll not next to this world")
class TestTombDoors(unittest.TestCase):
    def setUp(self):
        with open(POLL, encoding="utf-8") as f:
            self.source = f.read()

    def test_the_tomb_doors_are_unlocked_once_both_are_dead(self):
        body = re.search(r"void CheckTombDoors\(\)\s*\{(.*?)\n\}", self.source, re.S).group(1)
        self.assertIn('"korr_m39aa"', body)
        for tag in ("kor39_utharwynn", "kor39_yuthura", "k39_door_starmap", "kor39_kor36"):
            self.assertIn(tag, body)
        # both must be dead before anything is unlocked
        self.assertEqual(len(re.findall(r"GetIsDead\(", body)), 2)
        self.assertEqual(len(re.findall(r"SetLocked\(\w+, FALSE\)", body)), 2)

    def test_the_poll_runs_it(self):
        main = self.source[self.source.index("void main()"):]
        self.assertIn("CheckTombDoors();", main)


@unittest.skipUnless(os.path.exists(POLL), "generated poll not next to this world")
class TestItemArms(unittest.TestCase):
    def test_every_item_that_sends_a_plain_arm_has_it_in_the_poll(self):
        """An item whose arm the poll does not know fails every time with 'the game does not know the action' (Charisma did, as grant_test_ability)."""
        from .. import item_table
        with open(POLL, encoding="utf-8") as f:
            source = f.read()
        known = set(re.findall(r'if \(sName == "(\w+)"\) \{ DtArm_', source))
        plain = {data.arm_name for data in item_table.values() if data.arm_name and ":" not in data.arm_name}
        plain.discard("goal_marker")           # marks the goal, nothing is applied
        self.assertEqual(plain - known, set())
