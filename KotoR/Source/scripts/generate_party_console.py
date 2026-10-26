"""
Builds the Party Console: an inventory item that, when used, opens a one-question dialog whose answer opens the
party selection screen.

How the pieces connect (the item cannot run a script by its tag; a CastSpell property can):
  ap_partycon_a.uti      the item: a copy of the vanilla datapad (g_i_datapad001) as a plot item, base item 64 (Plot_Useable_Items), one CastSpell
                         property (itempropdef row 10) naming spells.2da row 132 with the Unlimited_Use cost (iprp_chargecost row 13) so using it never
                         consumes it. This is the build that ran from the hotbar in the game. Items built on the medpac base item (53) never ran the
                         spell (nothing was logged when they were used), whether or not they were plot items: do not use that base item.
  spells.2da row 132     a copy of the vanilla usable plot spell row 109 (user-targeted; a medpac-style row asks for a target and the item then does
                         nothing) with the impactscript ap_party_console; on a player's machine patch_party_console.py makes the row
  ap_party_console.ncs   the impact script: starts the dialog ap_party_con with the player as speaker, or refuses with a message
                         in BLOCKED_MODULES (the Taris cantina and its Duel Ring arena, the Korriban star map tomb, the Malak fight)
  ap_party_con.dlg       "Party Console." -> "Change your active party." (runs ap_pc_open) / "No change." (closes)
  ap_pc_open.ncs         opens the party selection screen shortly after the dialog closes; its exit script is ap_pc_done (logs the party size)

Everything is written to extender/scripts_src, extender/raw_override_files and the game's Override folder. spells.2da in the game's
Override is edited in place (a backup, spells.2da.before_partycon, is kept next to it the first time).
The game reads Override at startup, so restart it after running this.

Usage: python generate_party_console.py [--game-dir DIR]
Get the item with the dispatcher:  /ap_apply give_item:ap_partycon_a:1
"""
import argparse
import os
import shutil
import subprocess
import sys

from pykotor.extract.installation import Installation
from pykotor.resource.type import ResourceType
from pykotor.resource.formats.gff import read_gff, write_gff
from pykotor.resource.formats.twoda import read_2da, write_2da
from pykotor.resource.generics.uti import construct_uti, dismantle_uti, UTIProperty
from pykotor.resource.generics.dlg import DLG, DLGEntry, DLGReply, DLGLink, dismantle_dlg
from pykotor.common.language import LocalizedString
from pykotor.common.misc import ResRef, Game

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nwnnsscomp_path import resolve_nwnnsscomp  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(REPO_ROOT, "extender", "scripts_src")
RAW_DIR = os.path.join(REPO_ROOT, "extender", "raw_override_files")

DLG_RESREF = "ap_party_con"
SPELL_ROW = 132
PLOT_SPELL_ROW = 109              # PLOT_LEV_DAMAGE_SPACE_SUIT, a vanilla usable plot spell
ITEM_RESREF = "ap_partycon_a"
PLOT_USEABLE_ITEMS_BASE = 64     # baseitems.2da "Plot_Useable_Items"
UNLIMITED_USE = 13               # iprp_chargecost.2da
# Modules where the console refuses (a message instead of the dialog). Each is a whole module, so this needs no position test:
#   tar_m02ae   Taris Upper City Cantina; the Duel Ring arena is part of this module
#   korr_m39aa  the Korriban tomb with the star map
#   sta_m45ad   Star Forge Viewing Platform, where Malak is fought
BLOCKED_MODULES = ("tar_m02ae", "korr_m39aa", "sta_m45ad")
# Also refused on the Ebon Hawk: every module whose name starts with one of these (ebo_m12aa, the Hawk's main hold, and its other variants).
BLOCKED_PREFIXES = ("ebo_",)
CAST_SPELL_PROPERTY = 10         # itempropdef.2da
CHARGE_COST_TABLE = 3            # iprp_costtable.2da row naming iprp_chargecost

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--game-dir", default=r"C:\Program Files (x86)\Steam\steamapps\common\swkotor")
args = parser.parse_args()
GAME_DIR = args.game_dir
OVERRIDE_DIR = os.path.join(GAME_DIR, "Override")
NWNNSSCOMP = resolve_nwnnsscomp()

