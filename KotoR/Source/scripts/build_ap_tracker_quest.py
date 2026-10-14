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
import subprocess
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

# One-stage journal quests that persist "this companion's recruit check was
# reached" in the SAVE. The recruit scripts (see extender/scripts_src/
# ap_recruit_marker.nss) write the quest the moment the recruit is reached,
# and ap_poll_shared's CheckRecruitMarkers() re-reports every set one on every
# poll. The live AP|CHECK|COMPANION line is a one-shot: if the client is down,
# disconnected, or attached to a dead process at that instant, the check is
# lost for good. A marker in the save can't be. Key order/indices match
# Locations.py's companion_idx (bastila 0 ... zaalbar 8).
RECRUIT_QUEST_PREFIX = "ap_recruit_"
RECRUITS = [
    ("bastila", "Bastila Shan"),
    ("canderous", "Canderous Ordo"),
    ("carth", "Carth Onasi"),
    ("hk47", "HK-47 (or his replacement)"),
    ("jolee", "Jolee Bindo"),
    ("juhani", "Juhani"),
    ("mission", "Mission Vao"),
    ("t3m4", "T3-M4"),
    ("zaalbar", "Zaalbar"),
]
RECRUIT_STAGE = 1  # same "never 0" reasoning as STAGES below

# Entitlement markers: one journal quest per companion, ap_ent_<key>, that records in the SAVE whether the player is entitled to that
# companion. Stage 10 = entitled (written by the companion grant arm in the same script that adds the companion), stage 20 = trapped
# off for good (written by the Remove a Companion trap). A quest only moves forward, so 20 cannot be overwritten by an ordinary
# write. The reconciler (kotor_reconciliation.py) treats a companion on the roster with no marker, or with marker 20, as a leak.
# Stage 10 is not an ending (it stays an active quest); stage 20 is.
CREW_QUEST_PREFIX = "ap_ent_"
CREW_ENTITLED = 10
CREW_TRAPPED = 20


def _crew_texts(display: str) -> tuple[str, str, str]:
    return (f"Archipelago Crew: {display}",
            f"{display} is part of your crew. Archipelago recorded this in your save.",
            f"{display} has left your crew for good.")


def _recruit_texts(display: str) -> tuple[str, str]:
    return (f"Archipelago Recruit: {display}",
            f"You reached the recruitment of {display}. Your Archipelago check for it is recorded in this save.")


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
# _ensure_tlk_strings() below both checks for and appends them. The tracker's
# own 7 strings come first and stay a contiguous block on their own, so an
# install that already appended them (before the recruit quests existed) only
# needs the recruit strings added after them.
_TRACKER_TEXTS = [QUEST_NAME] + [text for _, text, _ in STAGES]
_RECRUIT_TEXTS = [t for _, display in RECRUITS for t in _recruit_texts(display)]
_CREW_TEXTS = [t for _, display in RECRUITS for t in _crew_texts(display)]
_TLK_TEXTS = _TRACKER_TEXTS + _RECRUIT_TEXTS + _CREW_TEXTS


def _arg_value(flag, default):
    for a in sys.argv[1:]:
        if a.startswith(flag + "="):
            return a.split("=", 1)[1]
    return default


def _game_running() -> bool:
    """True if swkotor.exe is running. dialog.tlk is read by the engine by
    offset, and appending entries rewrites the whole offset table, so
    rewriting it under a running game would garble that session's text."""
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq swkotor.exe", "/NH"],
                             capture_output=True, text=True, timeout=15).stdout
        return "swkotor.exe" in out.lower()
    except Exception:
        return False  # can't tell -> behave exactly as before this guard existed


class GameRunningError(RuntimeError):
    """dialog.tlk needs new entries but the game is running."""


def _ensure_tlk_strings(game_dir: str, check_running: bool = True) -> list[int]:
    """Returns the stringref indices for _TLK_TEXTS (tracker block first,
    then the recruit quests), appending only what's missing to dialog.tlk
    (idempotent rerun support):
      - everything already sits at the tail -> reuse it, no write;
      - only the tracker's own block sits at the tail (an install from
        before the recruit quests existed) -> append just the recruit
        strings right after it, so those 7 entries aren't orphaned;
      - otherwise append everything.
    Raises GameRunningError instead of writing while the game is running."""
    tlk_path = os.path.join(game_dir, "dialog.tlk")
    with open(tlk_path, "rb") as f:
        tlk = read_tlk(f.read())
    print(f"  dialog.tlk: {len(tlk.entries)} existing entries")

    texts = [e.text for e in tlk.entries]
    n = len(_TLK_TEXTS)
    t = len(_TRACKER_TEXTS)
    r = len(_RECRUIT_TEXTS)
    if len(texts) >= n and texts[-n:] == _TLK_TEXTS:
        tail_start = len(texts) - n
        indices = list(range(tail_start, tail_start + n))
        print(f"  already present at {indices[0]}-{indices[-1]}, reusing (no dialog.tlk write)")
        return indices

    if check_running and _game_running():
        raise GameRunningError(
            "dialog.tlk needs the Archipelago quest strings but swkotor.exe is running -- "
            "close the game and reconnect the client to apply them")

    backup_path = tlk_path + ".pre_ap_tracker_backup"
    if not os.path.exists(backup_path):
        shutil.copy2(tlk_path, backup_path)
        print(f"  backed up original -> {backup_path}")

    # Blocks sit at the tail in this order: tracker (7), recruit (18), crew (27). An install that already has a prefix of them
    # at the tail (the tracker alone, or tracker + recruit from 0.1.8) only gets the missing blocks appended right after it.
    if len(texts) >= t + r and texts[-(t + r):] == _TRACKER_TEXTS + _RECRUIT_TEXTS:
        start = len(texts) - (t + r)
        new_indices = [tlk.add(text) for text in _CREW_TEXTS]
        indices = list(range(start, start + t + r)) + new_indices
        print(f"  tracker + recruit strings already at {start}-{start + t + r - 1}; "
              f"appended {len(new_indices)} crew entries at {new_indices[0]}-{new_indices[-1]}")
    elif len(texts) >= t and texts[-t:] == _TRACKER_TEXTS:
        tracker_start = len(texts) - t
        new_indices = [tlk.add(text) for text in _RECRUIT_TEXTS + _CREW_TEXTS]
        indices = list(range(tracker_start, tracker_start + t)) + new_indices
        print(f"  tracker strings already at {tracker_start}-{tracker_start + t - 1}; "
              f"appended {len(new_indices)} recruit and crew entries at {new_indices[0]}-{new_indices[-1]}")
    else:
        indices = [tlk.add(text) for text in _TLK_TEXTS]
        print(f"  appended {n} entries at {indices[0]}-{indices[-1]}")

    with open(tlk_path, "wb") as f:
        write_tlk(tlk, f)
    print(f"  wrote {tlk_path} ({len(tlk.entries)} total)")
    return indices


