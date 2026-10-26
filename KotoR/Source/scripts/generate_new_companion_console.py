"""
New Companion console (0.2.0, FutureDesign.md "2. New Companion"): a computer terminal in the Ebon Hawk's main hold, between HK-47's spot and the swoop pod,
that swaps who travels in HK-47's party slot or in T3-M4's. HK-47 and T3-M4 stay the defaults; with the console the player can put Meetra Surik, Darth Malak,
Calo Nord, Yuthura Ban, Darth Bandon or Trask Ulgo (templates from generate_new_companion_assets.py) in either slot, and the original back at any time.

  - The unlock is the plot item ap_nc_console, delivered by the AP item "Ebon Hawk: New Companion Selection" (give_item:ap_nc_console).
    The Hawk's entry script places the terminal once the player holds it (generate_trampoline_batch.py AREA_PERMANENT_SPAWNS).
  - The first screen asks whose place a new companion should take. A slot is offered only once its companion has joined (IsAvailableCreature):
    until then the terminal says there is nobody to replace yet.
  - A swap removes the current character from the slot and creates the chosen one there with a fresh template (the slot's Tag and NPC slot stay as
    they were: HK47 / NPC_HK_47 or t3m4 / NPC_T3_M4). The tag is baked into a template and cannot be set when an object is created, so each character
    has a second template (resref + _t3, tag t3m4) for T3-M4's slot. If the old one was in the party the new one joins it; otherwise the new one stands
    at the slot's place on the ship. Level, gear and feats of the old character are not carried over (each swap creates a new character).
  - The current character of a slot is recognised by name (GetName), so no extra state is stored. A character already in either slot is not offered
    for the other, so one character is never in both.

Files written to extender/scripts_src (sources, compiled scripts, dialog, terminal template) and extender/raw_override_files (static files for
packaging). Nothing goes to the game's Override unless --deploy is given.
"""
import argparse
import json
import os
import subprocess
import sys

from pykotor.extract.installation import Installation
from pykotor.resource.type import ResourceType
from pykotor.resource.formats.gff import read_gff, write_gff
from pykotor.resource.generics.uti import construct_uti, dismantle_uti
from pykotor.resource.generics.utp import construct_utp, dismantle_utp
from pykotor.resource.generics.dlg import DLG, DLGEntry, DLGReply, DLGLink, dismantle_dlg
from pykotor.common.language import LocalizedString
from pykotor.common.misc import ResRef, Game

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nwnnsscomp_path import resolve_nwnnsscomp  # noqa: E402 -- see that module's docstring

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
SRC_DIR = os.path.join(REPO_ROOT, "extender", "scripts_src")
RAW_DIR = os.path.join(REPO_ROOT, "extender", "raw_override_files")
MANIFEST_PATH = os.path.join(SRC_DIR, "_newcompanion_console_manifest.json")

CONSOLE_ITEM = "ap_nc_console"
TERMINAL = "ap_nc_term"
DLG_RESREF = "ap_nc_dlg"
CUSTOM_STATUS = 9013
ITEM_BASE = "g_i_datapad001"
# The terminal is a clone of the computer terminal in the Endar Spire's Starboard Section (end_comp02, the security computer, in end_m01ab_s.rim): the same template
# (appearance 23, the computer panel; faction 2; useable), with its conversation and its "when used" script swapped for ours. That terminal's own script,
# k_pend_comp07, ends in ActionStartConversation(GetLastUsedBy(), "", FALSE, CONVERSATION_TYPE_COMPUTER, FALSE). An earlier version copied the invisible galaxy map
# helper and changed its model; clicking that never reached its script.
TERMINAL_BASE = "end_comp02"
TERMINAL_MODULE_ARCHIVE = "end_m01ab_s.rim"
# The characters that can take a slot's place: key -> (template for HK-47's slot, label shown, a part of GetName that identifies the character).
CHARACTERS = {
    "meetra": ("p_meetra", "Meetra Surik", "Meetra"),
    "malak": ("p_malak", "Darth Malak", "Malak"),
    "calo": ("p_calo", "Calo Nord", "Calo"),
    "yuthura": ("p_yuthura", "Yuthura Ban", "Yuthura"),
    "bandon": ("p_bandon", "Darth Bandon", "Bandon"),
    "trask": ("p_trask", "Trask Ulgo", "Trask"),
}
# The two slots. A character's template for T3-M4's slot is its HK-47 template + suffix (generate_new_companion_assets.py writes both).
# cond / swap: the prefix of the dialog's condition and swap script names (kept under 16 characters with the longest key, "yuthura").
SLOTS = {
    "hk47": {"npc": "NPC_HK_47", "tag": "HK47", "spot": "pebn_hk47", "label": "HK-47", "original": "p_hk47", "suffix": "",
             "cond": "ap_nc_c_", "swap": "ap_nc_s_", "ok": "ap_nc_hk_ok", "greet": "ap_nc_greet"},
    "t3m4": {"npc": "NPC_T3_M4", "tag": "t3m4", "spot": "pebn_t3m4", "label": "T3-M4", "original": "p_t3m4", "suffix": "_t3",
             "cond": "ap_nc_ct_", "swap": "ap_nc_st_", "ok": "ap_nc_t3_ok", "greet": "ap_nc_greett"},
}
NWNNSSCOMP = resolve_nwnnsscomp()
_COMPILED = []


