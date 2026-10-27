"""
Companion feat training (0.2.0, FutureDesign.md "1. Additional Feats becomes a training dialog").

Each of the seven companions gets a dialog option that trains them in a feat for credits. The option appears once the companion's
"Additional Feats Character: <name>" item has been received (the plot item ap_ft_<key>, delivered by a plain give_item); nothing is
queued, drawn at random, or retried.

How it reaches the dialog without editing the companions' hundreds of story nodes: each companion's conversation file gets one new
FIRST starter. While the companion has the unlock item (and the player is not in combat) that starter shows a short menu:
    "Train in a new feat." / "Let's talk." / "Never mind."
"Let's talk." links to exactly the starters the file had before (same entries, same conditions), so the conversation continues as
it always did. A companion without the item, or in combat, behaves exactly as before. Edits are made on the raw GFF (new nodes are
appended and one starter inserted), so every other byte of the vanilla file is kept.

Training:
  - The picker lists the feats the companion does not know, from the 18 feats of the old Additional Feats pool (FEATS below): the 11 passive ones the Archipelago Vendor offers, plus the 7 active/toggle ones (Power Attack, Power Blast,
    Flurry, Rapid Shot, Critical Strike, Sniper Shot, Force Jump). The Vendor's notes record one test in which a granted active feat was
    missing from the saved feat list and did not work in combat; that did not hold for companions: a live test (2026-10-25) showed the active feats
    work when trained here (ACTIVE_FEATS marks them). Force Jump, Force Focus and Force Immunity: Fear show only for a companion with Force levels.
  - Not available on the Ebon Hawk: the menu does not show in a module whose name starts with ebo_ (the Hawk and its Leviathan variants).
  - Price: 1,000 credits for a companion's first feat, +2,000 for each feat that companion has already been trained in. The count lives
    in the save as a plot receipt (ap_fn_<key>, one per training), so a reload restores credits and count together.
  - Credits are taken only after the feat reads back as acquired (KSE_GetFeatAcquired in the same script pass). A full feat array
    (the extender refuses the grant) charges nothing and the companion says so.
  - The scripts are shared by all seven: they find the companion by the tag of the conversation owner.

Files: extender/scripts_src (sources and compiled scripts), extender/raw_override_files (the seven patched dialogs and the 14 items).
Bases: a companion's dialog is built from extender/dialog_bases/<resref>.dlg when present (Juhani's, which the project already ships
changed), otherwise from the game's own file. Nothing goes to the game's Override unless --deploy is given.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

from pykotor.extract.installation import Installation, SearchLocation
from pykotor.resource.type import ResourceType
from pykotor.resource.formats.gff import GFFList, GFFStruct, read_gff, write_gff
from pykotor.resource.generics.utc import construct_utc
from pykotor.resource.generics.uti import construct_uti, dismantle_uti
from pykotor.common.language import LocalizedString
from pykotor.common.misc import ResRef

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nwnnsscomp_path import resolve_nwnnsscomp, compile_nss  # noqa: E402 -- see that module's docstring

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
SRC_DIR = os.path.join(REPO_ROOT, "extender", "scripts_src")
RAW_DIR = os.path.join(REPO_ROOT, "extender", "raw_override_files")
BASES_DIR = os.path.join(REPO_ROOT, "extender", "dialog_bases")
MANIFEST_PATH = os.path.join(SRC_DIR, "_feat_training_manifest.json")

# key -> (creature template, object tag as the conversation owner)
COMPANIONS = {
    "bastila": ("p_bastilla", "Bastila"),
    "canderous": ("p_cand", "Cand"),
    "carth": ("p_carth", "Carth"),
    "jolee": ("p_jolee", "Jolee"),
    "juhani": ("p_juhani", "Juhani"),
    "mission": ("p_mission", "Mission"),
    "zaalbar": ("p_zaalbar", "Zaalbar"),
}
# (feat.2da id, name, needs Force levels): the old Additional Feats pool; the first 11 are the Archipelago Vendor's passive feats.
FEATS = [
    (40, "Weapon Proficiency: Blaster Rifle", False),
    (42, "Weapon Proficiency: Heavy Weapons", False),
    (43, "Weapon Proficiency: Lightsaber", False),
    (4, "Armor Proficiency: Heavy", False),
    (5, "Armor Proficiency: Light", False),
    (6, "Armor Proficiency: Medium", False),
    (14, "Implant Level 1", False),
    (60, "Sneak Attack I", False),
    (104, "Scoundrel's Luck", False),
    (88, "Force Focus", True),
    (98, "Force Immunity: Fear", True),
    # active / toggle feats (see the module docstring: to be tested on companions)
    (28, "Power Attack", False),
    (29, "Power Blast", False),
    (11, "Flurry", False),
    (30, "Rapid Shot", False),
    (8, "Critical Strike", False),
    (31, "Sniper Shot", False),
    (101, "Force Jump", True),
]
ACTIVE_FEATS = {28, 29, 11, 30, 8, 31, 101}
MARKER_TEXT = "ap_feat_training"   # in the Comment of every node added here, so a patched file is never taken for a project base
MARKER = MARKER_TEXT.encode()
FIRST_PRICE = 1000
PRICE_STEP = 2000
CUSTOM_PRICE = 9021
CUSTOM_RESULT = 9022
ITEM_BASE = "g_i_datapad001"
UNLOCK_ITEM = "ap_ft_{key}"      # delivered by the AP item
RECEIPT_ITEM = "ap_fn_{key}"     # one per training; its stack size is the number trained

NWNNSSCOMP = resolve_nwnnsscomp()
_COMPILED = []

_HELPERS = """string KeyOf(object oNPC)
{
    string sTag = GetTag(oNPC);
    if (sTag == "Bastila") return "bastila";
    if (sTag == "Cand") return "canderous";
    if (sTag == "Carth") return "carth";
    if (sTag == "Jolee") return "jolee";
    if (sTag == "Juhani") return "juhani";
    if (sTag == "Mission") return "mission";
    if (sTag == "Zaalbar") return "zaalbar";
    return "";
}

