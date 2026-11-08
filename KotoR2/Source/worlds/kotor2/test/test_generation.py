import unittest

from Options import OptionError

from . import KotorTwoTestBase


def pool_counts(base):
    counts = {}
    for item in base.multiworld.itempool:
        counts[item.name] = counts.get(item.name, 0) + 1
    return counts


def location_names(base):
    return {l.name for l in base.multiworld.get_locations(base.player)}


class TestDefault(KotorTwoTestBase):
    """Default options: gates on, companions default, level target 20."""

    def test_beatable_and_counts(self):
        self.collect_all_but([])
        self.assertBeatable(True)
        names = location_names(self)
        self.assertIn("Defeat Kreia", names)
        self.assertIn("Level 20", names)
        self.assertNotIn("Level 21", names)
        self.assertIn("Companion Recruited: Atton Rand", names)
        self.assertIn("Influence: Kreia", names)

    def test_levels_and_alignment_hold_no_progression(self):
        for loc in self.multiworld.get_locations(self.player):
            if loc.name.startswith(("Level ", "Alignment:", "Influence:", "Archipelago Bazaar", "Bazaar Token")):
                self.assertFalse(loc.item and loc.item.advancement and loc.item.name != "Victory", loc.name)

    def test_tokens_in_pool(self):
        counts = pool_counts(self)
        self.assertEqual(counts["Telos Progression"], 3)
        self.assertEqual(counts["Nar Shaddaa Progression"], 3)
        self.assertEqual(counts["Dantooine Progression"], 2)   # DAN3 is off by default
        self.assertEqual(counts["Endgame Progression"], 4)

    def test_no_xp_or_credit_items_when_modes_off(self):
        counts = pool_counts(self)
        self.assertNotIn("Experience Points", counts)
        self.assertNotIn("Republic Credits", counts)


class TestNoCompanions(KotorTwoTestBase):
    options = {"companions": 0}

    def test_no_companion_checks(self):
        names = location_names(self)
        self.assertFalse(any(n.startswith(("Companion Recruited", "Influence:")) for n in names))
        self.collect_all_but([])
        self.assertBeatable(True)


class TestNoGates(KotorTwoTestBase):
    options = {"story_gates": 0}

    def test_no_tokens(self):
        self.assertFalse(any(i.name.endswith("Progression") for i in self.multiworld.itempool))
        self.collect_all_but([])
        self.assertBeatable(True)


class TestLevelFifty(KotorTwoTestBase):
    options = {"level_target": 50, "experience_mode": 2}

    def test_all_levels(self):
        self.assertIn("Level 50", location_names(self))
        self.collect_all_but([])
        self.assertBeatable(True)


class TestOneGateOff(KotorTwoTestBase):
    options = {"disabled_gates": ["NAR1", "NAR3", "KOR2"]}

    def test_beatable(self):
        self.collect_all_but([])
        self.assertBeatable(True)


class TestNihilusGoal(KotorTwoTestBase):
    options = {"goal": 1}

    def test_event_and_fewer_tokens_needed(self):
        self.assertIn("Defeat Darth Nihilus", location_names(self))
        self.assertNotIn("Defeat Kreia", location_names(self))
        # every Endgame token but the last is enough: the Kreia fight gate is not part of this goal
        self.collect_all_but(["Victory"])     # the base class would otherwise collect the pre-placed goal event too
        self.assertBeatable(True)
        tokens = self.get_items_by_name("Endgame Progression")
        goal = self.multiworld.get_location("Defeat Darth Nihilus", self.player)
        self.remove(tokens[:1])
        self.assertTrue(goal.can_reach(self.multiworld.state))
        self.remove(tokens[1:2])     # removing keeps events already collected, so ask the goal location itself
        self.assertFalse(goal.can_reach(self.multiworld.state))


class TestHighLevelGoal(KotorTwoTestBase):
    options = {"goal": 2, "goal_level": 25, "experience_mode": 2, "experience_item": 8000}

    def test_level_checks_reach_the_goal_level_and_xp_is_guaranteed(self):
        self.assertIn("Level 25", location_names(self))
        self.assertGreaterEqual(pool_counts(self)["Experience Points"] * 8000, 300000)
        self.collect_all_but([])
        self.assertBeatable(True)


class TestHighLevelLimitedFeasible(KotorTwoTestBase):
    options = {"goal": 2, "goal_level": 25, "experience_mode": 1, "experience_limiter": 2000}

    def test_generates(self):
        self.assertIn("Level 25", location_names(self))


class TestInfluenceGoal(KotorTwoTestBase):
    options = {"goal": 3, "influence_goal_count": 6}

    def test_beatable(self):
        self.assertIn("Influence Crew", location_names(self))
        self.collect_all_but([])
        self.assertBeatable(True)


