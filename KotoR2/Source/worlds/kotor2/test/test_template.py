"""The player template (Docs/KotOR2_TEMPLATE.yaml, written by hand in the style of the KotOR 1 template) has to match the world: every option is in it, nothing
else is, every value is valid, and every value shown is the option's default (the template says so at the top)."""
import dataclasses
import os
import unittest

import yaml

from .. import KotorTwoWorld
from Options import PerGameCommonOptions

from ..Options import KotorTwoOptions


def own_fields():
    """The world's own options: the dataclass also holds the ones Archipelago adds to every world (start_inventory, local_items and the like)."""
    common = {f.name for f in dataclasses.fields(PerGameCommonOptions)}
    return {f.name: f.type for f in dataclasses.fields(KotorTwoOptions) if f.name not in common}


def find_template():
    """The development folder keeps it in docs/, the published repository in Docs/, both next to the Archipelago core (ap_core / work/Archipelago)."""
    core = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    for folder in ("docs", "Docs"):
        path = os.path.join(os.path.dirname(core), folder, "KotOR2_TEMPLATE.yaml")
        if os.path.isfile(path):
            return path
    return None


TEMPLATE = find_template()


@unittest.skipIf(TEMPLATE is None, "the template is not laid out next to the Archipelago core")
class TestTemplate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(TEMPLATE, encoding="utf-8") as f:
            cls.data = yaml.safe_load(f)
        cls.options = cls.data[KotorTwoWorld.game]

    def test_header(self):
        self.assertEqual(self.data["game"], KotorTwoWorld.game)
        self.assertIn(KotorTwoWorld.game, self.data)

    def test_every_option_is_listed_once_and_only_those(self):
        fields = set(own_fields())
        standard = {"progression_balancing", "accessibility"}      # Archipelago's own, added to every world
        listed = set(self.options)
        self.assertEqual(sorted(fields - listed), [], "options missing from the template")
        self.assertEqual(sorted(listed - fields - standard), [], "template lists options the world does not have")

    def test_values_are_valid_and_are_the_defaults(self):
        fields = own_fields()
        for name, value in self.options.items():
            if name not in fields:
                continue
            option = fields[name]
            shown = option.from_any(value)
            default = option.from_any(option.default) if hasattr(option, "from_any") else None
            self.assertEqual(shown.value, default.value, f"{name}: the template shows {value!r}, the default is {option.default!r}")

    def test_says_it_is_not_ready(self):
        with open(TEMPLATE, encoding="utf-8") as f:
            head = f.read(1500)
        self.assertIn("NOT READY TO PLAY", head)


if __name__ == "__main__":
    unittest.main()
