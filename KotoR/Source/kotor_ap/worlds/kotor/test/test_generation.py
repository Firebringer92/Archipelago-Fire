"""
Generation tests for the KotOR world: for each combination of the options that change which items or locations exist, a seed must
generate, every location must be reachable with all items, the seed must fill and be beatable, and the items the options promise must
be in the pool (or precollected) and end up placed. Further tests pin the access rules and the placement bans.

Run from the Archipelago folder:   python -m unittest worlds.kotor.test.test_generation
"""
import typing
import unittest

from BaseClasses import CollectionState, ItemClassification
from Fill import distribute_items_restrictive
from test.bases import WorldTestBase
from worlds.AutoWorld import call_all

from .. import Items
from ..Items import item_table
from ..Locations import location_table, SUNRY_CHAIN_LOCATIONS
from ..StoryGates import location_planet, ONE_WAY_PLANETS, token_forbidden_families

CLASS_ITEM_NAMES = {
    "Class Switch: Jedi Guardian", "Class Switch: Jedi Consular", "Class Switch: Jedi Sentinel",
    "PC Class: Soldier", "PC Class: Scout", "PC Class: Scoundrel", "PC Droid Conversion",
}
TOKEN_NAMES = [n for names in Items.STORY_TOKEN_NAMES.values() for n in names]
QUEST_ITEM_NAMES = sorted(n for n, d in location_table.items() if d.location_type == "quest_item")
BAZAAR_NAMES = sorted(n for n, d in location_table.items() if d.location_type in ("bazaar_purchase", "loot_exchange"))
FEATS_ITEMS = [f"Additional Feats Character: {k}" for k in ("Bastila", "Canderous", "Carth", "Jolee", "Juhani", "Mission", "Zaalbar")]


class KotorScenario(WorldTestBase):
    """One option combination. Subclasses set `options` and, where the options promise items, `expected_items`
    (names that must exist in the pool or precollected) and `forbidden_items` (names that must not exist)."""
    game = "KotOR"
    expected_items: typing.ClassVar[typing.Tuple[str, ...]] = ()
    forbidden_items: typing.ClassVar[typing.Tuple[str, ...]] = ()
    expected_counts: typing.ClassVar[typing.Dict[str, int]] = {}
    # a group of names of which exactly one must exist (starting_class=random_class rolls one of the six)
    expected_one_of: typing.ClassVar[typing.Tuple[typing.Tuple[str, ...], ...]] = ()
    expected_locations: typing.ClassVar[typing.Tuple[str, ...]] = ()
    forbidden_locations: typing.ClassVar[typing.Tuple[str, ...]] = ()

    def _all_item_names(self) -> typing.List[str]:
        names = [i.name for i in self.multiworld.itempool]
        names += [i.name for i in self.multiworld.precollected_items[self.player]]
        return names

    def _fill(self):
        distribute_items_restrictive(self.multiworld)
        call_all(self.multiworld, "post_fill")

    def test_promised_items_exist(self):
        if type(self) is KotorScenario:
            return
        names = self._all_item_names()
        for name in self.expected_items:
            with self.subTest("expected", item=name):
                self.assertIn(name, names)
        for name in self.forbidden_items:
            with self.subTest("forbidden", item=name):
                self.assertNotIn(name, names)
        for name, count in self.expected_counts.items():
            with self.subTest("count", item=name):
                self.assertEqual(names.count(name), count)
        for group in self.expected_one_of:
            with self.subTest("one of", group=group):
                self.assertEqual(sum(1 for n in names if n in group), 1)

    def test_promised_locations_exist(self):
        if type(self) is KotorScenario:
            return
        existing = {loc.name for loc in self.multiworld.get_locations(self.player)}
        for name in self.expected_locations:
            with self.subTest("expected location", location=name):
                self.assertIn(name, existing)
        for name in self.forbidden_locations:
            with self.subTest("forbidden location", location=name):
                self.assertNotIn(name, existing)

    def test_promised_items_are_placed(self):
        """After the fill, every item of the pool is on a location or precollected."""
        if type(self) is KotorScenario:
            return
        wanted = set(self.expected_items)
        for group in self.expected_one_of:
            wanted |= {n for n in self._all_item_names() if n in group}
        pre = {i.name for i in self.multiworld.precollected_items[self.player]}
        self._fill()
        placed = {loc.item.name for loc in self.multiworld.get_locations() if loc.item}
        for name in wanted:
            with self.subTest("placed", item=name):
                self.assertTrue(name in pre or name in placed, f"{name} is neither precollected nor placed")