SCRIPTS = {
    "ap_party_console": '''#include "kse"

// Impact script of spells.2da row 132: runs when the Party Console item is used.
void main()
{
    KSE_Diag(199, "AP|PARTYCON|ran");
    object oPC = GetFirstPC();
    object oItem = GetSpellCastItem();
    if (!GetIsObjectValid(oItem)) oItem = GetItemActivated();
    KSE_Diag(199, "AP|PARTYCON|used|item=" + GetTag(oItem) + "|valid=" + IntToString(GetIsObjectValid(oItem)));
    string sMod = GetStringLowerCase(GetModuleFileName());
    if (__BLOCKED__)
    {
        KSE_Diag(199, "AP|PARTYCON|refused|mod=" + sMod);
        SetCustomToken(901, "The Party Console cannot be used here.");
        AssignCommand(oPC, ActionStartConversation(oPC, "ap_gate_msg", FALSE, CONVERSATION_TYPE_CINEMATIC, TRUE));
        return;
    }
    AssignCommand(oPC, ActionStartConversation(oPC, "ap_party_con", FALSE, CONVERSATION_TYPE_CINEMATIC, TRUE));
}
''',
    "ap_pc_open": '''#include "kse"

// Action script of the dialog's "open" line. The screen is opened shortly after, once the dialog has closed.
void main()
{
    object oPC = GetFirstPC();
    KSE_Diag(199, "AP|PARTYCON|opening|party=" + IntToString(GetPartyMemberCount()));
    AssignCommand(oPC, DelayCommand(0.6, ShowPartySelectionGUI("ap_pc_done")));
}
''',
    "ap_pc_done": '''#include "kse"

// Exit script of the party selection screen.
void main()
{
    KSE_Diag(199, "AP|PARTYCON|closed|party=" + IntToString(GetPartyMemberCount()));
}
''',
}

SCRIPTS["ap_party_console"] = SCRIPTS["ap_party_console"].replace(
    "__BLOCKED__", " || ".join([f'sMod == "{m}"' for m in BLOCKED_MODULES]
                               + [f'GetStringLeft(sMod, {len(p)}) == "{p}"' for p in BLOCKED_PREFIXES]))


def compile_script(resref, source):
    nss = os.path.join(SRC_DIR, f"{resref}.nss")
    ncs = os.path.join(SRC_DIR, f"{resref}.ncs")
    with open(nss, "w") as f:
        f.write(source)
    before = os.path.getmtime(ncs) if os.path.exists(ncs) else None
    result = subprocess.run([NWNNSSCOMP, "-c", nss, "-o", ncs], capture_output=True, text=True, cwd=SRC_DIR, timeout=30)
    fresh = os.path.exists(ncs) and (before is None or os.path.getmtime(ncs) != before)
    if not fresh or "Error" in result.stdout or "aborted" in result.stdout:
        sys.exit(f"COMPILE FAILED: {resref}\n{result.stdout}\n{result.stderr}")
    shutil.copyfile(ncs, os.path.join(OVERRIDE_DIR, f"{resref}.ncs"))
    print(f"  compiled + deployed {resref}.ncs")


def build_dlg():
    dlg = DLG()
    # Skippable: the player can click through a line. Left off (the default) every line has to run out its reading time, which is what made these menus slow.
    dlg.skippable = True

    def entry(text, script=None):
        e = DLGEntry()
        e.text = LocalizedString.from_english(text)
        e.plot_index = -1          # pykotor defaults to 0, which would award plot XP
        e.speaker = ""             # the owner: here the player
        if script:
            e.script1 = ResRef(script)
        return e

    def reply(text):
        r = DLGReply()
        r.text = LocalizedString.from_english(text)
        r.plot_index = -1
        return r

    greet = entry("Party Console.")
    # blank text: the line is only here to run the script; with text, the line was still on screen when the party screen opened
    # over it and came back after the screen closed
    opening = entry("", "ap_pc_open")
    r_open = reply("Change your active party.")
    r_open.links.append(DLGLink(opening))
    r_exit = reply("No change.")
    greet.links.append(DLGLink(r_open))
    greet.links.append(DLGLink(r_exit))
    dlg.starters.append(DLGLink(greet))
    return dlg


