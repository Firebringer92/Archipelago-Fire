"""
Edits of the game's own dialogs, applied on the player's machine to the player's own copy (see build_game_assets.py).

Two kinds of edit:

  * CutStart fixes. A scripted scene picks the PC's stand-in with one conditional link per body size (k_tall, k_medium, k_small, k_tiny, or the
    k_pend_bed* set), and none of them is true for a PC whose base class is not Soldier, Scout or Scoundrel, so the scene never starts and the game hangs at
    a "CutStart" object (jedi_start / jedi_granted, droid PCs). Each fix adds one unconditional link (empty Active script) to the entry that an existing
    conditional link already reaches, nothing else changed, so every other player sees the original dialog exactly.
  * Companion dialogs: Juhani's "what did you do before that?" answer for a droid PC, and the feat training menu on the seven companions
    (generate_feat_training.inject).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pykotor.resource.formats.gff import GFFStruct, read_gff, write_gff
from pykotor.common.misc import ResRef

# resref, the module file the vanilla copy is read from, where the new link goes ("start" or "reply"), the reply index (reply only),
# and the Active script of the existing conditional link whose target the new unconditional link reuses.
CUTSTART_FIXES = [
    ("cut00_convers", "STUNT_00_s.rim", "start", None, "k_tall"),
    ("k_player_dialog", "danm13_s.rim", "reply", 1, "k_tiny"),
    ("m12aa_c06", "STUNT_44_s.rim", "reply", 8, "k_medium"),
    ("m12aa_c06", "STUNT_44_s.rim", "reply", 24, "k_medium"),
    ("tar02_carth022", "tar_m02af_s.rim", "reply", 3, "k_pend_bedtal"),
    ("m01aa_c01", "end_m01aa_s.rim", "start", None, "k_pend_bedmed"),
]


def _add_unconditional(links, active_name):
    """links: a GFFList of link structs (Index, Active). Appends a link with no condition to the target of the one whose Active is active_name."""
    target = next((s.get_uint32("Index") for s in links if str(s.get_resref("Active")) == active_name), None)
    if target is None:
        raise ValueError(f"no link with the condition {active_name!r} to copy the target from")
    if any(not str(s.get_resref("Active")) for s in links):
        raise ValueError("the list already has an unconditional link")
    link = links.add(len(links))
    link.set_uint32("Index", target)
    link.set_resref("Active", "")


def apply_cutstart_fix(data, where, reply_index, active_name):
    gff = read_gff(data)
    root = gff.root
    if where == "start":
        starters = root.get_list("StartingList")
        _add_unconditional(starters, active_name)
        root.set_list("StartingList", starters)
    else:
        replies = root.get_list("ReplyList")
        links = replies[reply_index].get_list("EntriesList")
        _add_unconditional(links, active_name)
        replies[reply_index].set_list("EntriesList", links)
        root.set_list("ReplyList", replies)
    return gff


def cutstart_dialogs(game):
    """{file name: bytes} for the CutStart fixes. A dialog with more than one fix (m12aa_c06) gets all of them."""
    by_resref = {}
    for resref, module, where, reply_index, active in CUTSTART_FIXES:
        if resref in by_resref:
            data = by_resref[resref]
        else:
            data = game.resource(module, resref, "dlg")
            if data is None:
                raise FileNotFoundError(f"the game has no {resref}.dlg in {module}")
        gff = apply_cutstart_fix(data, where, reply_index, active)
        out = bytearray()
        write_gff(gff, out)
        by_resref[resref] = bytes(out)
    return {f"{resref}.dlg": data for resref, data in by_resref.items()}


def juhani_base(game):
    """Juhani's dialog with the droid PC's answer to "what did you do before that?" added (build_class_fallback_dialogs.build_juhani)."""
    import build_class_fallback_dialogs as fb
    gff = fb.build_juhani(game.installation)
    out = bytearray()
    write_gff(gff, out)
    return bytes(out)


def feat_training_dialogs(game):
    """{file name: bytes} for the seven companion dialogs with the feat training menu added."""
    import generate_feat_training as ft
    from pykotor.extract.installation import SearchLocation
    from pykotor.resource.generics.utc import construct_utc
    from pykotor.resource.type import ResourceType
    out = {}
    for key, (template, _tag) in ft.COMPANIONS.items():
        utc = construct_utc(read_gff(game.installation.resource(template, ResourceType.UTC, [SearchLocation.CHITIN]).data))
        resref = str(utc.conversation)
        if resref == "k_hjuh_dialog":
            data = juhani_base(game)
        else:
            res = game.installation.resource(resref, ResourceType.DLG, [SearchLocation.CHITIN])
            if res is None:
                raise FileNotFoundError(f"the game has no {resref}.dlg")
            data = res.data
        gff = read_gff(data)
        ft.inject(gff.root)
        blob = bytearray()
        write_gff(gff, blob)
        out[f"{resref}.dlg"] = bytes(blob)
    return out