def _occupant(slot):
    return f'GetName(GetObjectByTag("{SLOTS[slot]["tag"]}"))'


def _is_character(slot, key):
    """NWScript for 'the character in this slot is <key>'."""
    return f'FindSubString({_occupant(slot)}, "{CHARACTERS[key][2]}") >= 0'


def _is_original(slot):
    """NWScript for 'the slot holds its own companion': nobody from CHARACTERS."""
    return " && ".join(f'FindSubString({_occupant(slot)}, "{c[2]}") < 0' for c in CHARACTERS.values())


def _in_any_slot(key):
    return " || ".join(_is_character(slot, key) for slot in SLOTS)


def write_and_compile(resref, source, deploy_dir):
    nss_path = os.path.join(SRC_DIR, f"{resref}.nss")
    ncs_path = os.path.join(SRC_DIR, f"{resref}.ncs")
    with open(nss_path, "w") as f:
        f.write(source)
    before = os.path.getmtime(ncs_path) if os.path.exists(ncs_path) else None
    result = subprocess.run([NWNNSSCOMP, "-c", nss_path, "-o", ncs_path], capture_output=True, text=True, cwd=SRC_DIR, timeout=30)
    if not os.path.exists(ncs_path) or os.path.getmtime(ncs_path) == before:
        print(f"  COMPILE FAILED: {resref}\n{result.stdout}\n{result.stderr}")
        return False
    with open(ncs_path, "rb") as f:
        data = f.read()
    for d in (RAW_DIR, deploy_dir):
        if d:
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, f"{resref}.ncs"), "wb") as f:
                f.write(data)
    _COMPILED.append(resref)
    print(f"  compiled {resref}.ncs")
    return True


_SWAP_FUNC = """void SwapSlot(int nNpc, string sTag, string sSpot, string sTemplate)
{
    object oPC = GetPCSpeaker();
    if (!GetIsObjectValid(oPC)) oPC = GetFirstPC();
    object oOld = GetObjectByTag(sTag);
    int bInParty = IsNPCPartyMember(nNpc);
    location lLoc = GetLocation(oPC);
    object oSpot = GetWaypointByTag(sSpot);
    if (!bInParty && GetIsObjectValid(oSpot)) lLoc = GetLocation(oSpot);
    RemovePartyMember(nNpc);
    RemoveAvailableNPC(nNpc);
    if (GetIsObjectValid(oOld)) DestroyObject(oOld);
    AddAvailableNPCByTemplate(nNpc, sTemplate);
    object oNew = CreateObject(OBJECT_TYPE_CREATURE, sTemplate, lLoc);
    if (bInParty) AddPartyMember(nNpc, oNew);
    SetNPCSelectability(nNpc, TRUE);
    KSE_Diag(206, "AP|APPLIED|newcompanion_swap|template=" + sTemplate + "|inParty=" + IntToString(bInParty) + "|valid=" + IntToString(GetIsObjectValid(oNew)) + "|slot=" + sTag);
}
"""


def _cond(resref, body, deploy_dir):
    return write_and_compile(resref, f'#include "kse"\n\nint StartingConditional()\n{{\n    {body}\n}}\n', deploy_dir)


