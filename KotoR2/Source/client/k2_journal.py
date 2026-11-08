"""The Archipelago quests in the game's journal: one progress quest per planet family and the run tracker.

The story gates count how far a family's quest has got (nss/k2ap_gate.nss reads the quest's stage with GetJournalEntry), and every progression item of that
family moves its quest one stage on (the dispatcher's "token" job). The stage is stored in the save, so a loaded older save brings back the progress it had, and
the player sees it in the Journal. One more quest, the Archipelago Tracker, shows the share of the run's checks that are done (the dispatcher's "tracker" job).

  ap_prog_<family>   telos, nar, dxn, dan, kor, endgame: stage n = n progression items of that family received, the last stage ends the quest
  ap_tracker         stages 1, 20, 40, 60, 80, 100: the percent of checks done, 100 ends the quest

The game only accepts AddJournalQuestEntry for a (quest, stage) pair that global.jrl declares, and the Journal screen shows a quest's name and stage text only
from a dialog.tlk string (an inline text rendered as a blank row in KotOR 1, which has the same screen). So this module
  * appends the texts to the end of dialog.tlk (the entries already there are not touched: only the table grows, then the new texts follow the old ones),
  * builds a global.jrl from the one the game uses (Override's own if another mod put one there) with these quests added, for Override.
Both are made on the player's machine from the player's own files and nothing here is shipped. dialog.tlk is backed up before it is first written and put back
by revert (restore_strings) when it still is what this module wrote. A running game is never given a new dialog.tlk (it reads the file by offset).
"""
import hashlib
import json
import os
import shutil
import struct
import typing

PROGRESS_PREFIX = "ap_prog_"
TRACKER_TAG = "ap_tracker"
TRACKER_NAME = "Archipelago Tracker"
TRACKER_STAGES = (1, 20, 40, 60, 80, 100)
# (key, name shown, items in the family): the most any gate of the family asks for, including the gates that are off by default (data/gates.json; test_journal.py)
FAMILIES = (("telos", "Telos", 3), ("nar", "Nar Shaddaa", 3), ("dxn", "Dxun and Onderon", 3), ("dan", "Dantooine", 3), ("kor", "Korriban", 3),
            ("endgame", "Endgame", 4))
STRINGS_DIR = "strings"
TLK = "dialog.tlk"
HEADER = 20
ENTRY = 40


def family_texts(name: str, count: int) -> typing.Tuple[str, typing.List[str]]:
    """(quest name, [text of stage 1 .. count]) for a family."""
    texts = []
    for n in range(1, count + 1):
        if n < count:
            texts.append("You have found %d of the %d %s progression items. The story there moves on as you find more of them." % (n, count, name))
        else:
            texts.append("You have found all %d %s progression items. Nothing there is held back any more." % (count, name))
    return "Archipelago Progress: %s" % name, texts


def tracker_texts() -> typing.Tuple[str, typing.List[str]]:
    texts = ["Your Archipelago run has begun. Check locations throughout the galaxy to find items for yourself and other players."]
    texts += ["You have completed %d percent of the checks in this run." % p for p in TRACKER_STAGES[1:-1]]
    texts.append("You have completed every check in this run. Well done!")
    return TRACKER_NAME, texts


def all_texts() -> typing.List[str]:
    """Every string appended to dialog.tlk, in a fixed order: the tracker (name, stages), then each family (name, stages)."""
    name, texts = tracker_texts()
    out = [name] + texts
    for _key, family, count in FAMILIES:
        name, texts = family_texts(family, count)
        out += [name] + texts
    return out


def tracker_stage(done: int, total: int) -> int:
    """The tracker stage for `done` of `total` checks: 1 at the start, then the highest threshold reached; 100 only when every check is done."""
    if total <= 0:
        return TRACKER_STAGES[0]
    percent = 100 * done // total
    stage = TRACKER_STAGES[0]
    for s in TRACKER_STAGES[1:-1]:
        if percent >= s:
            stage = s
    return TRACKER_STAGES[-1] if done >= total else stage


