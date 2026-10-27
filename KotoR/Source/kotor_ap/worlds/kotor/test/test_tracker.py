"""The location tracker's handling of the 0.2.0 check types (quest items, Bazaar purchases and Loot Exchange exchanges)."""
import os
import re
import unittest

from kotor_location_tracker import LocationTracker

from ..Locations import location_table, QUEST_ITEM_LOCATIONS
from ..StoryGates import location_planet


def _id(name):
    return location_table[name].id


class TestQuestItemChecks(unittest.TestCase):
    def setUp(self):
        self.tracker = LocationTracker()

    def test_every_quest_item_tag_credits_its_check(self):
        for name in QUEST_ITEM_LOCATIONS:
            for tag in location_table[name].quest_item_tags:
                with self.subTest(location=name, tag=tag):
                    self.assertEqual(self.tracker.check_event(f"AP|QUESTITEM|{tag}", set()), [_id(name)])

    def test_a_check_already_done_is_not_sent_again(self):
        name = "Quest Item: Sith Armor - Taris North Apartments"
        self.assertEqual(self.tracker.check_event("AP|QUESTITEM|ptar_sitharmor", {_id(name)}), [])

    def test_unknown_tag_is_ignored(self):
        self.assertEqual(self.tracker.check_event("AP|QUESTITEM|not_an_item", set()), [])

    def test_bacca_blade_alternate_completion_from_the_journal(self):
        blade = _id("Quest Item: Bacca's Sword Blade - Lower Shadowlands")
        chieftain = _id("Kashyyyk: Chieftain in Need")
        self.assertEqual(self.tracker.check_event("AP|CHECK|JOURNAL|kas23_mainwookplot|value=99", set()), [])
        self.assertEqual(self.tracker.check_event("AP|CHECK|JOURNAL|kas23_mainwookplot|value=100", set()), [blade])
        self.assertEqual(sorted(self.tracker.check_event("AP|CHECK|JOURNAL|kas23_mainwookplot|value=130", set())),
                         sorted([blade, chieftain]))
        self.assertEqual(self.tracker.check_event("AP|CHECK|JOURNAL|kas23_mainwookplot|value=130", {blade, chieftain}), [])

    def test_poll_reports_the_same_tags_as_the_world(self):
        """scripts/generate_poll_shared.py keeps its own list of quest item tags; it must match the world's."""
        path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "scripts", "generate_poll_shared.py")
        if not os.path.exists(path):
            self.skipTest("poll generator not next to this world")
        with open(path, encoding="utf-8") as f:
            source = f.read()
        block = re.search(r"_QUEST_ITEM_TAGS = \[(.*?)\]", source, re.S).group(1)
        poll_tags = set(re.findall(r'"([^"]+)"', block))
        world_tags = {tag for name in QUEST_ITEM_LOCATIONS for tag in location_table[name].quest_item_tags}
        self.assertEqual(poll_tags, world_tags)