class TestDefaults(KotorScenario):
    options = {}
    expected_locations = tuple(QUEST_ITEM_NAMES) + ("Companion Recruited: HK-47", "Ebon Hawk: HK-47")
    forbidden_locations = tuple(BAZAAR_NAMES) + ("Companion Recruited: New Companion",)


class TestProgressionSystem(KotorScenario):
    options = {"progression_system": 1}
    expected_items = tuple(TOKEN_NAMES)
    expected_counts = {"Taris Progression 1": 1, "Star Forge Progression 3": 1}


class TestGatedCompanions(KotorScenario):
    options = {"companion_mode": 0, "progression_system": 1}
    expected_items = tuple(n for n in item_table if n.startswith("Companion: "))


class TestNewCompanion(KotorScenario):
    """HK-47 stays; the replacement is a console choice, with one item to unlock the console."""
    options = {"companion_mode": 0, "new_companion": 1, "progression_system": 1}
    expected_items = ("Companion: HK-47", "Ebon Hawk: New Companion Selection")
    forbidden_items = ("Companion: New Companion", "Additional Feats Character: New Companion")
    expected_counts = {"Ebon Hawk: New Companion Selection": 1}
    expected_locations = ("Companion Recruited: HK-47", "Ebon Hawk: HK-47")
    forbidden_locations = ("Companion Recruited: New Companion",)


class TestNewCompanionRandomClass(KotorScenario):
    """random_class: the same console and item, and every console character is dealt a class for the seed."""
    options = {"companion_mode": 0, "new_companion": 2}
    expected_items = ("Ebon Hawk: New Companion Selection",)
    expected_counts = {"Ebon Hawk: New Companion Selection": 1}

    def test_every_character_is_dealt_a_class(self):
        data = self.world.fill_slot_data()
        self.assertEqual(data["new_companion"], 2)
        self.assertEqual(sorted(data["new_companion_classes"]), sorted(["meetra", "malak", "calo", "yuthura", "bandon", "trask"]))
        self.assertTrue(set(data["new_companion_classes"].values()) <= {"soldier", "scout", "scoundrel", "guardian", "consular", "sentinel"})

    def test_the_keys_are_the_consoles_characters(self):
        import os, sys
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "scripts")))
        import generate_new_companion_console as console
        self.assertEqual(set(self.world.fill_slot_data()["new_companion_classes"]), set(console.CHARACTERS))


class TestNewCompanionOnKeepsTheirOwnClass(KotorScenario):
    options = {"companion_mode": 0, "new_companion": 1}
    expected_items = ("Ebon Hawk: New Companion Selection",)

    def test_no_classes_are_dealt(self):
        self.assertEqual(self.world.fill_slot_data()["new_companion_classes"], {})


class TestNewCompanionRandomClassNoCompanions(KotorScenario):
    options = {"companion_mode": 2, "new_companion": 2}
    forbidden_items = ("Ebon Hawk: New Companion Selection",)

    def test_no_classes_are_dealt(self):
        self.assertEqual(self.world.fill_slot_data()["new_companion_classes"], {})