def build_quests(jrl, stringrefs: list[int]) -> None:
    """Replaces the tracker quest and the 9 recruit quests in `jrl` (any
    existing quest with one of those tags is dropped first, so a rerun never
    duplicates). stringrefs follows _TLK_TEXTS order."""
    t = len(_TRACKER_TEXTS)
    r = len(_RECRUIT_TEXTS)
    name_ref, stage_refs = stringrefs[0], stringrefs[1:t]
    recruit_refs = stringrefs[t:t + r]
    crew_refs = stringrefs[t + r:]

    recruit_tags = {f"{RECRUIT_QUEST_PREFIX}{key}" for key, _ in RECRUITS}
    crew_tags = {f"{CREW_QUEST_PREFIX}{key}" for key, _ in RECRUITS}
    jrl.quests = [q for q in jrl.quests if q.tag != QUEST_TAG and q.tag not in recruit_tags and q.tag not in crew_tags]

    jrl.quests.append(JRLQuest(
        name=LocalizedString(name_ref),
        planet_id=-1,
        priority=JRLQuestPriority.LOWEST,
        tag=QUEST_TAG,
        entries=[
            JRLEntry(end=end, entry_id=stage, text=LocalizedString(ref))
            for (stage, _, end), ref in zip(STAGES, stage_refs)
        ],
    ))
    print(f"  added quest '{QUEST_TAG}' ({len(STAGES)} stages)")

    for i, (key, _display) in enumerate(RECRUITS):
        jrl.quests.append(JRLQuest(
            name=LocalizedString(recruit_refs[2 * i]),
            planet_id=-1,
            priority=JRLQuestPriority.LOWEST,
            tag=f"{RECRUIT_QUEST_PREFIX}{key}",
            # end=True: a finished quest, filed under Completed in the journal.
            entries=[JRLEntry(end=True, entry_id=RECRUIT_STAGE,
                              text=LocalizedString(recruit_refs[2 * i + 1]))],
        ))
    print(f"  added {len(RECRUITS)} recruit quests ({RECRUIT_QUEST_PREFIX}*)")

    for i, (key, _display) in enumerate(RECRUITS):
        jrl.quests.append(JRLQuest(
            name=LocalizedString(crew_refs[3 * i]),
            planet_id=-1,
            priority=JRLQuestPriority.LOWEST,
            tag=f"{CREW_QUEST_PREFIX}{key}",
            entries=[
                JRLEntry(end=False, entry_id=CREW_ENTITLED, text=LocalizedString(crew_refs[3 * i + 1])),
                JRLEntry(end=True, entry_id=CREW_TRAPPED, text=LocalizedString(crew_refs[3 * i + 2])),
            ],
        ))
    print(f"  added {len(RECRUITS)} crew quests ({CREW_QUEST_PREFIX}*) -> {len(jrl.quests)} total quests")


def build(game_dir: str, dry_run_dir: str | None = None) -> None:
    """dry_run_dir (testing only): read the real install but write nothing
    into it -- dialog.tlk is read from/written to a copy in dry_run_dir and
    the finished global.jrl is written there instead of the repo/Override."""
    tlk_dir = dry_run_dir if dry_run_dir else game_dir
    try:
        stringrefs = _ensure_tlk_strings(tlk_dir, check_running=dry_run_dir is None)
    except GameRunningError as e:
        # Not a failure: nothing was touched, the next Connect with the game
        # closed applies it. The last stdout line is what the client logs.
        print(f"SKIPPED: {e}")
        return

    inst = Installation(game_dir)
    res = inst.resource("global", ResourceType.JRL)
    jrl = construct_jrl(read_gff(res.data))
    print(f"  source: {res.filepath} ({len(jrl.quests)} existing quests)")

    build_quests(jrl, stringrefs)

    gff = dismantle_jrl(jrl, game=Game.K1)
    out_path = os.path.join(dry_run_dir, "global.jrl") if dry_run_dir else os.path.join(RAW_OVERRIDE_DIR, "global.jrl")
    with open(out_path, "wb") as f:
        write_gff(gff, f, ResourceType.JRL)
    print(f"  wrote {out_path} ({os.path.getsize(out_path)} bytes)")

    if dry_run_dir:
        print("  dry run: nothing deployed")
        return
    override_dir = os.path.join(game_dir, "Override")
    shutil.copy2(out_path, os.path.join(override_dir, "global.jrl"))
    print(f"  deployed -> {override_dir}\\global.jrl")


if __name__ == "__main__":
    build(_arg_value("--game-dir", DEFAULT_GAME_DIR), _arg_value("--dry-run-dir", None))
