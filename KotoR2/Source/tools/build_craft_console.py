"""Builds the Crafting Console item (assets/k2se_craft.uti) and its menu (assets/k2se_craft.dlg).

The item is a copy of the Roster Console (tools-built earlier, assets/k2se_roster.uti) that casts spell row 85, an unused plot
leftover whose impact script is k_ptat_sandper, so using the item runs nss/k_ptat_sandper.nss. The menu is a one-entry dialogue
whose text comes from custom tokens set by that script, with four replies: create or break down items, upgrade an item, chemical lab, close.
"""
import os
import sys

from pykotor.common.language import LocalizedString
from pykotor.resource.formats.gff import read_gff, write_gff
from pykotor.resource.generics.dlg import DLG, DLGEntry, DLGLink, DLGReply, dismantle_dlg, read_dlg
from pykotor.resource.generics.uti import construct_uti, dismantle_uti

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")


def build_item():
    with open(os.path.join(ASSETS, "k2se_roster.uti"), "rb") as f:
        gff = read_gff(f.read())
    uti = construct_uti(gff)
    uti.resref = type(uti.resref)("k2se_craft")
    uti.tag = "k2se_craft"
    uti.name = LocalizedString.from_english("Crafting Console")
    uti.description = LocalizedString.from_english("Opens the crafting menu: the workbench (create, break down, upgrade) or the chemical lab. Never used up.")
    for prop in uti.properties:
        prop.subtype = 85          # spells.2da row 85: impact script k_ptat_sandper
    out = os.path.join(ASSETS, "k2se_craft.uti")
    write_gff(dismantle_uti(uti), out)
    return out


def build_menu():
    # Copy the roster menu (known to work) and replace its nodes, so every file-level field stays what the game accepted.
    with open(os.path.join(ASSETS, "k2se_roster.dlg"), "rb") as f:
        dlg = read_dlg(f.read())
    entry = dlg.starters[0].node
    entry.text = LocalizedString.from_english("<CUSTOM9220>")
    template = entry.links[0].node
    entry.links.clear()
    # The first three replies show only when the seed's crafting switches allow them (the client writes ap_craft_bench / ap_craft_up / ap_craft_lab).
    for i, (script, condition) in enumerate([("k2se_cwb", "k2se_cok_bench"), ("k2se_cup", "k2se_cok_up"), ("k2se_clab", "k2se_cok_lab"), ("", "")]):
        reply = DLGReply()
        reply.text = LocalizedString.from_english("<CUSTOM%d>" % (9221 + i))
        reply.script1 = type(template.script1)(script)
        reply.plot_index = -1
        reply.camera_id = getattr(template, "camera_id", -1)
        link = DLGLink(reply)
        if condition:
            link.active1 = type(template.script1)(condition)
        entry.links.append(link)
    out = os.path.join(ASSETS, "k2se_craft.dlg")
    write_gff(dismantle_dlg(dlg), out)
    return out


if __name__ == "__main__":
    print(build_item())
    print(build_menu())