class TestNewCompanionRandomClassDroids(KotorScenario):
    options = {"companion_mode": 0, "new_companion": 2, "companion_class": 4}
    forbidden_items = ("Ebon Hawk: New Companion Selection",)

    def test_no_classes_are_dealt(self):
        data = self.world.fill_slot_data()
        self.assertEqual((data["new_companion"], data["new_companion_classes"]), (0, {}))


class TestNewCompanionOff(KotorScenario):
    options = {"companion_mode": 0, "new_companion": 0}
    forbidden_items = ("Ebon Hawk: New Companion Selection",)


class TestNewCompanionNoCompanions(KotorScenario):
    options = {"companion_mode": 2, "new_companion": 1}
    forbidden_items = ("Ebon Hawk: New Companion Selection", "Party Console")


class TestNewCompanionDroids(KotorScenario):
    options = {"companion_mode": 0, "new_companion": 1, "companion_class": 4}
    forbidden_items = ("Ebon Hawk: New Companion Selection",)


class TestPartyConsole(KotorScenario):
    """Always placed when companions exist, whatever the options."""
    options = {}
    expected_items = ("Party Console",)
    expected_counts = {"Party Console": 1}


class TestPartyConsoleLimitedCompanions(KotorScenario):
    options = {"companion_mode": 3}
    expected_counts = {"Party Console": 1}


class TestLimitedCompanions(KotorScenario):
    options = {"companion_mode": 3}


class TestNoCompanions(KotorScenario):
    options = {"companion_mode": 2}
    forbidden_locations = tuple(SUNRY_CHAIN_LOCATIONS)


class TestJediStart(KotorScenario):
    options = {"starting_class": 1, "jedi_class": 1}
    expected_items = ("Class Switch: Jedi Consular",)


class TestJediGranted(KotorScenario):
    options = {"starting_class": 2, "jedi_class": 2, "progression_system": 1}
    expected_items = ("Class Switch: Jedi Sentinel",)


class TestRandomClass(KotorScenario):
    options = {"starting_class": 3}
    expected_one_of = (tuple(sorted(CLASS_ITEM_NAMES - {"PC Droid Conversion"})),)


class TestDroid(KotorScenario):
    options = {"starting_class": 4}
    expected_items = ("PC Droid Conversion",)


class TestJediCompanions(KotorScenario):
    options = {"companion_class": 2, "companion_mode": 0, "progression_system": 1}

    def test_each_companion_gets_exactly_one_training_item(self):
        names = self._all_item_names()
        for key in ("carth", "canderous", "zaalbar", "mission"):
            with self.subTest(companion=key):
                self.assertEqual(sum(1 for n in names if n.startswith(f"Jedi Training: {key.capitalize()} (")), 1)


class TestRandomizedCompanionClasses(KotorScenario):
    options = {"companion_class": 3}


class TestAdditionalFeats(KotorScenario):
    """One unlock per non-droid companion; none for the player character, none for a replacement."""
    options = {"additional_feats": 1}
    expected_items = tuple(FEATS_ITEMS)
    forbidden_items = ("Additional Feats Character: PC", "Additional Feats Character: New Companion")

    def test_the_unlocks_deliver_plot_items(self):
        for name in FEATS_ITEMS:
            with self.subTest(item=name):
                self.assertTrue(item_table[name].arm_name.startswith("give_item:ap_ft_"))


class TestAdditionalFeatsNoCompanions(KotorScenario):
    options = {"additional_feats": 1, "companion_mode": 2}
    forbidden_items = tuple(FEATS_ITEMS) + ("Additional Feats Character: PC",)


class TestVendorAndTraps(KotorScenario):
    options = {"archipelago_vendor": 1, "enable_traps": 2, "progression_system": 1}
    expected_items = ("Vendor Pass: Skill Training", "Vendor Pass: Feat Training")


class TestQuestItemChecksOff(KotorScenario):
    options = {"quest_item_checks": 0}
    forbidden_locations = tuple(QUEST_ITEM_NAMES)