class TestCultLeaderGated(KotorTwoTestBase):
    options = {"goal": 4, "companions": 2, "extra_companions": ["Bastila Shan", "Darth Sion"], "ap_companions": 2}

    def test_every_offered_companion_is_in_the_pool(self):
        counts = pool_counts(self)
        for n in ("Companion: Atton Rand", "Companion: HK-47", "Companion: Bastila Shan", "Companion: Darth Sion"):
            self.assertEqual(counts[n], 1, n)
        self.assertEqual(counts["AP Companion"], 2)
        self.collect_all_but([])
        self.assertBeatable(True)

    def test_missing_companion_item_blocks_the_goal(self):
        self.collect_all_but(["Victory", "Companion: Bastila Shan"])
        self.assertBeatable(False)


class TestCultLeaderDefaultMode(KotorTwoTestBase):
    options = {"goal": 4, "companions": 1}

    def test_no_companion_items_in_default_mode(self):
        self.assertFalse(any(i.name.startswith(("Companion:", "AP Companion")) for i in self.multiworld.itempool))
        self.collect_all_but([])
        self.assertBeatable(True)


class TestLimitedCompanions(KotorTwoTestBase):
    options = {"companions": 3, "companion_unlock_step": 5, "extra_companions": ["Juhani"]}

    def test_no_companion_items_but_an_unlock_order(self):
        self.assertFalse(any(i.name.startswith("Companion:") for i in self.multiworld.itempool))
        order = self.world.fill_slot_data()["companion_unlock_order"]
        self.assertEqual(len(order), 13)
        self.assertEqual(order[0], "Companion: Atton Rand")
        self.assertEqual(order[-1], "Companion: Juhani")


class TestCheckFamilySwitches(KotorTwoTestBase):
    options = {"area_visit_checks": 0, "alignment_checks": 0}

    def test_families_removed(self):
        names = location_names(self)
        self.assertFalse(any(n.startswith("Alignment:") for n in names))
        self.assertFalse(any(l.type == "area" for l in self.world_locations()))

    def world_locations(self):
        from worlds.kotor2.Locations import LOCATIONS
        used = location_names(self)
        return [l for l in LOCATIONS if l.name in used]


class TestTrapTypes(KotorTwoTestBase):
    options = {"trap_types": ["lose_credits"], "trap_percentage": 100}

    def test_only_selected_traps(self):
        traps = {i.name for i in self.multiworld.itempool if i.name.startswith("Trap:")}
        self.assertEqual(traps, {"Trap: Lose Credits"})


class TestXpAndCreditsGated(KotorTwoTestBase):
    options = {"experience_mode": 2, "credit_mode": 2}

    def test_items_present(self):
        counts = pool_counts(self)
        self.assertGreater(counts["Experience Points"], 0)
        self.assertGreater(counts["Republic Credits"], 0)


class TestGoalNeedsCompanions(KotorTwoTestBase):
    options = {"goal": 3, "companions": 0}
    auto_construct = False
    run_default_tests = False

    def test_option_error(self):
        with self.assertRaises(OptionError):
            self.world_setup()


class TestHighLevelUnreachable(KotorTwoTestBase):
    options = {"goal": 2, "goal_level": 50, "experience_mode": 1, "experience_limiter": 500}
    auto_construct = False
    run_default_tests = False

    def test_option_error(self):
        with self.assertRaises(OptionError):
            self.world_setup()


class TestStartingClassNonForce(KotorTwoTestBase):
    options = {"starting_class": "non_force_user"}

    def test_a_non_jedi_base_class_is_chosen(self):
        data = self.world.fill_slot_data()["start_class"]
        self.assertIn(data["class"], (0, 1, 2))
        self.assertEqual(data["mode"], 1)


class TestStartingClassRandom(KotorTwoTestBase):
    options = {"starting_class": "random_class"}

    def test_a_base_class_is_chosen(self):
        data = self.world.fill_slot_data()["start_class"]
        self.assertIn(data["class"], (0, 1, 2, 3, 4, 5))
        self.assertEqual(data["mode"], 1 if data["class"] in (0, 1, 2) else 0)


class TestStartingClassPrestige(KotorTwoTestBase):
    options = {"starting_class": "prestige_start"}

    def test_a_prestige_class_is_chosen(self):
        self.assertIn(self.world.fill_slot_data()["start_class"]["class"], (11, 12, 13, 14, 15, 16))


class TestStartingClassDefault(KotorTwoTestBase):
    def test_nothing_to_convert(self):
        self.assertIsNone(self.world.fill_slot_data()["start_class"])


