"""The Archipelago Vendor's game files, built on the player's machine: his creature (a copy of the game's Jawa creature, as the Bazaar's), his conversation and the
plot items (four pass items and two receipts). The five conversation scripts (ap_vd_*) hold no game content and are compiled by tools/build_vendor.py.

The conversation is a table: a greeting, four menus (skill, ability, alignment, crafting supplies; each shown only while its pass item is held), and under each menu one
reply per item with two outcomes, done or not possible. The scripts take their category and item from the script parameters of the node or link that runs them
(category 0 skill, 1 ability, 2 alignment, 3 Components, 4 Chemicals). The same engine rules as the Bazaar's apply: entries and replies strictly alternate, a blank
reply loops every outcome back to the greeting, every node has plot index -1. nss/k2ap_vendor.nss has the rules and docs/FIRST_RUN_BUILD_PLAN.md section 25 the design.
"""
import json
import os
import typing

HERE = os.path.dirname(os.path.abspath(__file__))
NPC_RESREF = "apvendor"
DLG_RESREF = "ap_vendor"
PASS_TITLES = {"skill": "Skill Training", "abil": "Ability Training", "align": "Alignment Change", "supply": "Crafting Supplies"}
PASS_ITEM_NAMES = {key: "Vendor Pass: " + title for key, title in PASS_TITLES.items()}


def config(path: typing.Optional[str] = None) -> dict:
    path = path or os.path.join(HERE, "..", "data", "vendor.json")
    if not os.path.isfile(path):
        path = os.path.join(HERE, "vendor.json")                     # next to the client in a release
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_items() -> typing.Dict[str, bytes]:
    """The four pass items and the two receipts, plain plot items written from constants (client/k2_assets.py)."""
    from k2_assets import _item
    out: typing.Dict[str, bytes] = {}
    for key, title in PASS_TITLES.items():
        out["ap_vp_%s.uti" % key] = _item("ap_vp_" + key, "Vendor Pass: " + title,
                                         "Unlocks the %s menu of the Archipelago Vendor on the Ebon Hawk. Can't be sold or dropped." % title.lower(), None)
    out["ap_vd_skill.uti"] = _item("ap_vd_skill", "Skill Training Receipt", "Proof of one skill rank bought from the Archipelago Vendor. Can't be sold or dropped.", None)
    out["ap_vd_abil.uti"] = _item("ap_vd_abil", "Ability Training Receipt", "Proof of one ability point bought from the Archipelago Vendor. Can't be sold or dropped.", None)
    return out