class TestBazaar(KotorScenario):
    options = {"bazaar": 1, "progression_system": 1}
    expected_locations = tuple(BAZAAR_NAMES)

    def test_25_bazaar_checks(self):
        self.assertEqual(len(BAZAAR_NAMES), 25)

    def test_they_hold_no_progression(self):
        self._fill()
        for name in BAZAAR_NAMES:
            with self.subTest(location=name):
                self.assertFalse(self.multiworld.get_location(name, self.player).item.advancement)




class TestEverythingOn(KotorScenario):
    options = {
        "progression_system": 1, "companion_mode": 0, "companion_class": 2, "starting_class": 2, "additional_feats": 1,
        "archipelago_vendor": 1, "enable_traps": 2, "experience_mode": 2, "credit_mode": 2, "receive_inventory_items": 1,
        "new_companion": 1, "bazaar": 1, "quest_item_checks": 1,
    }


class TestGoals(KotorScenario):
    options = {"goal": 3, "progression_system": 1}


class TestAreaRandomizer(KotorScenario):
    options = {"area_randomizer": 1, "progression_system": 1}


class TestSlotData(KotorScenario):
    options = {"bazaar": 1}

    def test_new_options_reach_the_client(self):
        data = self.world.fill_slot_data()
        for key, want in (("bazaar", True), ("quest_item_checks", True), ("new_companion", 0)):
            with self.subTest(key=key):
                self.assertEqual(data[key], want)


class TestClassification(KotorScenario):
    """What the progression label is for: only the items a rule reads, and the goal markers, are progression. Written down
    so that a change to a label is a decision, not an accident."""
    options = {}

    @staticmethod
    def _label(name):
        c = item_table[name].classification
        return ("progression" if c & ItemClassification.progression else "trap" if c & ItemClassification.trap
                else "useful" if c & ItemClassification.useful else "filler")

    def test_rule_items_are_progression(self):
        for name in item_table:
            if name.startswith("Companion: ") or name in TOKEN_NAMES:
                with self.subTest(item=name):
                    self.assertEqual(self._label(name), "progression")

    def test_items_that_gate_nothing_are_useful(self):
        for name in item_table:
            if name.startswith(("Class Switch: ", "Jedi Training: ", "PC Class: ")) or name in (
                    "PC Droid Conversion", "Party Console", "Ebon Hawk: New Companion Selection") or name in FEATS_ITEMS:
                with self.subTest(item=name):
                    self.assertEqual(self._label(name), "useful")

    def test_skills_and_abilities_are_filler(self):
        for name in item_table:
            if name.startswith(("Skill: ", "Ability: ")):
                with self.subTest(item=name):
                    self.assertEqual(self._label(name), "filler")

    def test_removed_items_are_gone(self):
        for name in ("Companion: New Companion", "Additional Feats Character: PC", "Additional Feats Character: New Companion"):
            with self.subTest(item=name):
                self.assertNotIn(name, item_table)
        self.assertEqual([n for n in item_table if n.startswith("Progression Item:")], [])

    def test_progression_set_is_exactly_what_the_rules_need(self):
        progression = {n for n in item_table if self._label(n) == "progression"}
        companions = {n for n in item_table if n.startswith("Companion: ")}
        markers = {"Reached Level 20", "Malak Defeated", "Reached Dark Side 0", "Reached Light Side 100", "Reached Leviathan"}
        self.assertEqual(progression, set(TOKEN_NAMES) | companions | markers)