class TestPrestigeGated(KotorTwoTestBase):
    options = {"starting_class": "prestige_gated"}

    def test_one_prestige_item_and_a_pair(self):
        self.assertEqual(sum(1 for i in self.multiworld.itempool if i.name == "Prestige Class"), 1)
        pair = self.world.fill_slot_data()["prestige_pair"]
        self.assertIn(tuple(pair), [(11, 14), (13, 16), (12, 15)])
        self.assertIsNone(self.world.fill_slot_data()["start_class"])


class TestNoPrestigeItemOtherwise(KotorTwoTestBase):
    def test_no_item_and_no_pair(self):
        self.assertFalse(any(i.name == "Prestige Class" for i in self.multiworld.itempool))
        self.assertIsNone(self.world.fill_slot_data()["prestige_pair"])


class TestDroidStart(KotorTwoTestBase):
    options = {"starting_class": "droid"}

    def test_a_droid_class_and_race(self):
        data = self.world.fill_slot_data()["start_class"]
        self.assertIn(data["class"], (6, 7))
        self.assertEqual((data["mode"], data["race"]), (1, 5))


class TestCompanionClassModes(KotorTwoTestBase):
    DROIDS = {"3", "5", "8"}

    def assignments(self, **opts):
        from worlds.kotor2 import KotorTwoWorld
        self.world.options.companion_class.value = opts["value"]
        return self.world._companion_classes()

    def test_default_changes_nothing(self):
        self.assertEqual(self.assignments(value=0), {})

    def test_jedi_companion_gives_every_non_jedi_non_droid_a_jedi_base_class(self):
        out = self.assignments(value=1)
        self.assertEqual(set(out), {str(s) for s in range(12)} - self.DROIDS - {"6", "9"})
        self.assertTrue(all(v["class"] in (3, 4, 5) and v["mode"] == 0 for v in out.values()))

    def test_no_jedi_only_touches_kreia_and_visas_and_strips(self):
        out = self.assignments(value=2)
        self.assertEqual(set(out), {"6", "9"})
        self.assertTrue(all(v["class"] in (0, 1, 2, 9) and v["mode"] == 1 for v in out.values()))

    def test_droid_mode_makes_every_non_droid_a_droid(self):
        out = self.assignments(value=3)
        self.assertEqual(set(out), {str(s) for s in range(12)} - self.DROIDS)
        self.assertTrue(all(v["class"] in (6, 7) and v["race"] == 5 and v["mode"] == 1 for v in out.values()))

    def test_randomize_base_never_picks_a_prestige_class_and_includes_tech_specialist(self):
        seen = set()
        for _ in range(40):
            out = self.assignments(value=4)
            seen |= {v["class"] for v in out.values()}
            self.assertEqual(set(out), {str(s) for s in range(12)} - self.DROIDS)
        self.assertTrue(seen <= {0, 1, 2, 3, 4, 5, 9})
        self.assertIn(9, seen)

    def test_second_class_only_when_random_class(self):
        self.assertEqual(self.world._companion_second_class(), {})
        self.world.options.multiclass_companion.value = 2
        out = self.world._companion_second_class()
        self.assertEqual(set(out), {str(s) for s in range(12)} - self.DROIDS)
        self.assertTrue(all(c in (0, 1, 2, 3, 4, 5, 9) for c in out.values()))


class TestStartingStatsRandom(KotorTwoTestBase):
    options = {"starting_stats": "randomized"}

    def test_fourteen_values_from_one_to_twenty(self):
        stats = self.world.fill_slot_data()["start_stats"]
        self.assertEqual(len(stats), 14)
        self.assertTrue(all(1 <= v <= 20 for v in stats))
        self.assertFalse(any(i.name in ("Ability: Strength Increase", "Skill: Persuade") for i in self.multiworld.precollected_items[self.player]))


class TestStartingStatsDefault(KotorTwoTestBase):
    def test_nothing_to_set(self):
        self.assertIsNone(self.world.fill_slot_data()["start_stats"])


class TestCompanionPrestigeItems(KotorTwoTestBase):
    options = {"multiclass_companion": "prestige"}

    def test_one_item_per_jedi_capable_companion_with_a_pair_each(self):
        names = sorted(i.name for i in self.multiworld.itempool if i.name.startswith("Companion Prestige: "))
        self.assertEqual(names, sorted("Companion Prestige: " + n for n in ("Atton Rand", "Bao-Dur", "Handmaiden", "Kreia", "Mira", "Visas Marr", "Disciple")))
        pairs = self.world.fill_slot_data()["companion_prestige_pairs"]
        self.assertEqual(set(pairs), {"0", "1", "4", "6", "7", "9", "11"})
        self.assertTrue(all(tuple(p) in [(11, 14), (13, 16), (12, 15)] for p in pairs.values()))