def build_scripts(deploy_dir):
    ok = True
    # What the Endar Spire's security computer runs at the end of k_pend_comp07: the terminal starts a computer conversation with whoever used it. The log line
    # shows that a click reached this script.
    ok &= write_and_compile("ap_nc_use", '#include "kse"\n\nvoid main()\n{\n    KSE_Diag(206, "AP|NCTERM|used");\n'
                            '    ActionStartConversation(GetLastUsedBy(), "", FALSE, CONVERSATION_TYPE_COMPUTER, FALSE);\n}\n', deploy_dir)
    # first screen: which slots are there to offer
    ok &= _cond("ap_nc_ready", "return IsAvailableCreature(NPC_HK_47) || IsAvailableCreature(NPC_T3_M4);", deploy_dir)
    ok &= _cond("ap_nc_notyet", "return !(IsAvailableCreature(NPC_HK_47) || IsAvailableCreature(NPC_T3_M4));", deploy_dir)
    for slot, info in SLOTS.items():
        ok &= _cond(info["ok"], f"return IsAvailableCreature({info['npc']});", deploy_dir)
        # Condition on every link into the slot's menu: who is there now. A condition runs before the line it guards is shown, so the text has the
        # current name (an entry's own action script is not guaranteed to run before its text is drawn).
        who = "".join(f'    if ({_is_character(slot, key)}) sWho = "{label}";\n' for key, (_t, label, _f) in CHARACTERS.items())
        ok &= write_and_compile(info["greet"], f'''#include "kse"

int StartingConditional()
{{
    string sWho = "{info['label']}";
{who}    SetCustomToken({CUSTOM_STATUS}, "In {info['label']}'s place now: " + sWho + ".");
    return TRUE;
}}
''', deploy_dir)
        # one option per character: shown only while that character is in neither slot; one for the slot's own companion, shown while someone else is there
        for key, (template, _label, _frag) in CHARACTERS.items():
            ok &= _cond(info["cond"] + key, f"return !({_in_any_slot(key)});", deploy_dir)
            ok &= write_and_compile(info["swap"] + key, f'#include "kse"\n\n{_SWAP_FUNC}\nvoid main()\n{{\n    SwapSlot({info["npc"]}, "{info["tag"]}", "{info["spot"]}", "{template + info["suffix"]}");\n}}\n', deploy_dir)
        ok &= _cond(info["cond"] + slot, f"return !({_is_original(slot)});", deploy_dir)
        ok &= write_and_compile(info["swap"] + slot, f'#include "kse"\n\n{_SWAP_FUNC}\nvoid main()\n{{\n    SwapSlot({info["npc"]}, "{info["tag"]}", "{info["spot"]}", "{info["original"]}");\n}}\n', deploy_dir)
    return ok


def _entry(text):
    e = DLGEntry()
    e.text = LocalizedString.from_english(text)
    e.plot_index = -1
    e.speaker = ""
    return e


def _reply(text):
    r = DLGReply()
    r.text = LocalizedString.from_english(text)
    r.plot_index = -1
    return r


def _link(node, active=None):
    link = DLGLink(node)
    if active:
        link.active1 = ResRef(active)
    return link


def build_dlg():
    dlg = DLG()
    # Skippable: the player can click through a line. Left off (the default) every line has to run out its reading time, which is what made these menus slow.
    dlg.skippable = True
    which = _entry("Whose place should another companion take?")
    not_yet = _entry("There is nobody to replace yet. Neither HK-47 nor T3-M4 has joined you.")
    for slot, info in SLOTS.items():
        menu = _entry(f"Choose who travels with you in {info['label']}'s place. <CUSTOM{CUSTOM_STATUS}> Swapping does not carry over gear or levels: take the current companion's gear off first. Darth Bandon cannot wear body armor or robes; his end-game armor is built in.")
        again = _reply("")
        again.links.append(_link(menu, info["greet"]))
        options = [(slot, info["original"], info["label"])] + [(key, template + info["suffix"], label) for key, (template, label, _f) in CHARACTERS.items()]
        for key, _template, label in options:
            pick = _reply(f"Travel with {label}.")
            done = _entry(f"{label} is back with you." if key == slot else f"{label} now travels with you in {info['label']}'s place.")
            done.script1 = ResRef(info["swap"] + key)
            done.links.append(_link(again))
            pick.links.append(_link(done))
            menu.links.append(_link(pick, info["cond"] + key))
        other = _reply("Replace a different companion.")
        other.links.append(_link(which))
        menu.links.append(_link(other))
        menu.links.append(_link(_reply("Never mind.")))
        choose = _reply(f"In {info['label']}'s place.")
        choose.links.append(_link(menu, info["greet"]))
        which.links.append(_link(choose, info["ok"]))
    which.links.append(_link(_reply("Never mind.")))
    dlg.starters.append(_link(which, "ap_nc_ready"))
    dlg.starters.append(_link(not_yet, "ap_nc_notyet"))
    return dlg


