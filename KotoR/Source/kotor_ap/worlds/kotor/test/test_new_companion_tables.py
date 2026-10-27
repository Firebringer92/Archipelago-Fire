"""The New Companion console and the character builder keep two tables; every swap character the console offers must be built by
generate_new_companion_assets.py (a template for each slot, a spawn script and a greeting dialog), and everything the console's dialog names must exist."""
import os
import sys
import unittest

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "scripts")


@unittest.skipUnless(os.path.isdir(SCRIPTS), "scripts folder not next to this world")
class TestNewCompanionTables(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.abspath(SCRIPTS))
        import generate_new_companion_assets as assets
        import generate_new_companion_console as console
        cls.assets, cls.console = assets, console

    def test_every_console_character_is_built(self):
        built = set(self.assets.swap_template_resrefs())
        offered = {template for template, _label, _frag in self.console.CHARACTERS.values()}
        self.assertEqual(offered, built)

    def test_the_t3m4_slot_has_a_template_for_each_character(self):
        self.assertEqual(self.console.SLOTS["t3m4"]["suffix"], self.assets.T3_SUFFIX)
        self.assertEqual(self.console.SLOTS["hk47"]["suffix"], "")

    def test_trask_is_offered_and_built_as_himself(self):
        self.assertEqual(self.console.CHARACTERS["trask"], ("p_trask", "Trask Ulgo", "Trask"))
        spec = self.assets.NEW_CHARACTERS["trask"]
        self.assertEqual((spec["first"], spec["last"], spec["disguise_row"], spec["class_id"]), ("Trask", "Ulgo", 378, 0))

    def test_the_name_fragments_do_not_overlap(self):
        """The console tells who is in a slot by a part of their name, so no fragment may be part of another character's name or a slot's own companion."""
        names = {key: label for key, (_t, label, _f) in self.console.CHARACTERS.items()}
        names.update({slot: info["label"] for slot, info in self.console.SLOTS.items()})
        for key, (_t, _label, frag) in self.console.CHARACTERS.items():
            for other, label in names.items():
                if other != key:
                    with self.subTest(key=key, other=other):
                        self.assertNotIn(frag, label)

    def _dialog_resrefs(self):
        dlg = self.console.build_dlg()
        found, seen = set(), set()
        stack = []
        for link in dlg.starters:
            if link.active1 and str(link.active1):
                found.add(str(link.active1))
            stack.append(link.node)
        while stack:
            node = stack.pop()
            if id(node) in seen:
                continue
            seen.add(id(node))
            script = getattr(node, "script1", None)
            if script and str(script):
                found.add(str(script))
            for link in node.links:
                if link.active1 and str(link.active1):
                    found.add(str(link.active1))
                stack.append(link.node)
        return found

    def _generated_resrefs(self):
        names = {"ap_nc_use", "ap_nc_ready", "ap_nc_notyet"}
        for slot, info in self.console.SLOTS.items():
            names.update({info["ok"], info["greet"], info["cond"] + slot, info["swap"] + slot})
            for key in self.console.CHARACTERS:
                names.update({info["cond"] + key, info["swap"] + key})
        return names

    def test_the_dialog_names_only_scripts_the_generator_writes(self):
        self.assertEqual(self._dialog_resrefs() - self._generated_resrefs(), set())

    def test_every_script_name_fits_the_game_limit(self):
        for name in self._generated_resrefs():
            with self.subTest(name=name):
                self.assertLessEqual(len(name), 16)

    def test_every_template_name_fits_the_game_limit(self):
        for resref in self.assets.swap_template_resrefs():
            for suffix in ("", self.assets.T3_SUFFIX):
                with self.subTest(resref=resref + suffix):
                    self.assertLessEqual(len(resref + suffix), 16)

    def test_both_slots_offer_every_character_and_their_own_companion(self):
        resrefs = self._dialog_resrefs()
        for slot, info in self.console.SLOTS.items():
            self.assertIn(info["cond"] + slot, resrefs)
            for key in self.console.CHARACTERS:
                with self.subTest(slot=slot, key=key):
                    self.assertIn(info["cond"] + key, resrefs)
                    self.assertIn(info["swap"] + key, resrefs)
        self.assertEqual(len(self.console.build_dlg().starters), 2)

    def test_a_rolled_class_rewrites_the_template(self):
        """new_companion = random_class: class, starting feats, powers, hit points and Force points follow the rolled class."""
        a = self.assets
        for name, class_id in a.CLASS_IDS.items():
            utc = a.build_character_utc(dict(a.NEW_CHARACTERS["trask"]), 0)    # Constitution 12: a +1 modifier
            a.apply_rolled_class(utc, name)
            with self.subTest(name=name):
                self.assertEqual((utc.classes[0].class_id, utc.classes[0].class_level), (class_id, 1))
                self.assertEqual(utc.feats, a.CLASS_FEATS[name])
                self.assertEqual(utc.max_hp, a.CLASS_HIT_DIE[name] + 1)
                jedi = name in ("guardian", "consular", "sentinel")
                self.assertEqual(bool(utc.classes[0].powers), jedi)
                self.assertEqual(utc.max_fp > 0, jedi)

    def test_every_class_has_feats_and_a_hit_die(self):
        for name in self.assets.CLASS_IDS:
            self.assertIn(name, self.assets.CLASS_FEATS)
            self.assertIn(name, self.assets.CLASS_HIT_DIE)

    def test_a_restricted_character_cannot_wear_head_body_hands_gear_and_has_its_stats_built_in(self):
        """Armor on a disguised body crashed the game (Bandon, robes): a restricted character has the subrace baseitems.2da denies those slots to, and natural AC and save bonuses instead."""
        a = self.assets
        built = {"malak": a.build_malak_companion_utc(1, 1)}
        built.update({key: a.build_character_utc(dict(spec), 1) for key, spec in a.NEW_CHARACTERS.items()})
        self.assertEqual(set(built), {"malak", "calo", "yuthura", "bandon", "trask"})
        self.assertIn("bandon", a.GEAR_RESTRICTED)          # the one that crashed always stays restricted
        for key, utc in built.items():
            with self.subTest(key=key):
                if key in a.GEAR_RESTRICTED:
                    self.assertEqual(utc.subrace_id, a.MALAK_SUBRACE_ID)
                    self.assertEqual(utc.natural_ac, a.GEAR_SLOT_NATURAL_AC)
                    self.assertEqual((utc.reflex_bonus, utc.willpower_bonus, utc.fortitude_bonus), (a.GEAR_SLOT_SAVE_BONUS,) * 3)
                else:
                    self.assertEqual((utc.subrace_id, utc.natural_ac), (0, 0))
        meetra = a.build_new_companion_utc()      # a normal body, no disguise: wears gear as usual
        self.assertEqual((meetra.subrace_id, meetra.natural_ac), (0, 0))