int TrainedCount(object oPC, string sKey)
{
    object oReceipt = GetItemPossessedBy(oPC, "ap_fn_" + sKey);
    if (!GetIsObjectValid(oReceipt)) return 0;
    return GetItemStackSize(oReceipt);
}

int PriceFor(int nTrained)
{
    return %(first)d + %(step)d * nTrained;
}

int HasForceLevels(object oNPC)
{
    return GetLevelByClass(CLASS_TYPE_JEDIGUARDIAN, oNPC) + GetLevelByClass(CLASS_TYPE_JEDICONSULAR, oNPC) + GetLevelByClass(CLASS_TYPE_JEDISENTINEL, oNPC) > 0;
}
""" % {"first": FIRST_PRICE, "step": PRICE_STEP}


def _argparser():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--game-dir", default=DEFAULT_GAME_DIR)
    p.add_argument("--deploy", action="store_true", help="also copy the generated files to <game-dir>\\Override")
    return p


def write_and_compile(resref, source, deploy_dir):
    nss_path = os.path.join(SRC_DIR, f"{resref}.nss")
    ncs_path = os.path.join(SRC_DIR, f"{resref}.ncs")
    with open(nss_path, "w") as f:
        f.write(source)
    before = os.path.getmtime(ncs_path) if os.path.exists(ncs_path) else None
    result = compile_nss(nss_path, ncs_path, cwd=SRC_DIR, timeout=30)
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
    return True


def build_scripts(deploy_dir):
    ok = True
    # The first starter: the unlock item is held, the player is not in combat (the vanilla "focused on the nearby enemy" line keeps its place),
    # and the module is not the Ebon Hawk or one of its variants (module names starting ebo_).
    ok &= write_and_compile("ap_ftr_front", f'''#include "kse"

{_HELPERS}
int StartingConditional()
{{
    object oPC = GetPCSpeaker();
    string sKey = KeyOf(OBJECT_SELF);
    if (sKey == "") return FALSE;
    if (GetIsInCombat(oPC)) return FALSE;
    if (GetStringLeft(GetStringLowerCase(GetModuleFileName()), 4) == "ebo_") return FALSE;
    return GetIsObjectValid(GetItemPossessedBy(oPC, "ap_ft_" + sKey));
}}
''', deploy_dir)
    # The price line and what has been done so far (a reply's action: a custom token shows what was set before its entry appears).
    ok &= write_and_compile("ap_ftp_greet", f'''#include "kse"

{_HELPERS}
void main()
{{
    object oPC = GetPCSpeaker();
    string sKey = KeyOf(OBJECT_SELF);
    int nTrained = TrainedCount(oPC, sKey);
    SetCustomToken({CUSTOM_PRICE}, "Which feat? The next one costs " + IntToString(PriceFor(nTrained)) + " credits (" + IntToString(nTrained) + " trained so far).");
}}
''', deploy_dir)
    for feat, name, force in FEATS:
        force_check = "    if (!HasForceLevels(OBJECT_SELF)) return FALSE;\n" if force else ""
        ok &= write_and_compile(f"ap_ftc_{feat}", f'''#include "kse"

{_HELPERS}
int StartingConditional()
{{
{force_check}    return !KSE_GetFeatAcquired({feat}, OBJECT_SELF);
}}
''', deploy_dir)
        ok &= write_and_compile(f"ap_ftd_{feat}", f'''#include "kse"

{_HELPERS}
void Say(string sText)
{{
    SetCustomToken({CUSTOM_RESULT}, sText);
}}

void main()
{{
    object oPC = GetPCSpeaker();
    string sKey = KeyOf(OBJECT_SELF);
    string sName = GetName(OBJECT_SELF);
    if (sKey == "") {{ Say("Something went wrong: this is not one of the crew."); return; }}
    if (KSE_GetFeatAcquired({feat}, OBJECT_SELF)) {{ Say(sName + " already knows {name}."); return; }}
    int nTrained = TrainedCount(oPC, sKey);
    int nPrice = PriceFor(nTrained);
    if (GetGold(oPC) < nPrice) {{ Say("Training {name} costs " + IntToString(nPrice) + " credits, and you do not have enough."); return; }}
    KSE_GrantFeatArrayA({feat}, OBJECT_SELF);
    if (!KSE_GetFeatAcquired({feat}, OBJECT_SELF))
    {{
        Say(sName + " cannot take on {name}: there is no room left for another feat. You were not charged.");
        KSE_Diag(207, "AP|APPLIED|feat_training_refused|key=" + sKey + "|feat={feat}");
        return;
    }}
    int nAfter = KSE_SetCredits(oPC, GetGold(oPC) - nPrice);
    CreateItemOnObject("ap_fn_" + sKey, oPC, 1);
    Say(sName + " has learned {name}. That cost " + IntToString(nPrice) + " credits.");
    KSE_Diag(208, "AP|APPLIED|feat_training|key=" + sKey + "|feat={feat}|price=" + IntToString(nPrice) + "|creditsAfter=" + IntToString(nAfter) + "|count=" + IntToString(nTrained + 1));
}}
''', deploy_dir)
    return ok


# ---- raw DLG helpers --------------------------------------------------------------------------------------------------------------
_ENTRY_TEMPLATE = (("Speaker", "string", ""), ("Text", "text", None), ("VO_ResRef", "resref", ""), ("Script", "resref", ""), ("Delay", "uint32", 0xFFFFFFFF),
                   ("Comment", "string", MARKER_TEXT), ("Sound", "resref", ""), ("Quest", "string", ""), ("PlotIndex", "int32", -1),
                   ("PlotXPPercentage", "single", 1.0), ("Listener", "string", ""), ("WaitFlags", "uint32", 0), ("CameraAngle", "uint32", 0),
                   ("FadeType", "uint8", 0), ("SoundExists", "uint8", 0))
_REPLY_TEMPLATE = tuple(f for f in _ENTRY_TEMPLATE if f[0] not in ("Speaker", "SoundExists"))


def _set(struct, kind, label, value):
    if kind == "string":
        struct.set_string(label, value)
    elif kind == "resref":
        struct.set_resref(label, ResRef(value))
    elif kind == "uint32":
        struct.set_uint32(label, value)
    elif kind == "int32":
        struct.set_int32(label, value)
    elif kind == "single":
        struct.set_single(label, value)
    elif kind == "uint8":
        struct.set_uint8(label, value)
    elif kind == "text":
        struct.set_locstring(label, LocalizedString.from_english(value))


def _new_node(index, template, text, script=""):
    node = GFFStruct(index)
    for label, kind, default in template:
        _set(node, kind, label, text if kind == "text" else (script if label == "Script" else default))
    node.set_list("AnimList", GFFList())
    return node


def _link(position, index, active=""):
    link = GFFStruct(position)
    link.set_uint32("Index", index)
    link.set_resref("Active", ResRef(active))
    link.set_uint8("IsChild", 0)
    return link


def _links(*pairs):
    """A GFFList of link structs from (index, active) pairs, numbered in order."""
    out = GFFList()
    for pos, (index, active) in enumerate(pairs):
        out.append(_link(pos, index, active))
    return out


def inject(root):
    """Adds the training menu to one conversation (raw GFF root). Returns (new first starter's entry index, number of old starters).
    GFFStruct.get_list hands back a copy, so every changed list is put back with set_list."""
    entries = root.get_list("EntryList")
    replies = root.get_list("ReplyList")
    starters = root.get_list("StartingList")
    old = [(starters[i].get_uint32("Index"), str(starters[i].get_resref("Active"))) for i in range(len(starters))]

    e_front = len(entries)
    e_pick = e_front + 1
    e_result = e_front + 2
    r_train = len(replies)
    r_talk = r_train + 1
    r_never = r_train + 2
    r_again = r_train + 3
    r_enough = r_train + 4
    r_feat0 = r_train + 5

    # entries: the front menu, the picker, the result
    front = _new_node(e_front, _ENTRY_TEMPLATE, "What do you need?")
    front.set_list("RepliesList", _links((r_train, ""), (r_talk, ""), (r_never, "")))
    pick = _new_node(e_pick, _ENTRY_TEMPLATE, f"<CUSTOM{CUSTOM_PRICE}>")   # its text is a custom token: set it BEFORE the entry shows, by the reply that leads here
    pick.set_list("RepliesList", _links(*[(r_feat0 + i, f"ap_ftc_{feat}") for i, (feat, _n, _f) in enumerate(FEATS)], (r_never, "")))
    result = _new_node(e_result, _ENTRY_TEMPLATE, f"<CUSTOM{CUSTOM_RESULT}>")
    result.set_list("RepliesList", _links((r_again, ""), (r_enough, "")))
    for node in (front, pick, result):
        entries.append(node)

    # replies
    def reply(index, text, targets, script=""):
        node = _new_node(index, _REPLY_TEMPLATE, text, script=script)
        node.set_list("EntriesList", _links(*targets))
        replies.append(node)

    reply(r_train, "I would like you to train in a new feat.", [(e_pick, "")], script="ap_ftp_greet")
    reply(r_talk, "Let's talk.", old)   # the entries the file started with, under their own conditions
    reply(r_never, "Never mind.", [])          # no entry behind a reply ends the conversation
    reply(r_again, "Train another feat.", [(e_pick, "")], script="ap_ftp_greet")
    reply(r_enough, "That is enough for now.", [])
    for i, (feat, name, _force) in enumerate(FEATS):
        reply(r_feat0 + i, f"Train {name}.", [(e_result, "")], script=f"ap_ftd_{feat}")

    # the new first starter
    starter = GFFStruct(0)
    starter.set_uint32("Index", e_front)
    starter.set_resref("Active", ResRef("ap_ftr_front"))
    starters.insert(0, starter)
    for position in range(len(starters)):
        starters[position].struct_id = position

    root.set_list("EntryList", entries)
    root.set_list("ReplyList", replies)
    root.set_list("StartingList", starters)
    return e_front, len(old)


def base_dialog_bytes(installation, resref):
    base = os.path.join(BASES_DIR, f"{resref}.dlg")
    if os.path.isfile(base):
        with open(base, "rb") as f:
            return f.read(), "base"
    shipped = os.path.join(RAW_DIR, f"{resref}.dlg")
    if os.path.isfile(shipped):
        with open(shipped, "rb") as f:
            shipped_data = f.read()
        if MARKER not in shipped_data:
            # the project ships a changed copy of this file (not one of ours): keep it as the base before overwriting it with the patched one
            os.makedirs(BASES_DIR, exist_ok=True)
            with open(base, "wb") as f:
                f.write(shipped_data)
            return shipped_data, "project copy"
    res = installation.resource(resref, ResourceType.DLG, [SearchLocation.CHITIN])
    if res is None:
        sys.exit(f"{resref}.dlg not found in the game files")
    return res.data, "vanilla"


def build_item(installation, resref, title, description):
    src = installation.resource(ITEM_BASE, ResourceType.UTI)
    if src is None:
        sys.exit(f"vanilla {ITEM_BASE}.uti not found -- is --game-dir a real KOTOR install?")
    uti = construct_uti(read_gff(src.data))
    uti.resref = ResRef(resref)
    uti.tag = resref
    uti.name = LocalizedString.from_english(title)
    uti.description = LocalizedString.from_english(description)
    uti.plot = 1
    uti.stack_size = 99 if resref.startswith("ap_fn_") else 1
    data = bytearray()
    write_gff(dismantle_uti(uti), data)
    return bytes(data)


def main():
    args = _argparser().parse_args()
    deploy_dir = os.path.join(args.game_dir, "Override") if args.deploy else None
    os.makedirs(RAW_DIR, exist_ok=True)
    print("Building scripts...")
    if not build_scripts(deploy_dir):
        sys.exit("ABORT: a script failed to compile.")
    print(f"  compiled {len(_COMPILED)} scripts")

    installation = Installation(args.game_dir)
    files = {}
    for key, (template, _tag) in COMPANIONS.items():
        utc = construct_utc(read_gff(installation.resource(template, ResourceType.UTC).data))
        resref = str(utc.conversation)
        data, source = base_dialog_bytes(installation, resref)
        gff = read_gff(data)
        front, old = inject(gff.root)
        out = bytearray()
        write_gff(gff, out)
        files[f"{resref}.dlg"] = bytes(out)
        print(f"  {key}: {resref}.dlg from {source}: +{3} entries, +{5 + len(FEATS)} replies, 1 new first starter ({old} old starters kept behind \"Let's talk\")")
        title = f"Feat Training: {key.title()}"
        files[f"ap_ft_{key}.uti"] = build_item(installation, UNLOCK_ITEM.format(key=key), title,
                                                 f"Lets {key.title()} be trained in new feats, from {key.title()}'s own conversation. Can't be sold, dropped, or destroyed.")
        files[f"ap_fn_{key}.uti"] = build_item(installation, RECEIPT_ITEM.format(key=key), f"Feat Training Receipt: {key.title()}",
                                                 f"Proof of a feat {key.title()} has been trained in. Can't be sold, dropped, or destroyed.")
    for name, blob in files.items():
        for d in (RAW_DIR, deploy_dir):
            if d:
                os.makedirs(d, exist_ok=True)
                with open(os.path.join(d, name), "wb") as f:
                    f.write(blob)
    raw_files = sorted(list(files) + [f"{r}.ncs" for r in _COMPILED])
    with open(MANIFEST_PATH, "w", encoding="utf8") as f:
        json.dump({"scripts": sorted(_COMPILED), "raw_files": raw_files}, f, indent=1)
    print(f"Wrote {len(files)} files and the manifest ({len(_COMPILED)} scripts).")
    print(f"Deployed to {deploy_dir}." if deploy_dir else "Not deployed (no --deploy).")


if __name__ == "__main__":
    main()
