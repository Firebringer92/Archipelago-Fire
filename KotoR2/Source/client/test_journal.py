"""Tests of the Archipelago journal quests (client/k2_journal.py): the texts and stage counts the scripts and the world agree on, the byte-exact append to
dialog.tlk with its backup and restore, the journal file, and (where the game is installed) the real files, read only. Run through tools/run_client_tests.py."""
import json
import os
import re
import struct
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import k2_journal as J  # noqa: E402
from k2_patch import Patcher, find_game_dir  # noqa: E402


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def make_tlk(texts, language=0):
    """A small talk table in the game's format (flags 1: text present)."""
    blobs = [t.encode("cp1252") for t in texts]
    entries, offset = bytearray(), 0
    for b in blobs:
        entries += struct.pack("<I16sIIIIf", 1, b"", 0, 0, offset, len(b), 0.0)
        offset += len(b)
    return b"TLK V3.0" + struct.pack("<III", language, len(blobs), 20 + len(entries)) + bytes(entries) + b"".join(blobs)


def texts_of(data):
    from pykotor.resource.formats.tlk import read_tlk
    return [e.text for e in read_tlk(data).entries]


def make_jrl(tags):
    from pykotor.common.language import LocalizedString
    from pykotor.common.misc import Game
    from pykotor.resource.formats.gff import bytes_gff
    from pykotor.resource.generics.jrl import JRL, JRLEntry, JRLQuest, JRLQuestPriority, dismantle_jrl
    jrl = JRL()
    for i, tag in enumerate(tags):
        jrl.quests.append(JRLQuest(name=LocalizedString(10 + i), planet_id=2, priority=JRLQuestPriority.HIGH, tag=tag,
                                   entries=[JRLEntry(end=False, entry_id=5, text=LocalizedString(20 + i)), JRLEntry(end=True, entry_id=9, text=LocalizedString(30 + i))]))
    return bytes_gff(dismantle_jrl(jrl, game=Game.K2))


class TestTextsAndCounts(unittest.TestCase):
    def test_a_family_has_as_many_stages_as_the_most_any_gate_of_it_asks_for(self):
        gates = json.loads(read("data/gates.json"))["gates"]
        key_of = {"Telos": "telos", "Nar Shaddaa": "nar", "Dxun/Onderon": "dxn", "Dantooine": "dan", "Korriban": "kor", "Endgame": "endgame"}
        most = {}
        for g in gates:                                              # the gates that are off by default too: the stage is declared whichever gates a seed turns on
            most[key_of[g["family"]]] = max(most.get(key_of[g["family"]], 0), g["tokens_needed"])
        self.assertEqual({key: count for key, _name, count in J.FAMILIES}, most)

    def test_the_dispatcher_script_knows_the_same_stage_counts(self):
        source = read("nss/k2se_disp.nss")
        body = source[source.index("int DispProgressMax"): source.index("// Applies one job")]
        ones = set(re.findall(r'sFamily == "(\w+)"', body.split("return 3;")[0]))
        self.assertEqual(ones, {key for key, _n, count in J.FAMILIES if count == 3})
        self.assertIn('sFamily == "endgame") return 4;', body)
        self.assertEqual([c for _k, _n, c in J.FAMILIES if c not in (3, 4)], [])

    def test_the_scripts_and_the_client_use_the_same_quest_tags(self):
        self.assertIn('"ap_prog_" + sFamily', read("nss/k2ap_gate.nss"))
        self.assertIn('"ap_prog_" + sArgs', read("nss/k2se_disp.nss"))
        self.assertIn('"ap_tracker"', read("nss/k2se_disp.nss"))
        self.assertEqual((J.PROGRESS_PREFIX, J.TRACKER_TAG), ("ap_prog_", "ap_tracker"))
        for stage in J.TRACKER_STAGES:
            self.assertIn("nStage != %d" % stage if stage != J.TRACKER_STAGES[-1] else "nStage != 100", read("nss/k2se_disp.nss"))

    def test_every_text_is_plain_and_there_is_one_per_stage_and_name(self):
        texts = J.all_texts()
        self.assertEqual(len(texts), (1 + len(J.TRACKER_STAGES)) + sum(1 + c for _k, _n, c in J.FAMILIES))
        for t in texts:
            self.assertTrue(t.isascii() and t.strip() == t and t, t)

    def test_tracker_stage(self):
        self.assertEqual(J.tracker_stage(0, 0), 1)
        self.assertEqual(J.tracker_stage(0, 200), 1)
        self.assertEqual(J.tracker_stage(39, 200), 1)           # 19 percent
        self.assertEqual(J.tracker_stage(40, 200), 20)
        self.assertEqual(J.tracker_stage(120, 200), 60)
        self.assertEqual(J.tracker_stage(199, 200), 80)
        self.assertEqual(J.tracker_stage(200, 200), 100)