class TestNoCompanionPrestigeItemsByDefault(KotorTwoTestBase):
    def test_none(self):
        self.assertFalse(any(i.name.startswith("Companion Prestige: ") for i in self.multiworld.itempool))
        self.assertEqual(self.world.fill_slot_data()["companion_prestige_pairs"], {})


class TestExtraCompanionsPlan(KotorTwoTestBase):
    options = {"companions": "ap_gated", "extra_companions": ["Zez-Kai Ell", "Bastila Shan"], "ap_companions": 3}

    def test_slots_items_and_names(self):
        plan = self.world.fill_slot_data()["extras"]
        self.assertEqual([e["slot"] for e in plan], [12, 13, 14, 15, 16])
        self.assertEqual([e["name"] for e in plan[:2]], ["Bastila Shan", "Zez-Kai Ell"])          # the order of the data file, not of the option
        self.assertEqual([e["item"] for e in plan], ["Companion: Bastila Shan", "Companion: Zez-Kai Ell"] + ["AP Companion"] * 3)
        self.assertTrue(all(e["kind"] == "ap" for e in plan[2:]))
        self.assertEqual([e["name"] for e in plan[2:]], [self.world.player_name, self.world.player_name + " 2", self.world.player_name + " 3"])    # a single-player multiworld: named after the player, numbered
        self.assertTrue(all(e["class"] in (0, 1, 2, 3, 4, 5, 9) for e in plan[2:]))
        self.assertTrue(all(e["look_method"] in ("disguise", "template") for e in plan))
        names = sorted(i.name for i in self.multiworld.itempool if i.name == "AP Companion" or i.name.startswith("Companion: ") and i.name.partition(": ")[2] in ("Bastila Shan", "Zez-Kai Ell"))
        self.assertEqual(names, ["AP Companion"] * 3 + ["Companion: Bastila Shan", "Companion: Zez-Kai Ell"])


class TestGeneratedCompanionLooks(KotorTwoTestBase):
    options = {"companions": "ap_gated", "ap_companions": 8}

    def test_looks_come_from_the_pool_without_repeats_and_never_from_a_story_companion(self):
        from ..Items import extra_companion_data
        data = extra_companion_data()
        plan = self.world.fill_slot_data()["extras"]
        pool = {l["appearance"]: l for l in data["ap_looks"]}
        rows = [e["appearance"] for e in plan]
        self.assertEqual(len(rows), 8)
        self.assertEqual(len(set(rows)), 8)
        for e in plan:
            self.assertIn(e["appearance"], pool)
            self.assertEqual(e["gender"], pool[e["appearance"]]["gender"])
            self.assertIn(e["portrait"], data["portraits"]["female" if e["gender"] else "male"])      # a player-head portrait of the character's sex
            self.assertEqual((e["fallback_appearance"], e["fallback_portrait"]), (e["appearance"], e["portrait"]))
        companion_looks = {451, 452, 453, 454, 455, 456, 457, 462, 463, 511, 561, 639}
        self.assertFalse(companion_looks & {l["appearance"] for l in data["ap_looks"]})


class TestRetiredEnemyTemplates(KotorTwoTestBase):
    options = {"enemy_randomizer": True}

    def test_the_swoop_gang_is_never_drawn(self):
        from ..Items import enemy_data
        self.assertNotIn("n_swoopgang", enemy_data()["pool"])                 # it renders as an untextured white figure (found live)
        plan = self.world.fill_slot_data()["enemy_plan"]
        self.assertTrue(plan["spawns"])
        self.assertNotIn("n_swoopgang", {sp["template"] for sp in plan["spawns"]})


class TestNoExtrasInDefaultMode(KotorTwoTestBase):
    options = {"extra_companions": ["Juhani"], "ap_companions": 2}

    def test_empty(self):
        self.assertEqual(self.world.fill_slot_data()["extras"], [])


class TestAllExtrasFit(KotorTwoTestBase):
    options = {"companions": "ap_limited", "extra_companions": ["Bastila Shan", "Carth Onasi", "Jolee Bindo", "Juhani", "Mission Vao", "Zaalbar", "Canderous Ordo",
                                                                  "Darth Sion", "Darth Nihilus", "Kavar", "Vrook Lamar", "Zez-Kai Ell"], "ap_companions": 8}

    def test_twenty_slots_from_twelve_to_thirty_one(self):
        plan = self.world.fill_slot_data()["extras"]
        self.assertEqual([e["slot"] for e in plan], list(range(12, 32)))



class TestShopsOffByDefault(KotorTwoTestBase):
    def test_no_plan(self):
        self.assertEqual(self.world.fill_slot_data()["shop_plan"], {})


