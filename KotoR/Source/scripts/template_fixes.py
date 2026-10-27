"""
One-field edits of the game's own creature and trigger templates, applied on the player's machine to the player's own copy (see build_game_assets.py).

  tar08_calo082.utc   Taris, Davik's estate: the Calo standing in the corner of the hangar scene has his blow-up dialog as his own conversation,
                      so clicking him plays it out of order and breaks Davik's scene. The scripted start names the dialog itself, so the template
                      loses its Conversation.
  and_mandtrig01.utt  Dantooine, Matale Grounds raider ambush trigger: its OnEnter points straight at the preserved original (a short alias, a
                      template's script field is 16 characters), so the engine starts the scene's conversation itself.
  ebo40_carthtlk.utt  Leviathan, the Carth trigger on the Ebon Hawk: its OnEnter runs ap_lev_trigger (the Leviathan capture scene).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pykotor.resource.formats.gff import read_gff, write_gff

# file name, the module file the vanilla copy is read from, the field, its new value
EDITS = [
    ("tar08_calo082", "utc", "tar_m08aa_s.rim", "Conversation", ""),
    ("and_mandtrig01", "utt", "danm14ab_s.rim", "ScriptOnEnter", "apo_dan14ab_c06"),
    ("ebo40_carthtlk", "utt", "ebo_m40aa_s.rim", "ScriptOnEnter", "ap_lev_trigger"),
]


def edited_templates(game):
    """{file name: bytes}"""
    out = {}
    for resref, extension, module, field, value in EDITS:
        data = game.resource(module, resref, extension)
        if data is None:
            raise FileNotFoundError(f"the game has no {resref}.{extension} in {module}")
        gff = read_gff(data)
        gff.root.set_resref(field, value)
        blob = bytearray()
        write_gff(gff, blob)
        out[f"{resref}.{extension}"] = bytes(blob)
    return out
