"""The extra companions (slots 12 to 31): what the client knows about them, and the creature templates the seed needs.

The seed's slot data lists them (slot_data["extras"], see worlds/kotor2/__init__.py _extras_plan). For each, a creature template apxc<slot> is built from the player's own
game files when the client patches (build_templates, needs pykotor and the game folder). Every extra is a copy of ONE generic base template (BASE_TEMPLATE, a vetted
companion body that equips, unequips, levels up and saves like a companion), never the character's own leftover template: a new tag, the name from the seed, no
conversation, the party faction, level one in its base class (the class rebuild raises it to the player's level when it joins), and a portrait that exists in the install.
The look reaches the game one of two ways (the entry's look_method): "disguise" (the template keeps the base body; the seed's config holds ap_look_<slot>=<appearance row>
and the dispatcher's tick applies a permanent disguise effect, nss/k2ap_comp.nss K2AP_LookEnforce) or "template" (the row is written into the template). The look is the
character's own (the K1 look when the K1 models were copied by tools/build_extra_assets.py, else the generic fallback look of the entry).
"""
import os
import typing

BASE_SLOT = 12
TAG_PREFIX = "apxc"
PARTY_FACTION = 2
BASE_TEMPLATE = "p_atton"            # the generic base of every extra (data/extra_companions.json "base"; client/test_extras.py keeps the two equal)


def template_name(slot: int) -> str:
    return "%s%d" % (TAG_PREFIX, slot)


def extra_for_item(extras: typing.List[dict], item_name: str, delivered_before: typing.Iterable[str] = ()) -> typing.Optional[dict]:
    """The plan entry an item belongs to. 'Companion: <name>' is that character; each 'AP Companion' takes the next generated companion not yet given
    (delivered_before: the entries already handed out, as slots)."""
    if item_name.startswith("Companion: "):
        who = item_name.partition(": ")[2]
        return next((e for e in extras if e["name"] == who and e["kind"] != "ap"), None)
    if item_name == "AP Companion":
        used = set(delivered_before)
        return next((e for e in extras if e["kind"] == "ap" and e["slot"] not in used), None)
    return None


def base_template(inst) -> typing.Optional[bytes]:
    """The generic base template's bytes (the game's own copy, or the one in Override)."""
    from pykotor.extract.installation import SearchLocation
    from pykotor.resource.type import ResourceType
    res = inst.resource(BASE_TEMPLATE, ResourceType.UTC, [SearchLocation.CHITIN])
    return res.data if res is not None else None


def entry_look(entry: dict, k1_assets: bool) -> typing.Tuple[int, int]:
    """(appearance row, portrait row) of an entry: the character's own, or the generic fallback of a K1 character when the K1 models are not in Override."""
    own = entry["kind"] != "k1" or k1_assets
    return (entry["appearance"], entry["portrait"]) if own else (entry["fallback_appearance"], entry["fallback_portrait"])


def look_lines(extras: typing.List[dict], k1_present: typing.Callable[[dict], bool]) -> typing.List[str]:
    """The config.txt lines of the extras whose look is a disguise: ap_look_<slot>=<appearance row>."""
    out = []
    for entry in extras or []:
        if entry.get("look_method", "disguise") == "disguise":
            out.append("ap_look_%d=%d" % (entry["slot"], entry_look(entry, k1_present(entry))[0]))
    return out


def build_template(base_data: bytes, entry: dict, k1_assets: bool) -> bytes:
    """One extra's creature template from the generic base: see the module text. k1_assets False uses the fallback look and portrait of a K1 character."""
    from pykotor.common.language import LocalizedString
    from pykotor.common.misc import ResRef
    from pykotor.resource.formats.gff import GFFList, bytes_gff, read_gff
    gff = read_gff(base_data)
    root = gff.root
    slot = entry["slot"]
    root.set_string("Tag", template_name(slot))
    root.set_resref("TemplateResRef", ResRef(template_name(slot)))
    root.set_locstring("FirstName", LocalizedString.from_english(entry["name"]))
    root.set_locstring("LastName", LocalizedString.from_english(""))
    root.set_resref("Conversation", ResRef(""))              # an extra has no talk
    root.set_resref("ScriptDeath", ResRef(""))
    root.set_uint16("FactionID", PARTY_FACTION)
    root.set_uint8("Plot", 0)
    root.set_uint8("Gender", int(entry.get("gender", 0)))
    appearance, portrait = entry_look(entry, k1_assets)
    if entry.get("look_method", "disguise") == "template":
        root.set_uint16("Appearance_Type", appearance)         # otherwise the base body stays and the tick disguises it (look_lines)
    root.set_uint16("PortraitId", portrait)
    # a level-one shell in the base class: the class rebuild raises it to the player's level when it joins the party
    classes = root.get_list("ClassList")
    first = classes._structs[0] if classes is not None and len(classes) else None
    if first is not None:
        first.set_int32("Class", int(entry["class"]))
        first.set_int16("ClassLevel", 1)
        first.set_list("KnownList0", GFFList())
    root.set_list("FeatList", GFFList())
    for field, value in (("HitPoints", 12), ("CurrentHitPoints", 12), ("MaxHitPoints", 12)):
        root.set_int16(field, value)
    return bytes_gff(gff)


