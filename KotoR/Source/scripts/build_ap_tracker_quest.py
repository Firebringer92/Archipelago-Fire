"""
Builds an Override global.jrl declaring the "Archipelago Tracker" quest --
a journal entry showing overall check-completion progress at 0/20/40/60/
80/100%, so the player can see run progress without a cosmetic notify
message (see KotorClient.py/kotor_extender_bridge.py's removed "Connected
to..." send_notify calls).

Why this is needed at all: AddJournalQuestEntry(tag, id) only sets state
for a (tag, entry_id) pair that's already DECLARED in global.jrl -- it does
not spontaneously create a new quest from a never-seen tag. Confirmed live
via generate_trampoline_batch.py's now-retired diag_journal_persist_write/
_read research pair (arms 55/56): writing a brand-new, undeclared tag
("ap_journal_test") left GetJournalEntry reading -1 (unset) even
same-tick, before persistence across a save/reload was ever in question.
Superseded by diag_ap_tracker_write/_read (arms 58/59), which test this
quest's own properly-declared tag instead. global.jrl is a real, editable
GFF (pykotor's pykotor.resource.generics.jrl module: JRL/JRLQuest/JRLEntry,
confirmed via reading the real global.jrl -- 101 real quests, e.g.
tat18ac_dragonhunt) -- a structured data edit, not model/animation
surgery, so this carries none of the MDL-writer risk the Malak animation
fix hit.

planet_id=-1 matches the convention already used by 27 real quests (e.g.
k_starforge) that aren't tied to one specific planet -- exactly this
quest's own shape. priority=LOWEST so it doesn't compete with real story
quests for journal-sort prominence.

FIRST attempt (superseded, confirmed live): quest name/stage text via
LocalizedString.from_english() (stringref -1 + an inline substring) --
the same mechanism already proven working for Meetra/Malak's own first_
name/last_name (generate_new_companion_assets.py) and DLG entry text
elsewhere in this project. The quest itself DID appear in the in-game
Journal list (screenshot confirmed) -- AddJournalQuestEntry/global.jrl
declaration both genuinely work -- but its name rendered as a BLANK row.
Confirmed via direct read that the underlying data was written correctly
(stringref=-1, substring 0 = "Archipelago Tracker" present and intact) --
not a writer bug. The Journal screen's own quest-name lookup apparently
needs a real dialog.tlk stringref specifically and doesn't resolve an
inline substring the way character names/dialogue text do -- a real
Journal-UI-specific quirk, not a general LocalizedString problem.

This version appends the quest name + 6 stage texts as 7 new dialog.tlk
entries (game root, NOT Override -- there's no override mechanism for
this file, mods append to the real one) and references those stringrefs
instead. Purely additive -- only ever appends past the current end of the
table (49287 real entries confirmed via direct read), so every existing
stringref used throughout the rest of the game is completely undisturbed.
Idempotent: checks whether the last 7 entries already match this script's
own expected texts before appending again, so a rerun reuses the existing
indices instead of growing the table further each time.

Also invoked automatically on every Connect (KotorClient.py's
apply_ap_tracker_quest()) rather than shipping a pre-baked global.jrl --
_ensure_tlk_strings() is purely additive against WHATEVER dialog.tlk it's
pointed at, so the resulting stringrefs are only valid for the install
that actually ran this. A dev-machine-built global.jrl copied verbatim to
a different install would reference whatever entries happen to already
sit at the dev's own appended indices there -- wrong text, not a crash,
so this needs to run per-install rather than ship as a static file.

Usage: python build_ap_tracker_quest.py [--game-dir=<path>]
  Writes extender/raw_override_files/global.jrl (this install's own
  built copy -- not meant to be shared across installs, see above) and
  deploys it to <game-dir>/Override; patches <game-dir>/dialog.tlk
  in place (after backing up the original once, same convention as
  extender/build.ps1's binkw32_backups).
"""
import os
import shutil
import sys

from pykotor.common.language import LocalizedString
from pykotor.common.misc import Game
from pykotor.extract.installation import Installation
from pykotor.resource.formats.gff import read_gff, write_gff
from pykotor.resource.formats.tlk import read_tlk, write_tlk
from pykotor.resource.generics.jrl import construct_jrl, dismantle_jrl, JRLEntry, JRLQuest, JRLQuestPriority
from pykotor.resource.type import ResourceType

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
RAW_OVERRIDE_DIR = os.path.join(REPO_ROOT, "extender", "raw_override_files")