class TestReceiptCounts(unittest.TestCase):
    def setUp(self):
        self.tracker = LocationTracker()

    def _names(self, ids):
        by_id = {d.id: n for n, d in location_table.items()}
        return sorted(by_id[i] for i in ids)

    def test_counts_credit_every_number_up_to_them(self):
        ids = self.tracker.check_event("AP|BAZAAR|2|3", set())
        self.assertEqual(self._names(ids), [
            "Archipelago Bazaar: Purchase 1", "Archipelago Bazaar: Purchase 2",
            "Bazaar Token Exchange 1", "Bazaar Token Exchange 2", "Bazaar Token Exchange 3",
        ])

    def test_only_new_numbers_are_credited_afterwards(self):
        self.tracker.check_event("AP|BAZAAR|2|3", set())
        ids = self.tracker.check_event("AP|BAZAAR|3|3", set())
        self.assertEqual(self._names(ids), ["Archipelago Bazaar: Purchase 3"])

    def test_a_lower_count_after_loading_an_earlier_save_credits_nothing_and_keeps_the_mark(self):
        self.tracker.check_event("AP|BAZAAR|4|10", set())
        self.assertEqual(self.tracker.check_event("AP|BAZAAR|1|2", set()), [])
        self.assertEqual(self.tracker.check_event("AP|BAZAAR|4|10", set()), [])
        ids = self.tracker.check_event("AP|BAZAAR|5|10", set())
        self.assertEqual(self._names(ids), ["Archipelago Bazaar: Purchase 5"])

    def test_counts_beyond_the_last_check_do_nothing_extra(self):
        ids = self.tracker.check_event("AP|BAZAAR|5|20", set())
        self.assertEqual(len(ids), 25)
        self.assertEqual(self.tracker.check_event("AP|BAZAAR|9|40", set()), [])

    def test_checks_already_on_the_server_are_not_sent_again(self):
        done = {_id("Archipelago Bazaar: Purchase 1"), _id("Bazaar Token Exchange 1")}
        ids = self.tracker.check_event("AP|BAZAAR|1|1", done)
        self.assertEqual(ids, [])


class TestCompanionIndex(unittest.TestCase):
    def test_hk47_owns_companion_index_3(self):
        tracker = LocationTracker()
        self.assertEqual(tracker.check_event("AP|CHECK|COMPANION|3", set()), [_id("Companion Recruited: HK-47")])


class TestReGrantLists(unittest.TestCase):
    """The plot items the reconciler re-grants must be the same in the client, the poll generator and the world."""

    def test_poll_generator_lists_the_same_items_as_the_client(self):
        import entitlement
        path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "scripts", "generate_poll_shared.py")
        if not os.path.exists(path):
            self.skipTest("poll generator not next to this world")
        with open(path, encoding="utf-8") as f:
            source = f.read()
        start = source.index("_PROGRESSION_ITEM_RESREFS = [")
        end = source.index('lines.append("// Roster report')
        namespace = {}
        exec(source[start:end], namespace)
        self.assertEqual(namespace["_PROGRESSION_ITEM_RESREFS"], list(entitlement.PROGRESSION_ITEM_RESREFS.items()))

    def test_every_re_granted_item_is_delivered_by_a_world_item(self):
        import entitlement
        from ..Items import item_table
        arms = {data.arm_name for data in item_table.values()}
        for key, resref in entitlement.PROGRESSION_ITEM_RESREFS.items():
            with self.subTest(key=key):
                self.assertIn(f"give_item:{resref}", arms)


class TestLeavingTaris(unittest.TestCase):
    """Stage 99 of Escaping Taris completes every Taris and Endar Spire check the player did not reach."""
    ESCAPE = "AP|CHECK|JOURNAL|tar_escape|value=%d"

    def setUp(self):
        self.tracker = LocationTracker()
        self.expected = {data.id for name, data in location_table.items()
                         if location_planet(name, data) in ("Taris", "Endar Spire")}

    def test_nothing_is_released_before_the_escape_is_done(self):
        for stage in (1, 20, 50, 98):
            self.tracker.check_event(self.ESCAPE % stage, set())
            self.assertEqual(self.tracker.last_release_ids, set())

    def test_the_escape_releases_every_unreached_taris_and_endar_spire_check(self):
        sent = set(self.tracker.check_event(self.ESCAPE % 99, set()))
        self.assertEqual(sent, self.expected | {_id("Taris: Escaping Taris")})
        self.assertEqual(self.tracker.last_release_ids, self.expected - {_id("Taris: Escaping Taris")})

    def test_the_release_covers_the_taris_companions_the_visits_and_the_quest_items(self):
        sent = set(self.tracker.check_event(self.ESCAPE % 99, set()))
        for name in ("Companion Recruited: Mission Vao", "Companion Recruited: Zaalbar", "Companion Recruited: Carth Onasi",
                     "Quest Item: Shield Codes - Taris Sith Base"):
            with self.subTest(name=name):
                self.assertIn(_id(name), sent)

    def test_other_planets_are_never_released(self):
        sent = set(self.tracker.check_event(self.ESCAPE % 99, set()))
        for name, data in location_table.items():
            if location_planet(name, data) not in ("Taris", "Endar Spire") and name != "Taris: Escaping Taris":
                with self.subTest(name=name):
                    self.assertNotIn(data.id, sent)

    def test_checks_already_done_are_not_sent_again_and_a_repeat_sends_nothing(self):
        done = {_id("Companion Recruited: Carth Onasi"), _id("Taris: Escaping Taris")}
        sent = set(self.tracker.check_event(self.ESCAPE % 99, done))
        self.assertFalse(sent & done)
        self.assertEqual(self.tracker.check_event(self.ESCAPE % 99, done | sent), [])
        self.assertEqual(self.tracker.last_release_ids, set())

    def test_a_late_reconnect_still_releases(self):
        """The poll repeats the journal value for as long as the save holds it; the first event after a reconnect releases."""
        sent = self.tracker.check_event(self.ESCAPE % 99, set())
        self.assertTrue(set(sent) >= self.expected)