class TestAccessRules(KotorScenario):
    """The 0.2.0 requirements, each traced in the game files (FutureDesign.md). Everything starts from the open-world
    baseline B = Taris 3 and Dantooine 3."""
    options = {"progression_system": 1, "companion_mode": 1}

    B = ["Taris Progression 1", "Taris Progression 2", "Taris Progression 3",
         "Dantooine Progression 1", "Dantooine Progression 2", "Dantooine Progression 3"]
    MAPS = ["Tatooine Progression 1", "Tatooine Progression 2", "Tatooine Progression 3",
            "Kashyyyk Progression 1", "Kashyyyk Progression 2", "Kashyyyk Progression 3",
            "Manaan Progression 1", "Manaan Progression 2", "Manaan Progression 3",
            "Korriban Progression 1", "Korriban Progression 2", "Korriban Progression 3"]

    def _reach(self, location, tokens):
        state = CollectionState(self.multiworld)
        for item in self.multiworld.get_items():
            if item.name in tokens:
                state.collect(item)
        return self.multiworld.get_location(location, self.player).can_reach(state)

    def _needs(self, location, base, extra):
        """Not reachable with `base`, reachable with `base` plus `extra`."""
        with self.subTest(location=location):
            self.assertFalse(self._reach(location, base), f"{location} reachable without {extra}")
            self.assertTrue(self._reach(location, base + extra), f"{location} unreachable with {extra}")

    def test_manaan_needs_the_roland_route(self):
        man1 = ["Manaan Progression 1"]
        for loc in ("Visited: Manaan - Sith Base", "Manaan: Republic Embassy", "Quest Item: Data Module - Manaan Sith Base"):
            self._needs(loc, self.B, man1)
        # the submarine card (W_REPKEY2) comes at Roland's debrief, so the kolto facility and the Rift need the second Manaan item
        for loc in ("Visited: Manaan - Hrakert Station", "Visited: Manaan - Sea Floor", "Visited: Manaan - Kolto Control",
                    "Visited: Manaan - Hrakert Rift", "Manaan: Republic Hiring Mercenaries", "Quest Item: Environment Suit - Kolto Control"):
            self._needs(loc, self.B + man1, ["Manaan Progression 2"])

    def test_kashyyyk_lower_shadowlands_needs_jolee(self):
        for loc in ("Visited: Kashyyyk - Lower Shadowlands", "Kashyyyk: Hidden Hunters", "Quest Item: Bacca's Sword Blade - Lower Shadowlands"):
            self._needs(loc, self.B, ["Kashyyyk Progression 1"])

    def test_sunry_chain_needs_jolee(self):
        for loc in SUNRY_CHAIN_LOCATIONS:
            self._needs(loc, self.B + ["Manaan Progression 1", "Manaan Progression 2"], ["Kashyyyk Progression 1"])

    GENOHARADAN = ("Genoharadan: Ithorak", "Genoharadan: Lorgal", "Genoharadan: Rulan", "Genoharadan: Vorn", "Genoharadan: Zuulan", "Genoharadan")
    TAT3 = ["Tatooine Progression 1", "Tatooine Progression 2", "Tatooine Progression 3"]
    KAS2 = ["Kashyyyk Progression 1", "Kashyyyk Progression 2"]
    KOR3 = ["Korriban Progression 1", "Korriban Progression 2", "Korriban Progression 3"]
    MAN3 = ["Manaan Progression 1", "Manaan Progression 2", "Manaan Progression 3"]

    def test_the_genoharadan_line_needs_the_baseline_and_any_one_start(self):
        """Senni Vek appears once Tatooine's (3), Kashyyyk's (2) or Korriban's (3) star map is done; the Manaan map does not count."""
        for loc in self.GENOHARADAN:
            with self.subTest(location=loc):
                self.assertFalse(self._reach(loc, self.B), "reachable with the baseline alone")
                self.assertFalse(self._reach(loc, self.B + self.MAN3), "the Manaan items must not start the line")
                self.assertFalse(self._reach(loc, self.B + ["Kashyyyk Progression 1"] + self.TAT3[:2] + self.KOR3[:2]), "one short of every start")
                self.assertFalse(self._reach(loc, self.TAT3 + self.KAS2 + self.KOR3), "a start without the baseline")
                for start in (self.TAT3, self.KAS2, self.KOR3):
                    self.assertTrue(self._reach(loc, self.B + start), f"unreachable with the baseline and {start}")

    def test_the_genoharadan_finale_no_longer_needs_every_star_map(self):
        self.assertTrue(self._reach("Genoharadan", self.B + self.KAS2))
        self.assertTrue(self._reach("Genoharadan: Zuulan", self.B + self.TAT3))

    def test_premium_merchant_needs_the_leviathan(self):
        self._needs("General: Premium Merchant", self.B, self.MAPS)

    def test_quest_items_by_planet(self):
        self._needs("Quest Item: Shield Codes - Taris Sith Base", [], ["Taris Progression 1", "Taris Progression 2"])
        for loc in ("Quest Item: Sand People Clothing - Tatooine Dune Sea", "Quest Item: Map of the Eastern Dune Sea - Sand People Enclave", "Quest Item: Bantha Fodder - Tatooine Docking Bay"):
            self._needs(loc, self.B, ["Tatooine Progression 1"])
        for loc in ("Quest Item: Sith Medallion - Korriban Dreshdae", "Quest Item: Ajunta Pall's Blade - Tomb of Ajunta Pall", "Quest Item: Ancient Sith Tablet - Tomb of Tulak Hord"):
            self._needs(loc, self.B, ["Korriban Progression 1"])
        for loc in ("Quest Item: Sith Armor - Taris North Apartments", "Quest Item: Sith Papers - Taris Hidden Bek Base", "Quest Item: Rakghoul Serum - Taris Undercity"):
            with self.subTest(location=loc):
                self.assertTrue(self._reach(loc, []))

    def test_loot_exchange_has_no_extra_requirement(self):
        names = {l.name for l in self.multiworld.get_locations(self.player)}
        for k in range(1, 21):
            loc = f"Bazaar Token Exchange {k}"
            if loc in names:
                with self.subTest(location=loc):
                    self.assertTrue(self._reach(loc, self.B))