def main():
    installation = Installation(GAME_DIR)
    os.makedirs(RAW_DIR, exist_ok=True)

    print("Scripts...")
    for resref, source in SCRIPTS.items():
        compile_script(resref, source)

    print("Dialog...")
    data = bytearray()
    write_gff(dismantle_dlg(build_dlg(), Game.K1), data)
    for d in (SRC_DIR, RAW_DIR, OVERRIDE_DIR):
        with open(os.path.join(d, f"{DLG_RESREF}.dlg"), "wb") as f:
            f.write(bytes(data))
    print(f"  wrote {DLG_RESREF}.dlg ({len(data)} bytes)")

    print("Item...")
    src = installation.resource("g_i_datapad001", ResourceType.UTI)
    if src is None:
        sys.exit("vanilla g_i_datapad001.uti not found -- is --game-dir a real KOTOR install?")
    uti = construct_uti(read_gff(src.data))
    uti.resref = ResRef(ITEM_RESREF)
    uti.tag = ITEM_RESREF
    uti.base_item = PLOT_USEABLE_ITEMS_BASE
    uti.name = LocalizedString.from_english("Party Console")
    uti.description = LocalizedString.from_english("Use it to choose who travels with you. Can't be sold, dropped, or destroyed.")
    uti.plot = 1
    uti.stack_size = 1
    uti.charges = 0
    prop = UTIProperty()
    prop.property_name = CAST_SPELL_PROPERTY
    prop.subtype = SPELL_ROW
    prop.cost_table = CHARGE_COST_TABLE
    prop.cost_value = UNLIMITED_USE
    prop.param1 = 255
    prop.param1_value = 0
    prop.chance_appear = 100
    uti.properties = [prop]
    data = bytearray()
    write_gff(dismantle_uti(uti), data)
    for d in (RAW_DIR, OVERRIDE_DIR):
        with open(os.path.join(d, f"{ITEM_RESREF}.uti"), "wb") as f:
            f.write(bytes(data))
    print(f"  wrote {ITEM_RESREF}.uti (datapad copy, plot item, base item {PLOT_USEABLE_ITEMS_BASE}, CastSpell row {SPELL_ROW}, unlimited use)")

    print("spells.2da...")
    path = os.path.join(OVERRIDE_DIR, "spells.2da")
    backup = path + ".before_partycon"
    if not os.path.exists(backup):
        shutil.copyfile(path, backup)
        print(f"  backup -> {backup}")
    with open(path, "rb") as f:
        table = read_2da(f.read())
    label = table.get_cell(SPELL_ROW, "label")
    before = table.get_cell(SPELL_ROW, "impactscript")
    if not label.startswith("AP_"):
        sys.exit(f"spells.2da row {SPELL_ROW} is '{label}', not one of ours; refusing to change it.")
    # Row 132 started as the cast-spell spike's row (item targeting blank, like a medpac that asks for a target, and a medpac's
    # category); the item was usable but its script never ran. A vanilla plot spell that runs a script when its item is used (row 109,
    # the Leviathan space suit) targets the user themself, so row 132 becomes a copy of it in every column but its label and script.
    for header in table.get_headers():
        if header in ("label", "impactscript"):
            continue
        table.set_cell(SPELL_ROW, header, table.get_cell(PLOT_SPELL_ROW, header))
    table.set_cell(SPELL_ROW, "impactscript", "ap_party_console")
    out = bytearray()
    write_2da(table, out)
    with open(path, "wb") as f:
        f.write(bytes(out))
    print(f"  row {SPELL_ROW} ({label}): impactscript {before!r} -> 'ap_party_console'")
    # What package_dist.py ships (the spells.2da row is added on a player's machine by patch_party_console.py).
    import json
    manifest = {"scripts": sorted(SCRIPTS), "raw_files": [f"{DLG_RESREF}.dlg", f"{ITEM_RESREF}.uti"]}
    with open(os.path.join(SRC_DIR, "_partycon_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1)
    print("Done. Restart the game, then: /ap_apply give_item:ap_partycon_a:1")


main()