class TestTalkTable(unittest.TestCase):
    OLD = ["first", "second", "tést"]

    def test_the_append_keeps_every_old_entry_and_adds_ours_after_them(self):
        old = make_tlk(self.OLD)
        new, first = J.with_strings(old, J.all_texts())
        self.assertEqual(first, 3)
        self.assertEqual(texts_of(new), self.OLD + J.all_texts())
        # nothing before the new table rows and the new strings changed: the old string data is copied as it is
        self.assertEqual(new[:12], old[:12])
        self.assertTrue(new.endswith(b"".join(t.encode("cp1252") for t in J.all_texts())))
        self.assertIn(old[20 + 40 * 3:], new)

    def test_the_tail_is_found_only_when_all_of_it_is_there(self):
        old = make_tlk(self.OLD)
        new, first = J.with_strings(old, J.all_texts())
        self.assertIsNone(J.strings_at_tail(old, J.all_texts()))
        self.assertEqual(J.strings_at_tail(new, J.all_texts()), first)
        changed = make_tlk(self.OLD + J.all_texts()[:-1] + ["something else"])
        self.assertIsNone(J.strings_at_tail(changed, J.all_texts()))

    def test_a_file_that_is_not_a_talk_table_is_refused(self):
        with self.assertRaises(ValueError):
            J.with_strings(b"not a talk table at all, no", J.all_texts())


