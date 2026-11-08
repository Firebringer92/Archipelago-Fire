"""Game assets the client builds itself, on the player's machine, from nothing but constants: the Crafting Console (item and menu) and the dispatcher's message box.

None of this is copied from the game: the item templates and the menu are written field by field from the values the live tests showed the game accepts (the Roster
Console item that opens a menu through a spell, and the menu with the answers hidden by condition scripts). The files are written into Override with the rest of the
patch, so nothing here is published. docs/FIRST_RUN_BUILD_PLAN.md section 24 has the details.

  k2se_craft.uti   the Crafting Console: a plot item of the "useable plot item" base type that casts spell row 85 (an unused plot leftover whose impact script
                   k_ptat_sandper is ours and opens the menu), never used up
  k2se_craft.dlg   the menu: a header line (<CUSTOM9220>, set by the script) and the replies workbench / upgrade / chemical lab / close, with the three first replies
                   shown only while ap_craft_bench / ap_craft_up / ap_craft_lab allow it (condition scripts k2se_cok_*)
  k2se_msg.dlg     the dispatcher's one-line message box
The story progression items are not assets any more: they are stages of journal quests (client/k2_journal.py).
"""
import typing

CONSOLE_RESREF = "k2se_craft"
MENU_RESREF = "k2se_craft"
MESSAGE_RESREF = "k2se_msg"           # the dispatcher's message box
SPELL_ROW = 85                       # spells.2da row whose impact script is k_ptat_sandper
USEABLE_PLOT_BASE = 64               # baseitems.2da: Plot_Useable_Items
# (answer script, condition script) of the menu's replies, in order; token 9221 + n is the reply's text (the script sets them)
MENU_REPLIES = (("k2se_cwb", "k2se_cok_bench"), ("k2se_cup", "k2se_cok_up"), ("k2se_clab", "k2se_cok_lab"), ("", ""))


def _item(resref: str, name: str, description: str, spell: typing.Optional[int]) -> bytes:
    from pykotor.common.language import LocalizedString
    from pykotor.common.misc import ResRef
    from pykotor.resource.generics.uti import UTI, UTIProperty, dismantle_uti
    from pykotor.resource.formats.gff import bytes_gff
    uti = UTI()
    uti.resref = ResRef(resref)
    uti.tag = resref
    uti.base_item = USEABLE_PLOT_BASE
    uti.name = LocalizedString.from_english(name)
    uti.description = LocalizedString.from_english(description)
    uti.model_variation = 29
    uti.plot = True
    uti.stack_size = 1
    uti.charges = 0
    uti.max_charges = 0
    uti.cost = 40
    uti.add_cost = 40
    uti.palette_id = 5
    if spell is not None:
        prop = UTIProperty()
        prop.property_name = 10         # item_property: cast spell
        prop.subtype = spell
        prop.cost_table = 3
        prop.cost_value = 13            # unlimited uses
        prop.param1 = 255
        prop.param1_value = 0
        prop.upgrade_type = None
        prop.chance_appear = 100
        uti.properties.append(prop)
    return bytes_gff(dismantle_uti(uti))


def console_item() -> bytes:
    return _item(CONSOLE_RESREF, "Crafting Console",
                 "Opens the crafting menu: the workbench (create, break down, upgrade) or the chemical lab. Never used up.", SPELL_ROW)


def _node_fields(s, text: str, script: str) -> None:
    from pykotor.common.language import LocalizedString
    from pykotor.common.misc import ResRef
    from pykotor.resource.formats.gff import GFFList
    s.set_locstring("Text", LocalizedString.from_english(text))
    s.set_string("Listener", "")
    s.set_resref("VO_ResRef", ResRef(""))
    s.set_resref("Script", ResRef(script))
    s.set_uint32("Delay", 4294967295)
    s.set_string("Comment", "")
    s.set_resref("Sound", ResRef(""))
    s.set_string("Quest", "")
    s.set_int32("PlotIndex", -1)
    s.set_single("PlotXPPercentage", 1.0)
    s.set_uint32("WaitFlags", 0)
    s.set_uint32("CameraAngle", 0)
    s.set_uint8("FadeType", 0)
    s.set_uint8("SoundExists", 0)
    s.set_list("AnimList", GFFList())
    for n in range(1, 6):
        s.set_int32("ActionParam%d" % n, 0)
        s.set_int32("ActionParam%db" % n, 0)
    s.set_string("ActionParamStrA", "")
    s.set_string("ActionParamStrB", "")
    s.set_resref("Script2", ResRef(""))
    for name in ("AlienRaceNode", "Emotion", "FacialAnim", "NodeID", "NodeUnskippable", "PostProcNode", "RecordNoVOOverri", "RecordVO", "VOTextChanged"):
        s.set_int32(name, 0)