def build_dlg(cfg: dict) -> bytes:
    from pykotor.common.language import LocalizedString
    from pykotor.common.misc import Game, ResRef
    from pykotor.resource.formats.gff import bytes_gff
    from pykotor.resource.generics.dlg import DLG, DLGEntry, DLGLink, DLGReply, dismantle_dlg

    def entry(text: str, script: str = "", params: typing.Sequence[int] = ()) -> "DLGEntry":
        e = DLGEntry()
        e.text = LocalizedString.from_english(text)
        e.plot_index = -1
        e.speaker = NPC_RESREF
        if script:
            e.script1 = ResRef(script)
            for n, v in enumerate(params, 1):
                setattr(e, "script1_param%d" % n, v)
        return e

    def reply(text: str) -> "DLGReply":
        r = DLGReply()
        r.text = LocalizedString.from_english(text)
        r.plot_index = -1
        return r

    def link(node, active: str = "", params: typing.Sequence[int] = ()) -> "DLGLink":
        lk = DLGLink(node)
        if active:
            lk.active1 = ResRef(active)
            for n, v in enumerate(params, 1):
                setattr(lk, "active1_param%d" % n, v)
        return lk

    dlg = DLG()
    dlg.skippable = True
    greet = entry("Welcome to the Archipelago Vendor. <CUSTOM9031>")
    again = reply("")                                           # an entry never links to an entry: a blank reply loops every outcome back to the greeting
    again.links.append(link(greet, "ap_vd_greet"))
    back = lambda: reply("Never mind.")                         # noqa: E731 -- one per menu, each to the greeting
    poor_text = "That cannot be done now: check your credits and your limits."

    def menu(title: str, menu_id: int, intro: str, offers: typing.List[typing.Tuple[str, int, int]], done_text: str) -> None:
        """offers: (reply text, category, item)."""
        head = reply(title)
        greet.links.append(link(head, "ap_vd_menu", (menu_id,)))
        page = entry(intro)
        head.links.append(link(page))
        poor = entry(poor_text)
        poor.links.append(link(again))
        for text, cat, item in offers:
            r = reply(text)
            done = entry(done_text, "ap_vd_do", (cat, item))
            done.links.append(link(again))
            r.links.append(link(done, "ap_vd_ok", (cat, item)))
            r.links.append(link(poor, "ap_vd_no", (cat, item)))
            page.links.append(link(r))
        b = back()
        b.links.append(link(greet, "ap_vd_greet"))
        page.links.append(link(b))

    menu("Skill training.", 0, "Which skill do you want to train? One rank costs %d credits." % cfg["skill_price"],
         [("%s (%d credits)." % (name, cfg["skill_price"]), 0, i) for i, name in enumerate(cfg["skills"])], "Your training is done.")
    menu("Ability training.", 1, "Which ability do you want to raise? One point costs %d credits." % cfg["ability_price"],
         [("%s (%d credits)." % (name, cfg["ability_price"]), 1, i) for i, name in enumerate(cfg["abilities"])], "Your training is done.")
    menu("Alignment change.", 2, "I can move you %d points either way." % cfg["alignment_step"],
         [("Toward the dark side (I pay you %d credits)." % cfg["dark_pays"], 2, 0), ("Toward the light side (%d credits)." % cfg["light_costs"], 2, 1)],
         "It is done.")
    menu("Crafting supplies.", 3, "Components and Chemicals, by the bundle.",
         [("%d Components (%d credits)." % (n, price), 3, i) for i, (n, price) in enumerate(cfg["bundles"])]
         + [("%d Chemicals (%d credits)." % (n, price), 4, i) for i, (n, price) in enumerate(cfg["bundles"])], "Here you are.")
    leave = reply("Goodbye.")
    greet.links.append(link(leave))
    dlg.starters.append(link(greet, "ap_vd_greet"))
    return bytes_gff(dismantle_dlg(dlg, Game.K2))


def build_npc(inst, cfg: dict) -> bytes:
    from pykotor.common.language import LocalizedString
    from pykotor.common.misc import ResRef
    from pykotor.extract.installation import SearchLocation
    from pykotor.resource.formats.gff import bytes_gff, read_gff
    from pykotor.resource.type import ResourceType
    res = inst.resource(cfg["npc_source"], ResourceType.UTC, [SearchLocation.OVERRIDE, SearchLocation.CHITIN])
    if res is None:
        raise FileNotFoundError("the creature %s was not found in the game files" % cfg["npc_source"])
    gff = read_gff(res.data)
    root = gff.root
    root.set_string("Tag", NPC_RESREF)
    root.set_resref("TemplateResRef", ResRef(NPC_RESREF))
    root.set_locstring("FirstName", LocalizedString.from_english("Archipelago Vendor"))
    root.set_locstring("LastName", LocalizedString.from_english(""))
    root.set_resref("Conversation", ResRef(DLG_RESREF))
    root.set_uint8("Plot", 1)
    return bytes_gff(gff)


def build_files(game_dir: str) -> typing.Tuple[typing.Dict[str, bytes], typing.List[str]]:
    """({file name: bytes}, problems): the Vendor's creature, his conversation and the six items."""
    from pykotor.extract.installation import Installation
    cfg = config()
    inst = Installation(game_dir)
    files: typing.Dict[str, bytes] = {}
    problems: typing.List[str] = []
    for label, make in (("the conversation", lambda: {DLG_RESREF + ".dlg": build_dlg(cfg)}), ("the creature", lambda: {NPC_RESREF + ".utc": build_npc(inst, cfg)}),
                        ("the items", build_items)):
        try:
            files.update(make())
        except Exception as e:
            problems.append("the Vendor: %s could not be built: %s" % (label, e))
    return files, problems
