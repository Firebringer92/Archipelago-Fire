"""
The Unknown World finale (unk_m41aa, OnEnter k_punk_41aa_en): the confrontation conversation has lines spoken by Carth, Canderous, Mission and Zaalbar by object tag. The game's own entry script
spawns them only if they are available, so a companion who was never recruited left the scene without a speaker and it stopped. The area trampoline makes them available first. Both generators
(the packaging one and the per-seed one) build the same trampoline, so their copies of the table must not drift apart.
"""
import os
import re
import unittest

SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))), "scripts")
FILES = ("generate_area_trampolines.py", "generate_trampoline_batch.py")


def _table(name):
    with open(os.path.join(SCRIPTS, name), encoding="utf-8") as f:
        text = f.read().replace("\r\n", "\n")
    start = text.index("ORIGINAL_ENTER_BACKFILL = {")
    end = text.index("\n}\n", start) + 3
    return text[start:end]


def _pre(name):
    ns = {}
    exec(_table(name), ns)
    pre, post = ns["ORIGINAL_ENTER_BACKFILL"]["k_punk_41aa_en"]
    return pre, post


class TestUnknownWorldBackfill(unittest.TestCase):
    def test_both_generators_carry_the_same_table(self):
        self.assertEqual(_table(FILES[0]), _table(FILES[1]))

    def test_every_speaker_of_the_scene_is_made_available(self):
        pre, post = _pre(FILES[0])
        for npc, template in (("NPC_CARTH", "p_carth"), ("NPC_CANDEROUS", "p_cand"), ("NPC_MISSION", "p_mission"), ("NPC_T3_M4", "p_t3m4"), ("NPC_ZAALBAR", "p_zaalbar")):
            self.assertIn(f'AddAvailableNPCByTemplate({npc}, "{template}")', pre)
            self.assertIn(f"!IsAvailableCreature({npc})", pre)

    def test_it_only_runs_on_the_entry_that_spawns_the_crew(self):
        """The original spawns the crew when G_FinalChoice is above 0 and UNK_PARTYSHOWDOWN is 0; making a companion available on any other entry would hand out a recruit early."""
        pre, post = _pre(FILES[0])
        self.assertIn('GetGlobalNumber("G_FinalChoice") > 0', pre)
        self.assertIn('GetGlobalNumber("UNK_PARTYSHOWDOWN") == 0', pre)
        self.assertIn("GetIsPC(GetEnteringObject())", pre)

    def test_zaalbar_is_left_alone_when_the_story_took_him(self):
        pre, post = _pre(FILES[0])
        self.assertIn('!GetGlobalBoolean("tat_ZaalbarTaken")', pre)

    def test_nothing_is_taken_away_afterwards(self):
        """The scene needs them standing there for minutes, so there is no revert in the trampoline; the roster cleanup handles anyone without an entitlement."""
        pre, post = _pre(FILES[0])
        self.assertEqual(post, "")

    def test_the_generated_text_is_balanced(self):
        pre, post = _pre(FILES[0])
        self.assertEqual(pre.count("{"), pre.count("}"))
        self.assertEqual(pre.count("("), pre.count(")"))
        self.assertTrue(re.search(r'KSE_Diag\(141, "AP\|SAFEGUARD\|unk41_showdown_backfill\|', pre))


if __name__ == "__main__":
    unittest.main()
