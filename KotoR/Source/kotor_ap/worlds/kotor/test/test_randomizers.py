"""The two extender randomisers (randomised dialogue replies, randomised alignment pushes): the options reach the client in slot_data, off by default."""
from .test_generation import KotorScenario


class TestRandomizersOff(KotorScenario):
    options = {"companion_mode": 0}

    def test_both_are_off_in_slot_data(self):
        slot = self.world.fill_slot_data()
        self.assertIs(slot["randomize_dialogue"], False)
        self.assertIs(slot["randomize_alignment"], False)


class TestRandomizersOn(KotorScenario):
    options = {"companion_mode": 0, "randomize_dialogue": True, "randomize_alignment": True}

    def test_both_are_on_in_slot_data(self):
        slot = self.world.fill_slot_data()
        self.assertIs(slot["randomize_dialogue"], True)
        self.assertIs(slot["randomize_alignment"], True)


class TestOnlyDialogue(KotorScenario):
    options = {"companion_mode": 0, "randomize_dialogue": True}

    def test_alignment_stays_off(self):
        slot = self.world.fill_slot_data()
        self.assertIs(slot["randomize_dialogue"], True)
        self.assertIs(slot["randomize_alignment"], False)
