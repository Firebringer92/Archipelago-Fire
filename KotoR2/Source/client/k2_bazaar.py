"""The Archipelago Bazaar's game files that are built from the player's own install: the Jawa's creature, his conversation and the three plot items.

  apjawa.utc      the Jawa: a copy of the game's own Jawa creature with the Bazaar conversation, a new tag, no way to be killed
  ap_jawa.dlg     the conversation, written here (the words are ours): a greeting that shows the counts, a purchase branch and a token branch
  ap_bz_buy.uti, ap_bz_swap.uti, ap_bz_token.uti   plot items made from a plain game plot item (the receipts of a purchase and of an exchange, and the token)

The conversation scripts (ap_jw_*) are compiled by tools/build_bazaar.py and carry no game content. The design is that of the KotOR 1 Bazaar: the receipts held are the deals done, so
the state lives in the save. Engine constraints it follows (found in KotOR 1): a link's "not" flag is never used (every branch has its own pair of condition scripts), entries and
replies strictly alternate, every node has plot index -1.
"""
import json
import os
import typing

HERE = os.path.dirname(os.path.abspath(__file__))
NPC_RESREF = "apjawa"
DLG_RESREF = "ap_jawa"
BUY, SWAP, TOKEN = "ap_bz_buy", "ap_bz_swap", "ap_bz_token"


def config(path: typing.Optional[str] = None) -> dict:
    path = path or os.path.join(HERE, "..", "data", "bazaar.json")
    if not os.path.isfile(path):
        path = os.path.join(HERE, "bazaar.json")                     # next to the client in a release
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_dlg(cfg: dict) -> bytes:
    from pykotor.common.language import LocalizedString
    from pykotor.common.misc import Game, ResRef
    from pykotor.resource.formats.gff import bytes_gff
    from pykotor.resource.generics.dlg import DLG, DLGEntry, DLGLink, DLGReply, dismantle_dlg

    def entry(text: str) -> "DLGEntry":
        e = DLGEntry()
        e.text = LocalizedString.from_english(text)
        e.plot_index = -1
        e.speaker = NPC_RESREF
        return e

    def reply(text: str) -> "DLGReply":
        r = DLGReply()
        r.text = LocalizedString.from_english(text)
        r.plot_index = -1
        return r

    def link(node, active: typing.Optional[str] = None) -> "DLGLink":
        lk = DLGLink(node)
        if active:
            lk.active1 = ResRef(active)
        return lk

    dlg = DLG()
    dlg.skippable = True
    per = cfg["tokens_per_exchange"]
    greet = entry("Utinni! Jawa trade fair! <CUSTOM9011>")
    bought = entry("Good bargain! Jawa find you a fine thing. Take it, take it!")
    bought.script1 = ResRef("ap_jw_buy")
    poor = entry("Not enough credits! This one costs <CUSTOM9012>. Come back with more, yes?")
    traded = entry("Shiny tokens! Jawa take them. Here is your find!")
    traded.script1 = ResRef("ap_jw_swap")
    no_tokens = entry("Jawa want %d tokens for a find. Bring more shiny tokens, yes?" % per)
    again = reply("")                                          # an entry never links to an entry: a blank reply loops every outcome back to the greeting
    again.links.append(link(greet, "ap_jw_greet"))
    for node in (bought, poor, traded, no_tokens):
        node.links.append(link(again))
    buy = reply("Buy a find for <CUSTOM9012> credits.")
    buy.links.append(link(bought, "ap_jw_gold"))
    buy.links.append(link(poor, "ap_jw_nogold"))
    trade = reply("Trade %d Bazaar tokens for a find." % per)
    trade.links.append(link(traded, "ap_jw_tok"))
    trade.links.append(link(no_tokens, "ap_jw_notok"))
    leave = reply("Goodbye.")
    greet.links.append(link(buy, "ap_jw_canbuy"))
    greet.links.append(link(trade, "ap_jw_cantrd"))
    greet.links.append(link(leave))
    dlg.starters.append(link(greet, "ap_jw_greet"))
    return bytes_gff(dismantle_dlg(dlg, Game.K2))