def _link_fields(s, index: int, active: str, child: bool) -> None:
    from pykotor.common.misc import ResRef
    s.set_uint32("Index", index)
    if child:
        s.set_uint8("IsChild", 0)
    s.set_resref("Active", ResRef(active))
    s.set_resref("Active2", ResRef(""))
    s.set_int32("Logic", 0)
    s.set_uint8("Not", 0)
    s.set_uint8("Not2", 0)
    for n in range(1, 6):
        s.set_int32("Param%d" % n, 0)
    s.set_string("ParamStrA", "")
    for n in range(1, 6):
        s.set_int32("Param%db" % n, 0)
    s.set_string("ParamStrB", "")


def console_menu() -> bytes:
    """The menu as a GFF written field by field (the structure of the file the live tests proved)."""
    from pykotor.common.language import LocalizedString
    from pykotor.common.misc import ResRef
    from pykotor.resource.formats.gff import GFF, GFFContent, GFFList, bytes_gff

    gff = GFF(GFFContent.DLG)
    root = gff.root
    root.set_uint32("NumWords", 9)
    root.set_resref("EndConverAbort", ResRef(""))
    root.set_resref("EndConversation", ResRef(""))
    root.set_uint8("Skippable", 1)
    root.set_resref("CameraModel", ResRef(""))
    root.set_string("VO_ID", "")
    for name in ("AlienRaceOwner", "PostProcOwner", "RecordNoVO", "NextNodeID"):
        root.set_int32(name, 0)
    root.set_uint32("DelayEntry", 0)
    root.set_uint32("DelayReply", 0)
    root.set_list("StuntList", GFFList())
    start = GFFList()
    _link_fields(start.add(0), 0, "", False)
    root.set_list("StartingList", start)
    entries = GFFList()
    entry = entries.add(0)
    _node_fields(entry, "<CUSTOM9220>", "")
    entry.set_string("Speaker", "")
    replies = GFFList()
    for n, (script, condition) in enumerate(MENU_REPLIES):
        _link_fields(replies.add(n), n, condition, True)
    entry.set_list("RepliesList", replies)
    root.set_list("EntryList", entries)
    reply_nodes = GFFList()
    for n, (script, condition) in enumerate(MENU_REPLIES):
        node = reply_nodes.add(n)
        _node_fields(node, "<CUSTOM%d>" % (9221 + n), script)
        node.set_list("EntriesList", GFFList())
    root.set_list("ReplyList", reply_nodes)
    return bytes_gff(gff)


def message_dialog() -> bytes:
    """k2se_msg: the one-line message box the dispatcher shows (nss/k2se_disp.nss DispMessage). One entry, no replies, whose text is custom token 9201."""
    from pykotor.common.misc import ResRef
    from pykotor.resource.formats.gff import GFF, GFFContent, GFFList, bytes_gff
    gff = GFF(GFFContent.DLG)
    root = gff.root
    root.set_uint32("NumWords", 9)
    root.set_resref("EndConverAbort", ResRef(""))
    root.set_resref("EndConversation", ResRef(""))
    root.set_uint8("Skippable", 1)
    root.set_resref("CameraModel", ResRef(""))
    root.set_string("VO_ID", "")
    for name in ("AlienRaceOwner", "PostProcOwner", "RecordNoVO", "NextNodeID"):
        root.set_int32(name, 0)
    root.set_uint32("DelayEntry", 0)
    root.set_uint32("DelayReply", 0)
    root.set_list("StuntList", GFFList())
    start = GFFList()
    _link_fields(start.add(0), 0, "", False)
    root.set_list("StartingList", start)
    entries = GFFList()
    entry = entries.add(0)
    _node_fields(entry, "<CUSTOM9201>", "")
    entry.set_string("Speaker", "")
    entry.set_list("RepliesList", GFFList())
    root.set_list("EntryList", entries)
    root.set_list("ReplyList", GFFList())
    return bytes_gff(gff)


def asset_files(console: bool = True) -> typing.Dict[str, bytes]:
    """{Override file: bytes} for the assets this seed needs."""
    files: typing.Dict[str, bytes] = {MESSAGE_RESREF + ".dlg": message_dialog()}
    if console:
        files[CONSOLE_RESREF + ".uti"] = console_item()
        files[MENU_RESREF + ".dlg"] = console_menu()
    return files