class TestAlternateCompletions(unittest.TestCase):
    """Quests a player can make impossible to finish are completed by another journal value instead (tracker only; the journal itself is untouched)."""

    def setUp(self):
        self.tracker = LocationTracker()

    def test_dead_settler_completes_with_the_feud(self):
        settler, feud = _id("Dantooine: Dead Settler"), _id("Dantooine: Sandral-Matale Feud")
        self.assertEqual(self.tracker.check_event("AP|CHECK|JOURNAL|dan_romance|value=50", set()), [])
        self.assertEqual(sorted(self.tracker.check_event("AP|CHECK|JOURNAL|dan_romance|value=60", set())), sorted([settler, feud]))
        for ending in (62, 64, 66, 68):
            self.assertIn(settler, self.tracker.check_event(f"AP|CHECK|JOURNAL|dan_romance|value={ending}", set()))

    def test_dead_settler_still_completes_the_normal_way(self):
        self.assertEqual(self.tracker.check_event("AP|CHECK|JOURNAL|dan_casus|value=20", set()), [_id("Dantooine: Dead Settler")])
        self.assertEqual(self.tracker.check_event("AP|CHECK|JOURNAL|dan_casus|value=10", set()), [])

    def test_tach_poaching_completes_when_the_poachers_are_removed_before_the_quest_is_taken(self):
        tach, request = _id("Kashyyyk: Tach Poaching"), _id("Kashyyyk: Jolee's Request")
        self.assertEqual(self.tracker.check_event("AP|CHECK|JOURNAL|kas24_removepoachers|value=37", set()), [])
        self.assertEqual(sorted(self.tracker.check_event("AP|CHECK|JOURNAL|kas24_removepoachers|value=40", set())), sorted([tach, request]))

    def test_tach_poaching_still_completes_the_normal_way(self):
        self.assertEqual(self.tracker.check_event("AP|CHECK|JOURNAL|kas24_tachpoaching|value=50", set()), [_id("Kashyyyk: Tach Poaching")])

    def test_a_check_already_done_is_not_sent_again(self):
        done = {_id("Dantooine: Dead Settler"), _id("Dantooine: Sandral-Matale Feud")}
        self.assertEqual(self.tracker.check_event("AP|CHECK|JOURNAL|dan_romance|value=60", done), [])

    def test_every_alternate_completion_is_fully_described(self):
        for name, data in location_table.items():
            if data.alt_journal_tag:
                with self.subTest(location=name):
                    self.assertGreater(data.alt_journal_target, 0)
                    self.assertIn(data.id, {i for _t, n in self.tracker._alt_journal_index[data.alt_journal_tag] for i in [location_table[n].id]})