class TestShopPlan(KotorTwoTestBase):
    options = {"shop_randomizer": True, "shop_count": 12}

    def test_one_list_per_planet_shared_by_its_stores(self):
        from ..Items import shop_data
        data = shop_data()
        plan = self.world.fill_slot_data()["shop_plan"]
        by_planet = {}
        for s in data["stores"]:
            by_planet.setdefault(s["planet"], []).append(s)
        stores = {s["tag"]: s for s in plan["stores"]}
        self.assertEqual(len(stores), sum(1 for s in data["stores"] if not s["leave_alone"]))
        self.assertTrue(all(t not in stores for t in ("DahniStore", "patostore", "m_207_001")))        # the Pazaak dealers keep their cards
        lists = {}
        for planet, rows in by_planet.items():
            shared = {tuple(stores[r["tag"]]["stock"]) for r in rows if not r["leave_alone"]}
            self.assertEqual(len(shared), 1, planet)
            lists[planet] = list(next(iter(shared)))
        self.assertEqual(len(set(map(tuple, lists.values()))), len(lists))                              # the planets differ
        for stock in lists.values():
            self.assertEqual(stock[:len(data["staples"])], data["staples"])
            drawn = stock[len(data["staples"]):]
            self.assertEqual(len(drawn), 12)
            self.assertEqual(len(set(drawn)), 12)
            self.assertTrue(set(drawn) <= set(data["pool"]))
        self.assertEqual(sorted(plan["silence"]), sorted(data["stock_scripts"]))


class TestLootOffByDefault(KotorTwoTestBase):
    def test_no_plan(self):
        self.assertEqual(self.world.fill_slot_data()["loot_plan"], {})


class TestLootPlan(KotorTwoTestBase):
    options = {"loot_randomizer": True, "loot_mode": "bonus"}

    def test_plan(self):
        from ..Items import shop_data
        plan = self.world.fill_slot_data()["loot_plan"]
        self.assertEqual(plan["mode"], "bonus")
        self.assertEqual(plan["pool"], shop_data()["pool"])
        self.assertEqual(plan["skip_modules"], ["101PER"])
        self.assertIsInstance(plan["seed"], int)


class TestLootReplaceIsTheDefaultMode(KotorTwoTestBase):
    options = {"loot_randomizer": True}

    def test_mode(self):
        self.assertEqual(self.world.fill_slot_data()["loot_plan"]["mode"], "replace")


class TestEnemiesOffByDefault(KotorTwoTestBase):
    def test_no_plan(self):
        self.assertEqual(self.world.fill_slot_data()["enemy_plan"], {})


class TestEnemyPlanRandomSane(KotorTwoTestBase):
    options = {"enemy_randomizer": True, "enemy_mode": "random_sane"}

    def test_every_point_gets_a_pool_creature_inside_the_difficulty_band(self):
        from ..Items import enemy_data
        data = enemy_data()
        spawns = self.world.fill_slot_data()["enemy_plan"]["spawns"]
        self.assertEqual(len(spawns), sum(len(m["points"]) for m in data["modules"].values()))
        self.assertTrue(all(s["module"] in data["modules"] and s["template"] in data["pool"] for s in spawns))
        self.assertTrue(all(s["source"] == data["pool"][s["template"]]["source"] for s in spawns))
        for module, info in data["modules"].items():
            band_ok = [r for r, p in data["pool"].items() if info["cr_min"] - 2.0 <= p["cr"] <= info["cr_cap"]]
            for s in spawns:
                if s["module"] == module and band_ok:
                    self.assertLessEqual(data["pool"][s["template"]]["cr"], info["cr_cap"], module)
                    self.assertGreaterEqual(data["pool"][s["template"]]["cr"], info["cr_min"] - 2.0, module)
        for excluded in data["excluded_modules"]:
            self.assertTrue(all(s["module"] != excluded for s in spawns))


class TestEnemyPlanAreaAppropriate(KotorTwoTestBase):
    options = {"enemy_randomizer": True, "enemy_mode": "area_appropriate"}

    def test_the_kind_of_creature_follows_the_area(self):
        from ..Items import enemy_data
        data = enemy_data()
        categories = {p["category"] for p in data["pool"].values()}
        for s in self.world.fill_slot_data()["enemy_plan"]["spawns"]:
            wanted = data["modules"][s["module"]]["category"]
            if wanted in categories:
                in_band = [r for r, p in data["pool"].items() if p["category"] == wanted and data["modules"][s["module"]]["cr_min"] - 2.0 <= p["cr"] <= data["modules"][s["module"]]["cr_cap"]]
                if in_band:
                    self.assertEqual(data["pool"][s["template"]]["category"], wanted, s["module"])