class Env(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.game = os.path.join(self.tmp.name, "game")
        self.state = os.path.join(self.tmp.name, "state")
        os.makedirs(os.path.join(self.game, "Override"))
        os.makedirs(self.state)
        self.old = make_tlk(["one", "two"])
        self.path = os.path.join(self.game, "dialog.tlk")
        with open(self.path, "wb") as f:
            f.write(self.old)

    def tlk(self):
        with open(self.path, "rb") as f:
            return f.read()


class TestEnsureStrings(Env):
    def test_the_texts_are_added_once_after_a_backup(self):
        first, problems = J.ensure_strings(self.game, self.state, False)
        self.assertEqual((first, problems), (2, []))
        self.assertEqual(texts_of(self.tlk()), ["one", "two"] + J.all_texts())
        with open(os.path.join(self.state, "strings", "dialog.tlk"), "rb") as f:
            self.assertEqual(f.read(), self.old)
        before = os.stat(self.path).st_mtime_ns
        self.assertEqual(J.ensure_strings(self.game, self.state, False), (2, []))       # a second time: found, nothing written
        self.assertEqual(os.stat(self.path).st_mtime_ns, before)

    def test_a_running_game_gets_no_new_file(self):
        first, problems = J.ensure_strings(self.game, self.state, True)
        self.assertIsNone(first)
        self.assertIn("close the game", problems[0])
        self.assertEqual(self.tlk(), self.old)
        self.assertFalse(os.path.exists(os.path.join(self.state, "strings")))

    def test_a_running_game_is_fine_when_the_texts_are_already_there(self):
        J.ensure_strings(self.game, self.state, False)
        self.assertEqual(J.ensure_strings(self.game, self.state, True), (2, []))

    def test_a_broken_table_is_a_problem_not_a_crash(self):
        with open(self.path, "wb") as f:
            f.write(b"garbage")
        first, problems = J.ensure_strings(self.game, self.state, False)
        self.assertIsNone(first)
        self.assertEqual(len(problems), 1)

    def test_the_backup_is_the_game_file_even_after_another_mod_replaced_it(self):
        J.ensure_strings(self.game, self.state, False)
        other = make_tlk(["one", "two", "three from another mod"])
        with open(self.path, "wb") as f:
            f.write(other)                                       # another mod's table: ours are gone from it
        first, _ = J.ensure_strings(self.game, self.state, False)
        self.assertEqual(first, 3)
        with open(os.path.join(self.state, "strings", "dialog.tlk"), "rb") as f:
            self.assertEqual(f.read(), other)                     # never a file that holds our strings

    def test_restore_puts_the_game_file_back(self):
        J.ensure_strings(self.game, self.state, False)
        self.assertEqual(J.restore_strings(self.game, self.state), (["dialog.tlk"], []))
        self.assertEqual(self.tlk(), self.old)
        self.assertEqual(J.restore_strings(self.game, self.state), ([], []))                # nothing more to do

    def test_restore_leaves_a_file_someone_else_changed(self):
        J.ensure_strings(self.game, self.state, False)
        changed = self.tlk() + b"x"
        with open(self.path, "wb") as f:
            f.write(changed)
        self.assertEqual(J.restore_strings(self.game, self.state), ([], ["dialog.tlk"]))
        self.assertEqual(self.tlk(), changed)

    def test_restore_waits_for_the_game_to_close(self):
        J.ensure_strings(self.game, self.state, False)
        restored, kept = J.restore_strings(self.game, self.state, running=True)
        self.assertEqual(restored, [])
        self.assertEqual(len(kept), 1)
        self.assertNotEqual(self.tlk(), self.old)

    def test_the_patchers_revert_puts_it_back_too(self):
        J.ensure_strings(self.game, self.state, False)
        res = Patcher(self.game, self.state, running=lambda: False, config_path=os.path.join(self.tmp.name, "config.txt")).revert()
        self.assertIn("dialog.tlk", res.removed)
        self.assertEqual(self.tlk(), self.old)
        self.assertEqual(res.errors, [])


class TestJournalFile(Env):
    def refs(self, data):
        from pykotor.resource.formats.gff import read_gff
        from pykotor.resource.generics.jrl import construct_jrl
        return construct_jrl(read_gff(data))

    def test_every_quest_name_and_stage_resolves_to_its_text(self):
        new, first = J.with_strings(self.old, J.all_texts())
        table = texts_of(new)
        jrl = self.refs(J.build_jrl(make_jrl(["vanilla_a", "vanilla_b"]), first))
        by_tag = {q.tag: q for q in jrl.quests}
        self.assertEqual([q.tag for q in jrl.quests[:2]], ["vanilla_a", "vanilla_b"])
        name, texts = J.tracker_texts()
        tracker = by_tag[J.TRACKER_TAG]
        self.assertEqual(table[tracker.name.stringref], name)
        self.assertEqual([(e.entry_id, table[e.text.stringref], e.end) for e in tracker.entries],
                         [(s, t, s == 100) for s, t in zip(J.TRACKER_STAGES, texts)])
        for key, family, count in J.FAMILIES:
            quest = by_tag[J.PROGRESS_PREFIX + key]
            fname, ftexts = J.family_texts(family, count)
            self.assertEqual(table[quest.name.stringref], fname)
            self.assertEqual([(e.entry_id, table[e.text.stringref], e.end) for e in quest.entries],
                             [(n, ftexts[n - 1], n == count) for n in range(1, count + 1)])
            self.assertEqual((quest.planet_id, quest.priority.name), (-1, "LOWEST"))

    def test_a_rebuild_does_not_double_the_quests_and_leaves_the_others_alone(self):
        once = J.build_jrl(make_jrl(["vanilla_a"]), 2)
        twice = J.build_jrl(once, 2)
        self.assertEqual([q.tag for q in self.refs(twice).quests], [q.tag for q in self.refs(once).quests])
        a = self.refs(twice).quests[0]
        self.assertEqual((a.tag, a.planet_id, [(e.entry_id, e.end, e.text.stringref) for e in a.entries]), ("vanilla_a", 2, [(5, False, 20), (9, True, 30)]))

    def test_journal_files_builds_on_the_backup_of_a_journal_file_another_mod_had(self):
        backup = os.path.join(self.game, "Override", "_k2ap_backup")
        os.makedirs(backup)
        with open(os.path.join(backup, "global.jrl"), "wb") as f:
            f.write(make_jrl(["from_another_mod"]))
        files, problems = J.journal_files(self.game, self.state, backup, False)
        self.assertEqual((sorted(files), problems), (["global.jrl"], []))
        self.assertEqual(self.refs(files["global.jrl"]).quests[0].tag, "from_another_mod")
        self.assertEqual(len(texts_of(self.tlk())), 2 + len(J.all_texts()))

    def test_a_running_game_without_the_texts_builds_nothing(self):
        files, problems = J.journal_files(self.game, self.state, os.path.join(self.game, "none"), True)
        self.assertEqual(files, {})
        self.assertEqual(len(problems), 1)


def without_our_strings(data):
    """A talk table of a game this client has patched, back to the game's own (our strings are the last entries; cut them off)."""
    first = J.strings_at_tail(data, J.all_texts())
    if first is None:
        return data
    count, _base = struct.unpack_from("<II", data, 12)
    cut, = struct.unpack_from("<I", data, 20 + 40 * first + 28)               # offset of our first string, relative to the string data
    base = 20 + 40 * count
    return data[:12] + struct.pack("<II", first, 20 + 40 * first) + data[20:20 + 40 * first] + data[base:base + cut]


def vanilla_files(game):
    """(dialog.tlk, global.jrl) as the game shipped them, whether or not this client has patched the install."""
    from pykotor.extract.installation import Installation, SearchLocation
    from pykotor.resource.type import ResourceType
    with open(os.path.join(game, "dialog.tlk"), "rb") as f:
        tlk = without_our_strings(f.read())
    return tlk, Installation(game).resource("global", ResourceType.JRL, [SearchLocation.CHITIN]).data


def real_game():
    return find_game_dir(None, os.path.join(os.environ.get("LOCALAPPDATA", ""), "K2SE", "ap", "game_dir.txt"))


@unittest.skipUnless(real_game(), "the game is not installed here")
class TestRealFiles(unittest.TestCase):
    """Reads the real game files (nothing is written to them)."""

    def test_the_append_keeps_the_games_own_entries_and_the_journal_keeps_the_games_own_quests(self):
        game = real_game()
        data, jrl_bytes = vanilla_files(game)
        new, first = J.with_strings(data, J.all_texts())
        self.assertEqual(first, struct.unpack_from("<I", data, 12)[0])
        self.assertEqual(J.strings_at_tail(new, J.all_texts()), first)
        old_count = first
        # the old string data and the old entries' offsets are untouched
        self.assertTrue(new.endswith(data[struct.unpack_from("<I", data, 16)[0]:] + b"".join(t.encode("cp1252") for t in J.all_texts())))
        self.assertEqual(new[20:20 + 40 * old_count], data[20:20 + 40 * old_count])
        from pykotor.extract.installation import Installation
        from pykotor.resource.formats.gff import read_gff
        from pykotor.resource.generics.jrl import construct_jrl
        from pykotor.resource.type import ResourceType
        old = construct_jrl(read_gff(jrl_bytes))
        built = construct_jrl(read_gff(J.build_jrl(jrl_bytes, first)))
        self.assertEqual(len(built.quests), len([q for q in old.quests if q.tag not in {J.TRACKER_TAG}]) + 1 + len(J.FAMILIES) - len([q for q in old.quests if q.tag.startswith(J.PROGRESS_PREFIX)]))
        for a, b in zip(old.quests, built.quests):
            self.assertEqual((a.tag, a.planet_id, [(e.entry_id, e.end, e.text.stringref) for e in a.entries]),
                             (b.tag, b.planet_id, [(e.entry_id, e.end, e.text.stringref) for e in b.entries]))


    def test_a_scratch_copy_of_the_real_table_gets_the_quests_and_gives_the_original_back(self):
        import hashlib
        import shutil
        game = real_game()
        from pykotor.extract.installation import Installation
        from pykotor.resource.formats.gff import read_gff
        from pykotor.resource.generics.jrl import construct_jrl
        from pykotor.resource.type import ResourceType
        tlk_bytes, jrl_bytes = vanilla_files(game)
        with tempfile.TemporaryDirectory() as tmp:
            scratch, state, backup = os.path.join(tmp, "game"), os.path.join(tmp, "state"), os.path.join(tmp, "game", "Override", "_k2ap_backup")
            os.makedirs(backup)
            os.makedirs(state)
            with open(os.path.join(scratch, "dialog.tlk"), "wb") as f:
                f.write(tlk_bytes)
            with open(os.path.join(backup, "global.jrl"), "wb") as f:
                f.write(jrl_bytes)
            original = hashlib.sha1(open(os.path.join(scratch, "dialog.tlk"), "rb").read()).hexdigest()
            files, problems = J.journal_files(scratch, state, backup, False)
            self.assertEqual((sorted(files), problems), (["global.jrl"], []))
            table = texts_of(open(os.path.join(scratch, "dialog.tlk"), "rb").read())
            quests = {q.tag: q for q in construct_jrl(read_gff(files["global.jrl"])).quests}
            self.assertEqual(table[quests["ap_prog_endgame"].name.stringref], "Archipelago Progress: Endgame")
            self.assertEqual(table[quests["ap_prog_endgame"].entries[3].text.stringref], J.family_texts("Endgame", 4)[1][3])
            self.assertEqual(table[quests["ap_tracker"].entries[0].text.stringref], J.tracker_texts()[1][0])
            self.assertEqual(J.restore_strings(scratch, state), (["dialog.tlk"], []))
            self.assertEqual(hashlib.sha1(open(os.path.join(scratch, "dialog.tlk"), "rb").read()).hexdigest(), original)


if __name__ == "__main__":
    unittest.main()