def build_templates(game_dir: str, extras: typing.List[dict], k1_assets_present: typing.Callable[[dict], bool]) -> typing.Tuple[typing.Dict[str, bytes], typing.List[str]]:
    """({file name: bytes}, problems) for every planned extra. A source that cannot be found is a problem, not an exception."""
    from pykotor.extract.installation import Installation
    inst = Installation(game_dir)
    files: typing.Dict[str, bytes] = {}
    problems: typing.List[str] = []
    data = base_template(inst)
    if data is None:
        return files, ["the generic base template %s was not found in the game files: the extra companions were not built" % BASE_TEMPLATE]
    for entry in extras:
        try:
            files[template_name(entry["slot"]) + ".utc"] = build_template(data, entry, k1_assets_present(entry))
        except Exception as e:                                           # a template that cannot be rewritten is reported, the others still build
            problems.append("%s: %s" % (entry["name"], e))
    return files, problems


def k1_assets_in(override_dir: str, entry: dict) -> bool:
    """True when the K1 body model of a K1 character was copied into Override (tools/build_extra_assets.py): the K1 look can be used."""
    return entry["kind"] == "k1" and _model_marker(override_dir, entry)


# the .mdl each K1 character's body model is copied as (tools/build_extra_assets.py); present means the K1 look can be used
_MODEL_MARKER = {"Bastila Shan": "p_bastilaba.mdl", "Carth Onasi": "p_carthba.mdl", "Jolee Bindo": "p_joleeba.mdl", "Juhani": "p_juhaniba.mdl",
                 "Mission Vao": "p_missionba.mdl", "Zaalbar": "p_zaalbar.mdl", "Canderous Ordo": "p_candba.mdl"}


def _model_marker(override_dir: str, entry: dict) -> bool:
    marker = _MODEL_MARKER.get(entry["name"])
    return bool(marker) and os.path.isfile(os.path.join(override_dir, marker))


# ---------------------------------------------------------------- droid mode: the companions' own templates get the droid look
# The story companions' creature templates, by slot (the three droids, 3 G0-T0, 5 HK-47 and 8 T3-M4, are droids already and are not listed).
COMPANION_TEMPLATES = {0: "p_atton", 1: "p_baodur", 2: "p_mand", 4: "p_handmaiden", 6: "p_kreia", 7: "p_mira", 9: "p_visas", 10: "p_hanharr", 11: "p_disciple"}
DROID_RACE = 5


def build_droid_templates(game_dir: str, companion_classes: typing.Dict[str, dict]) -> typing.Tuple[typing.Dict[str, bytes], typing.List[str]]:
    """({file name: bytes}, problems): for the companions the seed makes droids (companion_class droid), a copy of their own creature template with the droid race and the
    seed's look row. The copy goes into Override under the template's own name, so it is the creature every join, scene and spawn creates. A companion who has already joined
    in a save keeps the look that save stored; the change shows for a new game."""
    from pykotor.extract.installation import Installation, SearchLocation
    from pykotor.resource.formats.gff import bytes_gff, read_gff
    from pykotor.resource.type import ResourceType
    inst = Installation(game_dir)
    files: typing.Dict[str, bytes] = {}
    problems: typing.List[str] = []
    for key, plan in sorted((companion_classes or {}).items(), key=lambda kv: int(kv[0])):
        slot = int(key)
        look = plan.get("look")
        resref = COMPANION_TEMPLATES.get(slot)
        if not look or plan.get("race") != DROID_RACE or resref is None:
            continue
        res = inst.resource(resref, ResourceType.UTC, [SearchLocation.CHITIN])
        if res is None:
            problems.append("the template %s (slot %d) was not found in the game files" % (resref, slot))
            continue
        try:
            gff = read_gff(res.data)
            gff.root.set_uint16("Appearance_Type", int(look))
            gff.root.set_uint8("Race", DROID_RACE)
            files[resref + ".utc"] = bytes_gff(gff)
        except Exception as e:
            problems.append("%s: %s" % (resref, e))
    return files, problems