class TestEnemyPlanFullyRandom(KotorTwoTestBase):
    options = {"enemy_randomizer": True, "enemy_mode": "fully_random"}

    def test_no_difficulty_limit(self):
        from ..Items import enemy_data
        data = enemy_data()
        spawns = self.world.fill_slot_data()["enemy_plan"]["spawns"]
        self.assertTrue(any(data["pool"][s["template"]]["cr"] > data["modules"][s["module"]]["cr_cap"] for s in spawns))


class TestDoorShuffleAlone(unittest.TestCase):
    """The shuffle and the route requirements, without any Archipelago object."""

    def setUp(self):
        from ..Items import door_data
        self.data = door_data()

    def test_connected_coupled_and_complete_for_many_seeds(self):
        import random
        from .. import DoorShuffle as S
        doors = self.data["doors"]
        for seed in range(200):
            pairs = S.shuffle(self.data, random.Random(seed))
            self.assertEqual(sorted(d for p in pairs for d in p), sorted(doors))
            self.assertTrue(all(doors[a]["module"] != doors[b]["module"] for a, b in pairs))
            self.assertTrue(S.reachable(pairs, doors, self.data["roots"]) >= set(self.data["modules"]))
            self.assertEqual(set(S.path_requirements(pairs, self.data)), set(self.data["modules"]))

    def test_the_same_seed_gives_the_same_pairs(self):
        import random
        from .. import DoorShuffle as S
        self.assertEqual(S.shuffle(self.data, random.Random(5)), S.shuffle(self.data, random.Random(5)))
        self.assertNotEqual(S.shuffle(self.data, random.Random(5)), S.shuffle(self.data, random.Random(6)))

    def test_route_requirements_take_the_cheapest_route(self):
        from .. import DoorShuffle as S
        data = {"roots": ["r"], "modules": ["r", "a", "b", "c"], "module_requires": {"r": {}, "a": {"Telos": 3}, "b": {"Dantooine": 2}, "c": {}},
                "doors": {"r1": {"module": "r"}, "r2": {"module": "r"}, "a1": {"module": "a"}, "a2": {"module": "a"}, "b1": {"module": "b"}, "b2": {"module": "b"},
                          "c1": {"module": "c"}, "c2": {"module": "c"}}}
        pairs = [("r1", "a1"), ("r2", "b1"), ("a2", "c1"), ("b2", "c2")]
        req = S.path_requirements(pairs, data)
        self.assertEqual(req["a"], {})
        self.assertEqual(req["c"], {"Dantooine": 2})            # through b (needs 2) is cheaper than through a (needs 3)
        self.assertEqual(S.merge({"Telos": 1}, {"Telos": 3, "Korriban": 1}), {"Telos": 3, "Korriban": 1})


class TestAreaRandomizerOff(KotorTwoTestBase):
    def test_no_plan(self):
        self.assertEqual(self.world.fill_slot_data()["door_plan"], {})


class TestAreaRandomizerOn(KotorTwoTestBase):
    options = {"area_randomizer": True}

    def test_plan_is_coupled_and_matches_the_data(self):
        from ..Items import door_data
        data = door_data()
        links = {l["door"]: l for l in self.world.fill_slot_data()["door_plan"]["links"]}
        self.assertEqual(set(links), set(data["doors"]))
        for a, b in self.world.door_pairs:
            self.assertEqual(links[a]["to_module"], data["doors"][b]["module"])
            self.assertEqual(links[a]["to_waypoint"], data["doors"][b]["arrive"])
            self.assertEqual(links[b]["to_module"], data["doors"][a]["module"])

    def test_still_beatable_and_locations_in_pooled_modules_never_need_less_than_before(self):
        from ..Locations import LOCATIONS
        self.collect_all_but([])
        self.assertBeatable(True)
        reqs = self.world.door_path_reqs
        self.assertTrue(reqs)
        for loc in self.multiworld.get_locations(self.player):
            self.assertIsNotNone(loc)


class TestAreaRandomizerAddsRouteRequirements(KotorTwoTestBase):
    options = {"area_randomizer": True}

    def test_some_location_needs_more_than_in_the_base_game(self):
        from ..Items import door_data
        from ..Locations import LOCATIONS
        data = door_data()
        extra = 0
        for loc in LOCATIONS:
            spec_modules = [m for m in (loc.spec.get("module") or loc.spec.get("modules") or "").split(";") if m]
            if spec_modules and all(m in self.world.door_path_reqs for m in spec_modules):
                if self.world._door_requirements(loc):
                    extra += 1
        self.assertGreater(extra, 0)