QUEST_TAG = "ap_tracker"
QUEST_NAME = "Archipelago Tracker"
STAGES = [
    # 1, NOT 0 -- confirmed via a direct read of every real quest in
    # global.jrl that NONE of the 101 vanilla quests ever use entry_id=0
    # (minimums are 1/3/5/10 only), and nwscript.nss's own GetJournalEntry
    # doc calls 0 "no quest entry has been added" -- a reserved sentinel,
    # not a real displayable stage. A live test at stage 0 (even after
    # fixing the name to a real dialog.tlk stringref, and even after a
    # RemoveJournalQuestEntry+re-add) still rendered a blank Journal row,
    # consistent with the UI treating state 0 as "not really there."
    (1, "Your Archipelago run has begun. Check locations throughout the "
        "galaxy to find items for yourself and other players.", False),
    (20, "You've found 20% of all checks in this run.", False),
    (40, "You've found 40% of all checks in this run.", False),
    (60, "You've found 60% of all checks in this run.", False),
    (80, "You've found 80% of all checks in this run.", False),
    (100, "You've found every check in this run. Well done!", True),
]
# Fixed order: quest name first, then each stage's text -- matches how
# _ensure_tlk_strings() below both checks for and appends them.
_TLK_TEXTS = [QUEST_NAME] + [text for _, text, _ in STAGES]


def _arg_value(flag, default):
    for a in sys.argv[1:]:
        if a.startswith(flag + "="):
            return a.split("=", 1)[1]
    return default


def _ensure_tlk_strings(game_dir: str) -> list[int]:
    """Returns the 7 stringref indices for _TLK_TEXTS, appending them to
    dialog.tlk if they aren't already there (idempotent rerun support)."""
    tlk_path = os.path.join(game_dir, "dialog.tlk")
    with open(tlk_path, "rb") as f:
        tlk = read_tlk(f.read())
    print(f"  dialog.tlk: {len(tlk.entries)} existing entries")

    n = len(_TLK_TEXTS)
    if len(tlk.entries) >= n:
        tail_start = len(tlk.entries) - n
        if [tlk.entries[tail_start + i].text for i in range(n)] == _TLK_TEXTS:
            indices = list(range(tail_start, tail_start + n))
            print(f"  already present at {indices[0]}-{indices[-1]}, reusing (no dialog.tlk write)")
            return indices

    backup_path = tlk_path + ".pre_ap_tracker_backup"
    if not os.path.exists(backup_path):
        shutil.copy2(tlk_path, backup_path)
        print(f"  backed up original -> {backup_path}")

    indices = [tlk.add(text) for text in _TLK_TEXTS]
    with open(tlk_path, "wb") as f:
        write_tlk(tlk, f)
    print(f"  appended {n} entries at {indices[0]}-{indices[-1]} -> {tlk_path} ({len(tlk.entries)} total)")
    return indices


def build(game_dir: str) -> None:
    stringrefs = _ensure_tlk_strings(game_dir)
    name_ref, stage_refs = stringrefs[0], stringrefs[1:]

    inst = Installation(game_dir)
    res = inst.resource("global", ResourceType.JRL)
    jrl = construct_jrl(read_gff(res.data))
    print(f"  source: {res.filepath} ({len(jrl.quests)} existing quests)")

    jrl.quests = [q for q in jrl.quests if q.tag != QUEST_TAG]
    quest = JRLQuest(
        name=LocalizedString(name_ref),
        planet_id=-1,
        priority=JRLQuestPriority.LOWEST,
        tag=QUEST_TAG,
        entries=[
            JRLEntry(end=end, entry_id=stage, text=LocalizedString(ref))
            for (stage, _, end), ref in zip(STAGES, stage_refs)
        ],
    )
    jrl.quests.append(quest)
    print(f"  added quest '{QUEST_TAG}' ({len(quest.entries)} stages) -> {len(jrl.quests)} total quests")

    gff = dismantle_jrl(jrl, game=Game.K1)
    out_path = os.path.join(RAW_OVERRIDE_DIR, "global.jrl")
    with open(out_path, "wb") as f:
        write_gff(gff, f, ResourceType.JRL)
    print(f"  wrote {out_path} ({os.path.getsize(out_path)} bytes)")

    override_dir = os.path.join(game_dir, "Override")
    shutil.copy2(out_path, os.path.join(override_dir, "global.jrl"))
    print(f"  deployed -> {override_dir}\\global.jrl")


if __name__ == "__main__":
    build(_arg_value("--game-dir", DEFAULT_GAME_DIR))
