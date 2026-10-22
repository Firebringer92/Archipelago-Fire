"""
Item tags that loot mode must leave alone although gear_items.json flags them as ordinary loot.

Loot mode (patch_loot_disturb.py's Mod_OnAcquirItem handler) and the area-entry exemption list (generate_trampoline_batch.py's
QUEST_EXEMPT_TAGS) work by TAG, and a tag is only protected when the table entry of the same name is quest_dependent. Some tags are shared
by a quest item and an ordinary one, and the ordinary entry then makes the quest item destroyable:

  k37_itm_freedont  the Sword of Ajunta Pall: every script of the quest finds the sword by this tag. The real blade (template
                    k37_itm_ajunta, plot-flagged, given by Freedon Nadd's ghost) and the ordinary "Notched Steel Sword" share it.
  k37_itm_freednf1  the two other swords the statue puzzle looks for ("Silver Lined Sword" and "Vibrosword")
  k37_itm_freednf2
  g_i_datapad001    shared with g_i_datapad002, the Mandalorian Datapad of the Dantooine raiders quest
  g_i_asthitem001   shared with g_i_asthitem002, a quest "Aesthetic Item" first seen in unk_m41ad

The next world version should carry the same flags in gear_items.json itself; until then every reader of the table passes it through
with_shared_quest_tags(). Keeping the tags in one module means the loot handler and the exemption list cannot disagree.
"""

SHARED_QUEST_TAGS = (
    "g_i_asthitem001",
    "g_i_datapad001",
    "k37_itm_freednf1",
    "k37_itm_freednf2",
    "k37_itm_freedont",
)


def with_shared_quest_tags(gear):
    """The gear table with quest_dependent set on SHARED_QUEST_TAGS. The table passed in is not changed."""
    out = dict(gear)
    for tag in SHARED_QUEST_TAGS:
        entry = out.get(tag)
        if entry is not None and not entry.get("quest_dependent"):
            out[tag] = dict(entry, quest_dependent=True)
    return out