def build_item(installation):
    """The unlock item: a plot item (it cannot be sold, dropped or destroyed) that makes the Hawk's entry script place the terminal. It is not used itself:
    an attempt to make it a hotbar item never fired its spell in the game."""
    src = installation.resource(ITEM_BASE, ResourceType.UTI)
    if src is None:
        sys.exit(f"vanilla {ITEM_BASE}.uti not found -- is --game-dir a real KOTOR install?")
    uti = construct_uti(read_gff(src.data))
    uti.resref = ResRef(CONSOLE_ITEM)
    uti.tag = CONSOLE_ITEM
    uti.name = LocalizedString.from_english("Ebon Hawk: New Companion Selection")
    uti.description = LocalizedString.from_english(
        "Unlocks the New Companion console in the Ebon Hawk's main hold, between HK-47 and the swoop racing pod: swap HK-47 or T3-M4 for another companion. Can't be sold, dropped, or destroyed.")
    uti.plot = 1
    uti.stack_size = 1
    data = bytearray()
    write_gff(dismantle_uti(uti), data)
    return bytes(data)


def build_terminal(game_dir):
    from pykotor.resource.formats.rim import read_rim
    archive = os.path.join(game_dir, "modules", TERMINAL_MODULE_ARCHIVE)
    src = next((x for x in read_rim(archive) if x.restype == ResourceType.UTP and x.resref.get().lower() == TERMINAL_BASE), None)
    if src is None:
        sys.exit(f"{TERMINAL_BASE}.utp not found in {archive} -- is --game-dir a real KOTOR install?")
    utp = construct_utp(read_gff(src.data))
    utp.resref = ResRef(TERMINAL)
    utp.tag = TERMINAL
    utp.name = LocalizedString.from_english("New Companion Console")
    utp.comment = "New Companion console (a clone of the Endar Spire security computer)"
    utp.conversation = ResRef(DLG_RESREF)
    utp.on_used = ResRef("ap_nc_use")   # starts the conversation (ap_nc_dlg) with whoever used the terminal
    data = bytearray()
    write_gff(dismantle_utp(utp), data)
    return bytes(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--game-dir", default=DEFAULT_GAME_DIR)
    parser.add_argument("--deploy", action="store_true", help="also copy the generated files to <game-dir>\\Override")
    args = parser.parse_args()
    deploy_dir = os.path.join(args.game_dir, "Override") if args.deploy else None
    os.makedirs(RAW_DIR, exist_ok=True)

    print("Building scripts...")
    if not build_scripts(deploy_dir):
        sys.exit("ABORT: a script failed to compile.")
    installation = Installation(args.game_dir)
    files = {}
    data = bytearray()
    write_gff(dismantle_dlg(build_dlg(), Game.K1), data)
    files[f"{DLG_RESREF}.dlg"] = bytes(data)
    files[f"{CONSOLE_ITEM}.uti"] = build_item(installation)
    files[f"{TERMINAL}.utp"] = build_terminal(args.game_dir)
    for name, blob in files.items():
        for d in (SRC_DIR, RAW_DIR, deploy_dir):
            if d:
                os.makedirs(d, exist_ok=True)
                with open(os.path.join(d, name), "wb") as f:
                    f.write(blob)
        print(f"  wrote {name} ({len(blob)} bytes)")
    raw_files = sorted(list(files) + [f"{r}.ncs" for r in _COMPILED])
    with open(MANIFEST_PATH, "w", encoding="utf8") as f:
        json.dump({"scripts": sorted(_COMPILED), "raw_files": raw_files}, f, indent=1)
    print(f"Wrote manifest: {len(_COMPILED)} scripts, {len(raw_files)} files.")
    print(f"Deployed to {deploy_dir}." if deploy_dir else "Not deployed (no --deploy).")


if __name__ == "__main__":
    main()
