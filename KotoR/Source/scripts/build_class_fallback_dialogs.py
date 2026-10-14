"""
Builds the two vanilla dialogs a droid PC (class 9) would still stall in, as raw Override files in extender/raw_override_files:

  * m01aa_c01.dlg  -- the Endar Spire opening cutscene picks the PC's stand-in with one starter per body class
    (k_pend_bedtal / bedmed / bedsml / bedtny), none of which is true for a class other than Soldier/Scout/Scoundrel, so the
    scene never starts (the "CutStart" hang). One starter with an empty Active script is added at the end, pointing at the
    same entry as the medium-body starter.
  * k_hjuh_dialog.dlg -- Juhani's "what did you do before that?" question (entry 133) offers only Soldier / Scout / Scoundrel
    answers, so the droid PC gets no answer and the conversation just ends. A fourth answer with no condition is added.

Same technique as the four CutStart fixes already shipped (cut00_convers, k_player_dialog, m12aa_c06, tar02_carth022): an
extra unconditional link, nothing else changed, so every other player sees the original dialog exactly.

  python build_class_fallback_dialogs.py [--game-dir=PATH] [--deploy]
"""
import copy
import os
import shutil
import sys

from pykotor.common.language import LocalizedString
from pykotor.extract.installation import Installation, SearchLocation
from pykotor.resource.formats.gff import read_gff, write_gff
from pykotor.resource.type import ResourceType

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
RAW_OVERRIDE_DIR = os.path.join(REPO_ROOT, "extender", "raw_override_files")

OPENING_BODY_STARTER = "k_pend_bedmed"  # the starter whose target the fallback reuses
JUHANI_ENTRY = 133
JUHANI_REPLY_TO_COPY = 173  # "I was a soldier for the Republic." -- same destination entry as the other two answers
DROID_ANSWER = "I served the Republic as a combat droid."


def _arg(flag, default=None):
    for a in sys.argv[1:]:
        if a.startswith(flag + "="):
            return a.split("=", 1)[1]
    return default


def build_opening(inst):
    res = inst.resource("m01aa_c01", ResourceType.DLG, [SearchLocation.MODULES], module_root="end_m01aa")
    gff = read_gff(res.data)
    starters = gff.root.get_list("StartingList")
    target = next(s for s in starters if str(s.get_resref("Active")) == OPENING_BODY_STARTER)
    assert all(str(s.get_resref("Active")) for s in starters), "m01aa_c01 already has an unconditional starter"
    new = starters.add(len(starters))
    new.set_uint32("Index", target.get_uint32("Index"))
    new.set_resref("Active", "")
    gff.root.set_list("StartingList", starters)  # get_list hands back a copy, so the edited list is stored back
    return gff


def build_juhani(inst):
    gff = read_gff(inst.resource("k_hjuh_dialog", ResourceType.DLG, [SearchLocation.CHITIN]).data)
    entries = gff.root.get_list("EntryList")
    replies = gff.root.get_list("ReplyList")
    links = entries[JUHANI_ENTRY].get_list("RepliesList")
    assert len(links) == 3 and all(str(l.get_resref("Active")) for l in links), "E133 changed shape"
    assert any(l.get_uint32("Index") == JUHANI_REPLY_TO_COPY for l in links)
    reply = copy.deepcopy(replies[JUHANI_REPLY_TO_COPY])
    reply.struct_id = len(replies)
    reply.set_locstring("Text", LocalizedString.from_english(DROID_ANSWER))
    replies.append(reply)
    link = links.add(len(links))
    link.set_uint32("Index", len(replies) - 1)
    link.set_resref("Active", "")
    entries[JUHANI_ENTRY].set_list("RepliesList", links)
    gff.root.set_list("EntryList", entries)
    gff.root.set_list("ReplyList", replies)
    return gff


def main():
    game_dir = _arg("--game-dir", DEFAULT_GAME_DIR)
    inst = Installation(game_dir)
    os.makedirs(RAW_OVERRIDE_DIR, exist_ok=True)
    for name, gff in (("m01aa_c01", build_opening(inst)), ("k_hjuh_dialog", build_juhani(inst))):
        path = os.path.join(RAW_OVERRIDE_DIR, name + ".dlg")
        write_gff(gff, path, ResourceType.DLG)
        print(f"wrote {path}")
        if "--deploy" in sys.argv:
            shutil.copy2(path, os.path.join(game_dir, "Override", name + ".dlg"))
            print(f"  deployed to {game_dir}\\Override")


if __name__ == "__main__":
    main()
