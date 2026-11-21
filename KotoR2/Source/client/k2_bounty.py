"""The Bounty Datapads (bounty_cards): forty of the enemy randomizer's new creatures carry one.

A datapad is a plot item (so it cannot be sold, dropped or destroyed and the count in the save only goes up) made from the same plain game plot item as the Bazaar's
tokens. The creature that carries it is one of the enemy randomizer's copies (apenNNN.utc): its item list gets the datapad, so it is in the body's inventory when the
creature dies. The game counts the datapads the player holds and reports "BC|<count>" (nss/k2se_poll.nss); the nth bounty check fires when the count reaches n.
"""
import typing

DATAPAD = "ap_bounty_card"


def build_item(inst, item_base: str) -> typing.Dict[str, bytes]:
    """{"ap_bounty_card.uti": bytes}: the datapad, made from the game's own plain plot item `item_base`."""
    from pykotor.common.language import LocalizedString
    from pykotor.common.misc import ResRef
    from pykotor.extract.installation import SearchLocation
    from pykotor.resource.formats.gff import bytes_gff, read_gff
    from pykotor.resource.type import ResourceType
    res = inst.resource(item_base, ResourceType.UTI, [SearchLocation.OVERRIDE, SearchLocation.CHITIN])
    if res is None:
        raise FileNotFoundError("the plot item %s was not found in the game files" % item_base)
    text = "A bounty datapad taken from a hunted creature. Can't be sold or dropped."
    gff = read_gff(res.data)
    root = gff.root
    root.set_resref("TemplateResRef", ResRef(DATAPAD))
    root.set_string("Tag", DATAPAD)
    root.set_locstring("LocalizedName", LocalizedString.from_english("Bounty Datapad"))
    root.set_locstring("Description", LocalizedString.from_english(text))
    root.set_locstring("DescIdentified", LocalizedString.from_english(text))
    root.set_uint8("Plot", 1)
    root.set_uint16("StackSize", 1)                       # one item per template (a template saying more once gave 99 tokens from one container)
    return {DATAPAD + ".uti": bytes_gff(gff)}


def with_datapad(utc_data: bytes) -> bytes:
    """The creature template with one datapad added to its item list (it drops it with the rest of its inventory)."""
    from pykotor.common.misc import ResRef
    from pykotor.resource.formats.gff import GFFList, bytes_gff, read_gff
    gff = read_gff(utc_data)
    root = gff.root
    items = root.get_list("ItemList") if root.exists("ItemList") else GFFList()
    position = len(items)
    entry = items.add(0)
    entry.set_resref("InventoryRes", ResRef(DATAPAD))
    entry.set_uint16("Repos_PosX", position % 8)
    entry.set_uint16("Repos_Posy", position // 8)            # the game's own spelling of the field
    entry.set_uint8("Dropable", 1)
    root.set_list("ItemList", items)                          # the list returned by get_list is a copy: put it back
    return bytes_gff(gff)