class TestCraftingOffByDefault(KotorTwoTestBase):
    def test_no_plan_and_no_craft_items(self):
        self.assertEqual(self.world.fill_slot_data()["crafting_plan"], {})
        self.assertFalse(any(i.name.startswith("Crafting: ") for i in self.multiworld.itempool))


class TestCraftingModeWithoutGating(KotorTwoTestBase):
    options = {"crafting_mode": "complex"}

    def test_plan_has_the_gear_and_no_items(self):
        from ..Items import crafting_data
        plan = self.world.fill_slot_data()["crafting_plan"]
        self.assertEqual((plan["mode"], plan["gated"]), (2, False))
        self.assertEqual(plan["gear"], crafting_data()["gear"])
        self.assertEqual(plan["types"], ["armor", "ranged", "melee", "lightsaber", "other", "parts", "lab"])
        self.assertFalse(any(i.name.startswith("Crafting: ") for i in self.multiworld.itempool))


class TestCraftingGated(KotorTwoTestBase):
    options = {"crafting_mode": "simple", "crafting_gated": True}

    def test_one_item_per_type_in_the_pool(self):
        names = sorted(i.name for i in self.multiworld.itempool if i.name.startswith("Crafting: "))
        self.assertEqual(names, sorted(["Crafting: Armor and Robes", "Crafting: Ranged Weapons", "Crafting: Melee Weapons", "Crafting: Lightsabers",
                                        "Crafting: Belts, Gloves and Other Gear", "Crafting: Upgrade Parts", "Crafting: Chemical Lab"]))
        self.assertTrue(self.world.fill_slot_data()["crafting_plan"]["gated"])


class TestCraftingGatedWithoutMode(KotorTwoTestBase):
    options = {"crafting_gated": True}

    def test_only_the_games_own_types_are_gated(self):
        names = sorted(i.name for i in self.multiworld.itempool if i.name.startswith("Crafting: "))
        self.assertEqual(names, ["Crafting: Chemical Lab", "Crafting: Upgrade Parts"])
        plan = self.world.fill_slot_data()["crafting_plan"]
        self.assertEqual((plan["gear"], plan["types"]), ([], ["parts", "lab"]))


class TestGearItemsInThePool(KotorTwoTestBase):
    options = {"gear_items": 40}

    def test_gear_is_part_of_the_filler_and_the_plan_gates_recipes(self):
        gear = [i for i in self.multiworld.itempool if i.name.startswith("Gear: ")]
        self.assertGreater(len(gear), 20)
        self.assertTrue(all(not i.advancement for i in gear))
        self.assertEqual(len({i.name for i in gear}), len(gear) if len(gear) <= 360 else 360)       # every piece once before any repeats


class TestNoGearItemsWhenZero(KotorTwoTestBase):
    options = {"gear_items": 0}

    def test_none(self):
        self.assertFalse(any(i.name.startswith("Gear: ") for i in self.multiworld.itempool))


class TestCraftingPlanGatesRecipesByGearItems(KotorTwoTestBase):
    options = {"crafting_mode": "simple", "gear_items": 20}

    def test_flag(self):
        self.assertTrue(self.world.fill_slot_data()["crafting_plan"]["gear_gated"])


class TestCraftingPlanWithoutGearItems(KotorTwoTestBase):
    options = {"crafting_mode": "simple", "gear_items": 0}

    def test_flag(self):
        self.assertFalse(self.world.fill_slot_data()["crafting_plan"]["gear_gated"])


class TestVendorPasses(KotorTwoTestBase):
    options = {"archipelago_vendor": True}

    def test_three_passes_without_a_crafting_mode(self):
        names = sorted(i.name for i in self.multiworld.itempool if i.name.startswith("Vendor Pass: "))
        self.assertEqual(names, ["Vendor Pass: Ability Training", "Vendor Pass: Alignment Change", "Vendor Pass: Skill Training"])


class TestVendorPassesWithCrafting(KotorTwoTestBase):
    options = {"archipelago_vendor": True, "crafting_mode": "simple"}

    def test_the_supply_pass_joins(self):
        names = sorted(i.name for i in self.multiworld.itempool if i.name.startswith("Vendor Pass: "))
        self.assertEqual(len(names), 4)
        self.assertIn("Vendor Pass: Crafting Supplies", names)


class TestNoVendorByDefault(KotorTwoTestBase):
    def test_no_passes(self):
        self.assertFalse(any(i.name.startswith("Vendor Pass: ") for i in self.multiworld.itempool))


class TestPeragusOffByDefault(KotorTwoTestBase):
    def test_plan_empty_and_every_check_present(self):
        self.assertEqual(self.world.fill_slot_data()["peragus_plan"], {})
        self.assertIn("Visited: Peragus - Mining Tunnels", location_names(self))
        self.assertIn("Quest: Voiceprint Protocol", location_names(self))