class TestAccessRulesWithBazaar(TestAccessRules):
    options = {"progression_system": 1, "companion_mode": 1, "bazaar": 1}


class TestTokenBans(KotorScenario):
    """Which token families may sit where (the item rules), read straight from the rule functions."""
    options = {"progression_system": 1}

    def _banned(self, name):
        return token_forbidden_families(name, location_table[name])

    def test_taris_and_the_endar_spire_take_any_token(self):
        for name, data in location_table.items():
            if location_planet(name, data) in ("Taris", "Endar Spire") and name != "Quest Item: Shield Codes - Taris Sith Base":
                with self.subTest(location=name):
                    self.assertEqual(self._banned(name), set())

    def test_shield_codes_take_taris_tokens_only(self):
        self.assertEqual(self._banned("Quest Item: Shield Codes - Taris Sith Base"), set(Items.STORY_TOKEN_NAMES) - {"tar"})

    def test_the_late_game_takes_no_token(self):
        for name, data in location_table.items():
            if location_planet(name, data) in ONE_WAY_PLANETS:
                with self.subTest(location=name):
                    self.assertEqual(self._banned(name), set(Items.STORY_TOKEN_NAMES))

    def test_an_open_world_planets_own_tokens_stay_off_it(self):
        self.assertIn("tat", self._banned("Quest Item: Bantha Fodder - Tatooine Docking Bay"))
        self.assertIn("kor", self._banned("Quest Item: Ajunta Pall's Blade - Tomb of Ajunta Pall"))
        self.assertIn("kas", self._banned("Quest Item: Bacca's Sword Blade - Lower Shadowlands"))
        self.assertIn("man", self._banned("Quest Item: Data Module - Manaan Sith Base"))