# ---- dialog.tlk ---------------------------------------------------------------------------------------------------------------------------
def _header(data: bytes) -> typing.Tuple[int, int]:
    """(string count, offset of the string data) of a KotOR talk table."""
    if len(data) < HEADER or data[:8] != b"TLK V3.0":
        raise ValueError("dialog.tlk is not a talk table the game knows (version 3.0)")
    count, base = struct.unpack_from("<II", data, 12)
    if base != HEADER + ENTRY * count:
        raise ValueError("dialog.tlk has an entry table of an unexpected size")
    return count, base


def _text(data: bytes, base: int, index: int) -> str:
    flags, = struct.unpack_from("<I", data, HEADER + ENTRY * index)
    offset, size = struct.unpack_from("<II", data, HEADER + ENTRY * index + 28)
    return data[base + offset: base + offset + size].decode("cp1252", "replace") if flags & 1 else ""


def strings_at_tail(data: bytes, texts: typing.Sequence[str]) -> typing.Optional[int]:
    """The index of the first of `texts` when they already end the table, else None."""
    count, base = _header(data)
    n = len(texts)
    if count < n:
        return None
    first = count - n
    return first if all(_text(data, base, first + i) == t for i, t in enumerate(texts)) else None


def with_strings(data: bytes, texts: typing.Sequence[str]) -> typing.Tuple[bytes, int]:
    """The table with `texts` added after the last entry: (new bytes, index of the first new string). Every old entry keeps its offset (they are relative to
    the string data), so only the header and the entry table change; the old string data is copied as it is."""
    count, base = _header(data)
    table, old_strings = data[HEADER:base], data[base:]
    blobs = [t.encode("cp1252", "replace") for t in texts]
    entries, offset = bytearray(), len(old_strings)
    for blob in blobs:
        entries += struct.pack("<I16sIIIIf", 1, b"", 0, 0, offset, len(blob), 0.0)
        offset += len(blob)
    header = data[:12] + struct.pack("<II", count + len(blobs), base + len(entries))
    return header + table + bytes(entries) + old_strings + b"".join(blobs), count