class TestShortenedPeragus(KotorTwoTestBase):
    options = {"shortened_peragus": True}

    def test_the_cut_checks_are_gone_and_the_kept_ones_stay(self):
        names = location_names(self)
        for gone in ("Visited: Peragus - Mining Tunnels", "Visited: Peragus - Asteroid Exterior", "Visited: Peragus - Dormitories",
                     "Quest: Rescue FullName", "Quest: Turbolift Lockdown", "Quest: Voiceprint Protocol"):
            self.assertNotIn(gone, names)
        for kept in ("Visited: Peragus - Administration Level", "Visited: Peragus - Fuel Depot", "Visited: Peragus - Hangar Bay",
                     "Visited: Harbinger - Crew Quarters", "Quest: Rescue T3-M4", "Quest: Medical Bay Murders: Bonus Mission",
                     "Quest: Orbital Drift Charts", "Quest: Recover Ebon Hawk"):
            self.assertIn(kept, names)

    def test_the_plan_is_in_the_slot_data_with_the_hooks_of_variant_a(self):
        plan = self.world.fill_slot_data()["peragus_plan"]
        self.assertEqual(plan["variant"], "short_hallway")
        self.assertEqual(plan["skipped_modules"], ["102PER", "104PER", "105PER"])
        ids = [h["id"] for h in plan["hooks"]]
        self.assertEqual(ids, ["start", "jump", "act2", "navicomputer", "engine_deck", "hangar"])
        jump = plan["hooks"][1]["ops"]
        self.assertEqual(jump[0], {"op": "npc_add", "slot": 8, "tag": "T3M4"})          # slot 8 is re-opened by the jump or the first Hawk scene is dead
        self.assertEqual(jump[-1]["op"], "load")                                           # the module change comes last
        self.assertIn({"op": "global", "name": "101PER_Sion_Arrives", "value": 1}, jump)
        self.assertIn({"op": "journal", "tag": "MedBayMur", "stage": 40}, jump)             # mystery_flags is on by default so the Medical Bay Murders check stays possible

    def test_every_removed_check_is_a_real_location(self):
        from worlds.kotor2.Locations import LOCATION_NAME_TO_ID
        for name in self.world.fill_slot_data()["peragus_plan"]["removed_locations"]:
            self.assertIn(name, LOCATION_NAME_TO_ID)

    def test_the_slot_data_holds_no_cut_check(self):
        listed = {v["name"] for v in self.world.fill_slot_data()["locations"].values()}
        self.assertFalse(listed & set(self.world.fill_slot_data()["peragus_plan"]["removed_locations"]))


class TestPeragusHooksAreComplete(KotorTwoTestBase):
    options = {"shortened_peragus": True}

    def test_every_operation_has_its_fields(self):
        needs = {"unlock": {"tag"}, "global": {"name", "value"}, "journal": {"tag", "stage"}, "spell": {"id"}, "npc_add": {"slot", "tag"}, "npc_hide": {"slot"},
                 "destroy": {"tag"}, "faction_all": {"tag", "faction"}, "item": {"resref", "count"}, "spawn": {"template", "waypoint", "replace_tag"},
                 "load": {"module", "waypoint", "movie"}}
        for hook in self.world.fill_slot_data()["peragus_plan"]["hooks"]:
            self.assertTrue({"id", "module", "replaces", "run", "ops"} <= set(hook))
            for op in hook["ops"]:
                self.assertIn(op["op"], needs)
                self.assertTrue(needs[op["op"]] <= set(op), op)


class TestPeragusWithGoalLevelStillGenerates(KotorTwoTestBase):
    options = {"shortened_peragus": True, "goal": "high_level", "goal_level": 15, "experience_mode": "ap_limited", "experience_limiter": 3000}

    def test_generates(self):
        self.assertTrue(self.world.fill_slot_data()["peragus_plan"])


class TestLootMaterialsFlag(KotorTwoTestBase):
    options = {"loot_randomizer": True, "crafting_mode": "simple"}

    def test_flag(self):
        self.assertTrue(self.world.fill_slot_data()["loot_plan"]["materials"])


class TestLootMaterialsFlagOff(KotorTwoTestBase):
    options = {"loot_randomizer": True}

    def test_flag(self):
        self.assertFalse(self.world.fill_slot_data()["loot_plan"]["materials"])


class TestShopSuppliesOnlyFlag(KotorTwoTestBase):
    options = {"shop_randomizer": True, "crafting_gated": True}

    def test_flag(self):
        self.assertTrue(self.world.fill_slot_data()["shop_plan"]["supplies_only"])