class TestPlacementBans(KotorScenario):
    """After the fill, over several seeds: no progression item where it is barred, and the bans leave a seed beatable."""
    options = {"progression_system": 1, "companion_mode": 0, "bazaar": 1, "additional_feats": 1}

    def _barred(self):
        barred = {}
        for name, data in location_table.items():
            planet = location_planet(name, data)
            if planet in ONE_WAY_PLANETS:
                barred[name] = "late game"
            elif (data.location_type == "journal" and data.region == "Ebon Hawk") or name in SUNRY_CHAIN_LOCATIONS:
                barred[name] = "Ebon Hawk quest or Sunry chain"
            elif data.location_type in ("alignment", "alignment_bonus", "level", "bounty", "datapad") and name != "Boss: Calo Nord":
                barred[name] = "never progression by type"
        return barred

    def test_no_progression_on_barred_checks(self):
        barred = self._barred()
        for seed in range(1, 9):
            self.world_setup(seed)
            self._fill()
            for loc in self.multiworld.get_locations(self.player):
                if loc.name in barred and loc.item is not None and not loc.locked:
                    with self.subTest(seed=seed, location=loc.name):
                        self.assertFalse(loc.item.advancement, f"{loc.item.name} on {loc.name} ({barred[loc.name]})")

    def test_shield_codes_hold_only_taris_tokens(self):
        taris = set(Items.STORY_TOKEN_NAMES["tar"])
        for seed in range(1, 9):
            self.world_setup(seed)
            self._fill()
            item = self.multiworld.get_location("Quest Item: Shield Codes - Taris Sith Base", self.player).item
            with self.subTest(seed=seed):
                if item is not None and item.name in TOKEN_NAMES:
                    self.assertIn(item.name, taris)

    def test_bazaar_checks_hold_no_progression(self):
        for seed in range(1, 9):
            self.world_setup(seed)
            self._fill()
            for name in BAZAAR_NAMES:
                with self.subTest(seed=seed, location=name):
                    self.assertFalse(self.multiworld.get_location(name, self.player).item.advancement)

    def test_taris_tokens_can_now_be_placed_on_taris(self):
        """With the Taris ban lifted, a seed may put another planet's tokens on Taris; the sweep over seeds must find at least one."""
        found = False
        for seed in range(1, 25):
            self.world_setup(seed)
            self._fill()
            for loc in self.multiworld.get_locations(self.player):
                if loc.item and loc.item.name in TOKEN_NAMES and location_planet(loc.name, location_table[loc.name]) == "Taris" \
                        and not loc.item.name.startswith("Taris"):
                    found = True
        self.assertTrue(found, "no other family's token landed on Taris in 24 seeds")


class TestCalo(KotorScenario):
    options = {"progression_system": 1}

    def test_calo_may_hold_progression_with_the_area_randomizer_off(self):
        rules_ok = False
        for seed in range(1, 40):
            self.world_setup(seed)
            self._fill()
            item = self.multiworld.get_location("Boss: Calo Nord", self.player).item
            if item is not None and item.advancement:
                rules_ok = True
                break
        self.assertTrue(rules_ok, "Calo Nord never held a progression item in 39 seeds")

    def test_calo_needs_the_baseline(self):
        state = CollectionState(self.multiworld)
        loc = self.multiworld.get_location("Boss: Calo Nord", self.player)
        self.assertFalse(loc.can_reach(state))
        for item in self.multiworld.get_items():
            if item.name in ("Taris Progression 1", "Taris Progression 2", "Taris Progression 3",
                             "Dantooine Progression 1", "Dantooine Progression 2", "Dantooine Progression 3"):
                state.collect(item)
        self.assertTrue(loc.can_reach(state))


class TestCaloWithAreaRandomizer(KotorScenario):
    options = {"progression_system": 1, "area_randomizer": 1}

    def test_calo_stays_barred(self):
        for seed in range(1, 10):
            self.world_setup(seed)
            self._fill()
            item = self.multiworld.get_location("Boss: Calo Nord", self.player).item
            with self.subTest(seed=seed):
                self.assertFalse(item is not None and item.advancement)