def _sha(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def _atomic_write(path: str, blob: bytes) -> None:
    tmp = path + ".k2ap_tmp"
    with open(tmp, "wb") as f:
        f.write(blob)
    os.replace(tmp, path)


def ensure_strings(game_dir: str, state_dir: str, running: bool) -> typing.Tuple[typing.Optional[int], typing.List[str]]:
    """Make dialog.tlk hold the texts. Returns (index of the first text or None, problems). Writes the file (after a backup) only when the texts are missing
    and the game is not running."""
    path = os.path.join(game_dir, TLK)
    texts = all_texts()
    try:
        with open(path, "rb") as f:
            data = f.read()
        first = strings_at_tail(data, texts)
    except (OSError, ValueError) as e:
        return None, ["the Archipelago journal texts could not be added: %s" % e]
    if first is not None:
        return first, []
    if running:
        return None, ["the Archipelago journal needs new texts in dialog.tlk, which the running game must not have changed: close the game and connect again"]
    folder = os.path.join(state_dir, STRINGS_DIR)
    record_path = os.path.join(folder, "record.json")
    try:
        os.makedirs(folder, exist_ok=True)
        record = {}
        try:
            with open(record_path) as f:
                record = json.load(f)
        except (OSError, ValueError):
            pass
        backup = os.path.join(folder, TLK)
        if record.get("written_sha") != _sha(data) or not os.path.isfile(backup):
            shutil.copy2(path, backup)                     # the game's file as it is now (the one before our strings); never a file we wrote ourselves
        new, first = with_strings(data, texts)
        _atomic_write(path, new)
        with open(record_path, "w") as f:
            json.dump({"written_sha": _sha(new), "game_dir": game_dir}, f)
    except OSError as e:
        return None, ["dialog.tlk could not be written (%s): the Archipelago journal needs its texts there" % e]
    return first, []


def restore_strings(game_dir: str, state_dir: str, running: bool = False) -> typing.Tuple[typing.List[str], typing.List[str]]:
    """(restored, left alone): puts dialog.tlk back from the backup when it still is exactly what this module wrote."""
    folder = os.path.join(state_dir, STRINGS_DIR)
    backup, record_path, path = os.path.join(folder, TLK), os.path.join(folder, "record.json"), os.path.join(game_dir, TLK)
    try:
        with open(record_path) as f:
            record = json.load(f)
        with open(path, "rb") as f:
            current = f.read()
    except (OSError, ValueError):
        return [], []
    if not os.path.isfile(backup) or record.get("game_dir", "").lower() != game_dir.lower():
        return [], []
    if _sha(current) != record.get("written_sha"):
        return [], [TLK]
    if running:
        return [], [TLK + " (the game is running)"]
    try:
        shutil.copy2(backup, path)
        os.remove(backup)
        os.remove(record_path)
    except OSError:
        return [], [TLK]
    return [TLK], []


# ---- global.jrl ---------------------------------------------------------------------------------------------------------------------------
def build_jrl(base: bytes, first: int) -> bytes:
    """global.jrl `base` with the quests added (any quest of ours already in it is dropped first, so a rebuild never doubles them). `first` is the index of the
    first appended text."""
    from pykotor.common.language import LocalizedString
    from pykotor.common.misc import Game
    from pykotor.resource.formats.gff import bytes_gff, read_gff
    from pykotor.resource.generics.jrl import JRLEntry, JRLQuest, JRLQuestPriority, construct_jrl, dismantle_jrl
    jrl = construct_jrl(read_gff(base))
    ours = {TRACKER_TAG} | {PROGRESS_PREFIX + key for key, _n, _c in FAMILIES}
    jrl.quests = [q for q in jrl.quests if q.tag not in ours]
    ref = first

    def quest(tag: str, name: str, stages: typing.Sequence[typing.Tuple[int, str]]) -> None:
        nonlocal ref
        quest_name = ref
        ref += 1
        entries = []
        for i, (stage, _text) in enumerate(stages):
            entries.append(JRLEntry(end=i == len(stages) - 1, entry_id=stage, text=LocalizedString(ref)))
            ref += 1
        # planet_id -1 and the lowest priority: the convention of the game's quests that belong to no planet
        jrl.quests.append(JRLQuest(name=LocalizedString(quest_name), planet_id=-1, priority=JRLQuestPriority.LOWEST, tag=tag, entries=entries))

    name, texts = tracker_texts()
    quest(TRACKER_TAG, name, list(zip(TRACKER_STAGES, texts)))
    for key, family, count in FAMILIES:
        name, texts = family_texts(family, count)
        quest(PROGRESS_PREFIX + key, name, list(zip(range(1, count + 1), texts)))
    return bytes_gff(dismantle_jrl(jrl, game=Game.K2))


def journal_files(game_dir: str, state_dir: str, backup_dir: str, running: bool) -> typing.Tuple[typing.Dict[str, bytes], typing.List[str]]:
    """({"global.jrl": bytes}, problems): the strings are put in dialog.tlk and the journal file is built on the game's own (or the one another mod put in
    Override: the backup the patcher made of it if the one in Override is ours)."""
    first, problems = ensure_strings(game_dir, state_dir, running)
    if first is None:
        return {}, problems
    try:
        saved = os.path.join(backup_dir, "global.jrl")
        if os.path.isfile(saved):
            with open(saved, "rb") as f:
                base = f.read()
        else:
            from pykotor.extract.installation import Installation
            from pykotor.resource.type import ResourceType
            res = Installation(game_dir).resource("global", ResourceType.JRL)
            if res is None:
                return {}, problems + ["the game's global.jrl was not found: the Archipelago journal was not built"]
            base = res.data
        return {"global.jrl": build_jrl(base, first)}, problems
    except Exception as e:
        return {}, problems + ["the Archipelago journal file could not be built: %s" % e]