def build_jawa(inst, cfg: dict) -> bytes:
    from pykotor.common.language import LocalizedString
    from pykotor.common.misc import ResRef
    from pykotor.extract.installation import SearchLocation
    from pykotor.resource.formats.gff import bytes_gff, read_gff
    from pykotor.resource.type import ResourceType
    res = inst.resource(cfg["jawa_source"], ResourceType.UTC, [SearchLocation.OVERRIDE, SearchLocation.CHITIN])
    if res is None:
        raise FileNotFoundError("the Jawa creature %s was not found in the game files" % cfg["jawa_source"])
    gff = read_gff(res.data)
    root = gff.root
    root.set_string("Tag", NPC_RESREF)
    root.set_resref("TemplateResRef", ResRef(NPC_RESREF))
    root.set_locstring("FirstName", LocalizedString.from_english("Bazaar Trader"))
    root.set_locstring("LastName", LocalizedString.from_english(""))
    root.set_resref("Conversation", ResRef(DLG_RESREF))
    root.set_uint8("Plot", 1)                                 # he cannot be killed
    return bytes_gff(gff)


def build_items(inst, cfg: dict) -> typing.Dict[str, bytes]:
    from pykotor.common.language import LocalizedString
    from pykotor.common.misc import ResRef
    from pykotor.extract.installation import SearchLocation
    from pykotor.resource.formats.gff import bytes_gff, read_gff
    from pykotor.resource.type import ResourceType
    res = inst.resource(cfg["item_base"], ResourceType.UTI, [SearchLocation.OVERRIDE, SearchLocation.CHITIN])
    if res is None:
        raise FileNotFoundError("the plot item %s was not found in the game files" % cfg["item_base"])
    per = cfg["tokens_per_exchange"]
    specs = {
        BUY: ("Bazaar Find", "A find bought from the Bazaar Trader on the Ebon Hawk. Can't be sold, dropped, or destroyed."),
        SWAP: ("Bazaar Trade Receipt", "Proof of a trade of Bazaar tokens with the Bazaar Trader on the Ebon Hawk. Can't be sold, dropped, or destroyed."),
        TOKEN: ("Bazaar Token", "A shiny token. The Bazaar Trader on the Ebon Hawk trades a find for %d of these. Can't be sold or dropped." % per),
    }
    out: typing.Dict[str, bytes] = {}
    for resref, (title, text) in specs.items():
        gff = read_gff(res.data)
        root = gff.root
        root.set_resref("TemplateResRef", ResRef(resref))
        root.set_string("Tag", resref)
        root.set_locstring("LocalizedName", LocalizedString.from_english(title))
        root.set_locstring("Description", LocalizedString.from_english(text))
        root.set_locstring("DescIdentified", LocalizedString.from_english(text))
        root.set_uint8("Plot", 1)
        root.set_uint16("StackSize", 1)                       # one item per template: the stack comes from the base item (a template saying 99 once gave 99 tokens from one container)
        out[resref + ".uti"] = bytes_gff(gff)
    return out


def build_files(game_dir: str) -> typing.Tuple[typing.Dict[str, bytes], typing.List[str]]:
    """({file name: bytes}, problems): the Jawa, his conversation and the three items, made from this install."""
    from pykotor.extract.installation import Installation
    cfg = config()
    inst = Installation(game_dir)
    files: typing.Dict[str, bytes] = {}
    problems: typing.List[str] = []
    for label, make in (("the conversation", lambda: {DLG_RESREF + ".dlg": build_dlg(cfg)}),
                        ("the Jawa", lambda: {NPC_RESREF + ".utc": build_jawa(inst, cfg)}),
                        ("the items", lambda: build_items(inst, cfg))):
        try:
            files.update(make())
        except Exception as e:
            problems.append("the Bazaar: %s could not be built: %s" % (label, e))
    return files, problems