class TestBountyCards(unittest.TestCase):
    """Forty cards: 38 modules carry one bounty carrier, two reachable modules carry a second."""

    def test_40_bounty_cards(self):
        values = sorted(d.bounty_value for d in location_table.values() if d.location_type == "bounty")
        self.assertEqual(values, list(range(1, 41)))


class _DroidShopCases:
    """Shared checks for the shop stock in a seed with a droid option."""
    DROID_PARTS = {"Droid_Computer_Spike_Mount_x", "Droid_Heavy_Plating", "Droid_Shield", "Droid_Utility_Device", "Droid_Light_Plating", "Droid_Medium_Plating",
                   "Droid_Motion_Sensors_x", "Droid_Security_Spike_Mount", "Droid_Sonic_Sensors_x", "Droid_Search_Scope_x", "Droid_Targeting_Computers"}
    WANT = 0

    def _stock(self):
        return self.world.fill_slot_data()["shop_stock"]

    def _types(self, shop):
        from .. import read_gear_json
        gear = read_gear_json()
        return [gear[r]["base_item_type"] for r in shop]

    def test_every_shop_has_the_full_count_and_no_repeats(self):
        for planet, shop in self._stock().items():
            with self.subTest(planet=planet):
                self.assertEqual(len(shop), self.world.options.shop_item_count.value)
                self.assertEqual(len(shop), len(set(shop)))

    def test_every_shop_has_all_three_repair_kits(self):
        from .. import DROID_REPAIR_KITS
        for planet, shop in self._stock().items():
            with self.subTest(planet=planet):
                self.assertTrue(set(DROID_REPAIR_KITS) <= set(shop))

    def test_every_shop_has_its_share_of_droid_parts_with_every_group(self):
        from .. import DROID_PART_GROUPS
        for planet, shop in self._stock().items():
            types = self._types(shop)
            with self.subTest(planet=planet):
                self.assertGreaterEqual(sum(t in self.DROID_PARTS for t in types), self.WANT)
                for group, group_types in DROID_PART_GROUPS.items():
                    self.assertTrue(any(t in group_types for t in types), f"no {group} in the {planet} shop")


class TestShopsBothDroid(_DroidShopCases, KotorScenario):
    options = {"starting_class": 4, "companion_class": 4, "shop_randomizer": 1}
    WANT = 12

    def test_everything_in_a_shop_is_usable_by_a_droid(self):
        from .. import _is_droid_gear, read_gear_json
        gear = read_gear_json()
        for planet, shop in self._stock().items():
            with self.subTest(planet=planet):
                self.assertTrue(all(_is_droid_gear(gear[r]) for r in shop))


class TestShopsOneDroid(_DroidShopCases, KotorScenario):
    options = {"starting_class": 4, "shop_randomizer": 1}
    WANT = 8

    def test_part_of_the_shop_is_still_gear_for_a_human(self):
        from .. import _is_droid_gear, read_gear_json
        gear = read_gear_json()
        for planet, shop in self._stock().items():
            with self.subTest(planet=planet):
                self.assertTrue(any(not _is_droid_gear(gear[r]) for r in shop))


class TestFillerTrapCap(KotorScenario):
    """Traps=item_filler never puts more than MAX_FILLER_TRAPS traps in the pool, even when traps are the only thing the weights allow."""
    options = {"enable_traps": 1, "item_distribution_type": 1, "trap_weight": 100, "weapon_weight": 0, "armor_weight": 0, "consumable_weight": 0,
               "exp_weight": 0, "credit_weight": 0, "skill_weight": 0, "ability_weight": 0}

    def test_no_more_than_the_cap(self):
        from .. import MAX_FILLER_TRAPS, TRAP_ITEMS
        traps = [n for n in self._all_item_names() if n in TRAP_ITEMS]
        self.assertEqual(len(traps), MAX_FILLER_TRAPS)
        self.assertEqual(MAX_FILLER_TRAPS, 36)
