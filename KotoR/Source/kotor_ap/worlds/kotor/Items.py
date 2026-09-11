import importlib.resources
import json
import typing

from BaseClasses import Item, ItemClassification


class ItemData(typing.NamedTuple):
    code: typing.Optional[int]
    classification: ItemClassification
    # Extender arm name this item forwards to (see KNOWN_ARM_NAMES in
    # KotorClient.py / AP_ARM_NAMES in extender/src/dllmain.c). Must match
    # exactly -- this is how the client knows what to send when the item
    # is received.
    arm_name: str


class KotorItem(Item):
    game: str = "KotOR"


# Full arm-set coverage. Skills/xp/credits are repeatable (each grant is a
# fixed additive increment, safe to receive many times -- see
# kotor_reconciliation.py's ARM_EFFECT table, which uses the exact same
# fixed amounts). Companions, feats, class switches, and the jedi-convert
# items are one-shot progression items (re-receiving them is a safe no-op
# via the extender's own before/after-state guards, but there's only ever
# one copy in the pool). Credits/xp additionally exist as the client-side
# set_xp/set_credits exact-value reconciliation actions -- that's a
# correction mechanism, not something granted as an AP item itself.
base_id = 9200000

item_table: typing.Dict[str, ItemData] = {
    "Skill: Computer Use": ItemData(base_id + 0, ItemClassification.useful, "computer_use"),
    "Skill: Demolitions": ItemData(base_id + 1, ItemClassification.useful, "demolitions"),
    "Skill: Stealth": ItemData(base_id + 2, ItemClassification.useful, "stealth"),
    "Skill: Awareness": ItemData(base_id + 3, ItemClassification.useful, "awareness"),
    "Skill: Persuade": ItemData(base_id + 4, ItemClassification.useful, "persuade"),
    "Skill: Repair": ItemData(base_id + 5, ItemClassification.useful, "repair"),
    "Skill: Security": ItemData(base_id + 6, ItemClassification.useful, "security"),
    "Skill: Treat Injury": ItemData(base_id + 7, ItemClassification.useful, "treat_injury"),
    "Companion: Bastila Shan": ItemData(base_id + 8, ItemClassification.progression, "companion_bastila"),
    "Companion: Canderous Ordo": ItemData(base_id + 9, ItemClassification.progression, "companion_canderous"),
    # base_id+10 ("Feat: Toughness"/feat_toughness) RETIRED -- feats are
    # left entirely to normal in-game level-up choices now, never touched
    # by AP. Not reusing this offset since it's a stable AP item code a
    # live seed's item pool depends on, same reasoning as the retired
    # +13/+14 offsets below.
    "Class Switch: Jedi Guardian": ItemData(base_id + 11, ItemClassification.progression, "class_guardian"),
    "Class Switch: Jedi Consular": ItemData(base_id + 12, ItemClassification.progression, "class_consular"),
    # base_id+13/+14 (Companion: Jedi Conversion / Jedi Experience) RETIRED
    # -- see generate_trampoline_batch.py's APPLIES table comment. Confirmed
    # live: AddMultiClass and GiveXPToCreature both have zero effect on a
    # non-PC party member in this engine build. Not renumbering the
    # remaining items' base_id offsets since those are stable AP item codes
    # a live seed's item pool depends on.
    "Ability: Charisma Increase": ItemData(base_id + 15, ItemClassification.useful, "grant_test_ability"),
    "Experience Points": ItemData(base_id + 16, ItemClassification.filler, "xp"),
    "Republic Credits": ItemData(base_id + 17, ItemClassification.filler, "credits"),
    "Companion: Carth Onasi": ItemData(base_id + 18, ItemClassification.progression, "companion_carth"),
    "Companion: HK-47": ItemData(base_id + 19, ItemClassification.progression, "companion_hk47"),
    "Companion: Jolee Bindo": ItemData(base_id + 20, ItemClassification.progression, "companion_jolee"),
    "Companion: Juhani": ItemData(base_id + 21, ItemClassification.progression, "companion_juhani"),
    "Companion: Mission Vao": ItemData(base_id + 22, ItemClassification.progression, "companion_mission"),
    "Companion: T3-M4": ItemData(base_id + 23, ItemClassification.progression, "companion_t3m4"),
    "Companion: Zaalbar": ItemData(base_id + 24, ItemClassification.progression, "companion_zaalbar"),
    "Class Switch: Jedi Sentinel": ItemData(base_id + 25, ItemClassification.progression, "class_sentinel"),
    "Ability: Strength Increase": ItemData(base_id + 26, ItemClassification.useful, "ability_strength"),
    "Ability: Dexterity Increase": ItemData(base_id + 27, ItemClassification.useful, "ability_dexterity"),
    "Ability: Constitution Increase": ItemData(base_id + 28, ItemClassification.useful, "ability_constitution"),
    "Ability: Intelligence Increase": ItemData(base_id + 29, ItemClassification.useful, "ability_intelligence"),
    "Ability: Wisdom Increase": ItemData(base_id + 30, ItemClassification.useful, "ability_wisdom"),
    # Completion-condition markers (2026-08-29) -- locked (place_locked_item
    # in __init__.py's create_regions()) to "Level 20 Reached"/"Malak
    # Defeated" in Locations.py, real items with real codes (NOT an AP
    # "Event" item with code=None -- that requires the LOCATION's own
    # address to also be None, i.e. a purely internal marker never sent
    # over the network at all, which contradicts these being real,
    # player-visible checks the client reports via a genuine LocationChecks
    # packet; confirmed live via Main.py's own generation-time assertion
    # when this was first tried as a true code=None Event). arm_name
    # "goal_marker" is deliberately unmapped to anything real in
    # KNOWN_ARM_NAMES/HEAVY_ARMS/CLASS_ARM_TO_KEY -- there is nothing
    # meaningful to grant for "you already reached level 20"/"you already
    # defeated Malak" by definition, so on receipt this safely round-trips
    # to the extender's existing "ERROR:unknown item" reply (dllmain.c's
    # ap_apply(), the same graceful path any truly-unrecognized name hits)
    # and stops there -- no crash, no incorrect grant, just a harmless
    # logged no-op.
    "Reached Level 20": ItemData(base_id + 31, ItemClassification.progression, "goal_marker"),
    "Malak Defeated": ItemData(base_id + 32, ItemClassification.progression, "goal_marker"),
    # true_balance's own pair, added same day once the above pattern was
    # already in place -- locked to the EXISTING "Alignment: Dark Side 0"/
    # "Alignment: Light Side 100" locations (no new Locations.py entries
    # needed, unlike Level 20/Malak above) rather than the wider 0-20/80-100
    # "extreme" bands kotor_location_tracker.py's true_balance_reached()
    # uses live in-game -- a deliberate simplification for AP's own
    # generation-time completion check, not a claim the two are identical;
    # see Rules.py for the exact reasoning.
    "Reached Dark Side 0": ItemData(base_id + 33, ItemClassification.progression, "goal_marker"),
    "Reached Light Side 100": ItemData(base_id + 34, ItemClassification.progression, "goal_marker"),
    # CompanionClass=jedi_companion (2026-08-30): one guaranteed-placement
    # item per (non-Jedi companion x possible Jedi class) -- 4 companions x
    # 3 classes = 12 static entries here, but __init__.py's create_items()
    # only ever actually places ONE of the 3 per companion each seed (the
    # class was already decided by that seed's roll, same guaranteed-
    # placement pattern as starting_class=jedi_granted). arm_name is the
    # "companion_class:<name>:<class>" parameterized action -- see
    # generate_trampoline_batch.py's build_companion_class_block() and
    # KotorClient.py's companion_class dispatch. Order/grouping matches
    # __init__.py's NON_JEDI_COMPANIONS list.
    "Jedi Training: Carth (Guardian)": ItemData(base_id + 35, ItemClassification.progression, "companion_class:carth:guardian"),
    "Jedi Training: Carth (Consular)": ItemData(base_id + 36, ItemClassification.progression, "companion_class:carth:consular"),
    "Jedi Training: Carth (Sentinel)": ItemData(base_id + 37, ItemClassification.progression, "companion_class:carth:sentinel"),
    "Jedi Training: Canderous (Guardian)": ItemData(base_id + 38, ItemClassification.progression, "companion_class:canderous:guardian"),
    "Jedi Training: Canderous (Consular)": ItemData(base_id + 39, ItemClassification.progression, "companion_class:canderous:consular"),
    "Jedi Training: Canderous (Sentinel)": ItemData(base_id + 40, ItemClassification.progression, "companion_class:canderous:sentinel"),
    "Jedi Training: Zaalbar (Guardian)": ItemData(base_id + 41, ItemClassification.progression, "companion_class:zaalbar:guardian"),
    "Jedi Training: Zaalbar (Consular)": ItemData(base_id + 42, ItemClassification.progression, "companion_class:zaalbar:consular"),
    "Jedi Training: Zaalbar (Sentinel)": ItemData(base_id + 43, ItemClassification.progression, "companion_class:zaalbar:sentinel"),
    "Jedi Training: Mission (Guardian)": ItemData(base_id + 44, ItemClassification.progression, "companion_class:mission:guardian"),
    "Jedi Training: Mission (Consular)": ItemData(base_id + 45, ItemClassification.progression, "companion_class:mission:consular"),
    "Jedi Training: Mission (Sentinel)": ItemData(base_id + 46, ItemClassification.progression, "companion_class:mission:sentinel"),
    # StartingClass=random_class (2026-09-02): the PC's own starting class,
    # rerolled to one of all 6 classes. A Jedi roll reuses the existing
    # Class Switch items above (AddMultiClass, same as starting_class=
    # jedi_start/jedi_granted); a base-class roll needs these 3 new items
    # instead, since AddMultiClass can't replace an existing base class --
    # these use KSE_SetCreatureField directly (see generate_trampoline_batch.py's
    # pc_class_soldier/scout/scoundrel arms), the same mechanism
    # CompanionClass already uses for companions.
    "PC Class: Soldier": ItemData(base_id + 47, ItemClassification.progression, "pc_class_soldier"),
    "PC Class: Scout": ItemData(base_id + 48, ItemClassification.progression, "pc_class_scout"),
    "PC Class: Scoundrel": ItemData(base_id + 49, ItemClassification.progression, "pc_class_scoundrel"),
    # AdditionalFeats (2026-09-07): one per eligible character (PC + the 7
    # non-droid companions, order matching __init__.py's COMPANION_CLASS_KEYS).
    # Receiving one grants nothing immediately -- the arm_name is a marker
    # KotorClient.py recognizes specially (NOT a real extender arm name,
    # unlike every other entry in this table): it records a pending flag
    # in the delivery log instead of queuing a send, and only decides +
    # queues the actual 3-feat grant once that character is both recruited
    # and their class has settled (see KotorContext._is_companion_recruited/
    # _is_companion_class_finalized/_is_pc_class_finalized). The eventual
    # real send reuses the "companion_class"-style parameterized-action
    # shape once the 3 feats are chosen -- see generate_trampoline_batch.py's
    # build_additional_feats_block().
    "Additional Feats Character: PC": ItemData(base_id + 50, ItemClassification.useful, "additional_feats:pc"),
    "Additional Feats Character: Bastila": ItemData(base_id + 51, ItemClassification.useful, "additional_feats:bastila"),
    "Additional Feats Character: Canderous": ItemData(base_id + 52, ItemClassification.useful, "additional_feats:canderous"),
    "Additional Feats Character: Carth": ItemData(base_id + 53, ItemClassification.useful, "additional_feats:carth"),
    "Additional Feats Character: Jolee": ItemData(base_id + 54, ItemClassification.useful, "additional_feats:jolee"),
    "Additional Feats Character: Juhani": ItemData(base_id + 55, ItemClassification.useful, "additional_feats:juhani"),
    "Additional Feats Character: Mission": ItemData(base_id + 56, ItemClassification.useful, "additional_feats:mission"),
    "Additional Feats Character: Zaalbar": ItemData(base_id + 57, ItemClassification.useful, "additional_feats:zaalbar"),

    # 2026-09-08: Progression System (ProgressionSystem option) -- 10 real
    # main-questline items, each classification=progression (not useful --
    # AP's own fill algorithm needs the real classification to weight/place
    # these correctly relative to logic, unlike Additional Feats above
    # which is a pure quality-of-life bonus with no access rule riding on
    # it). Reuses the EXISTING give_item:<resref> mechanism (already
    # proven for curated gear, see gear_base_id below) directly -- no new
    # client-side grant code needed, "create this real item in inventory"
    # is the exact same operation regardless of WHY it's being granted.
    # What makes these different from ordinary gear is entirely on the
    # SUPPRESSION/RECONCILIATION side (see PROGRESSION_ITEM_RESREFS below
    # and scripts/patch_progression_system.py) -- each one's normal
    # vanilla acquisition script gets suppressed, and it's granted instead
    # once the paired AP check clears. See Rules.py for the access rules
    # gating what each one unlocks, and FutureDesign.md's 2026-09-08
    # Progression System entries for the full derivation (every gate here
    # is confirmed via the game's own compiled scripts, not guessed).
    # base_id + 58 through 67 = the 10 originally-designed Progression System
    # items. base_id+62 (Tatooine Desert Map) and base_id+63 (Star Map:
    # Dantooine) were dropped 2026-09-08 after tracing each one's REAL
    # checkpoint script rather than just its pickup location: nothing in the
    # entire game (chitin + Override, every resource type) ever checks
    # whether the player possesses tat20aa_westmap, and Dantooine's star map
    # turned out to be neither part of the Leviathan-capture gate nor a
    # travel barrier of any kind (see Rules.py and FutureDesign.md). Their
    # IDs are left permanently unused rather than renumbering the rest.
    "Progression Item: Sith Armor": ItemData(base_id + 58, ItemClassification.progression, "give_item:ptar_sitharmor"),
    "Progression Item: Sith Papers": ItemData(base_id + 59, ItemClassification.progression, "give_item:ptar_sithpapers"),
    "Progression Item: Taris Shield Codes": ItemData(base_id + 60, ItemClassification.progression, "give_item:ptar_shieldcodes"),
    "Progression Item: Manaan Enviro Suit": ItemData(base_id + 61, ItemClassification.progression, "give_item:man28_envirosuit"),
    "Progression Item: Star Map (Tatooine)": ItemData(base_id + 64, ItemClassification.progression, "give_item:tat_starpad"),
    "Progression Item: Star Map (Kashyyyk)": ItemData(base_id + 65, ItemClassification.progression, "give_item:kas_starpad"),
    "Progression Item: Star Map (Manaan)": ItemData(base_id + 66, ItemClassification.progression, "give_item:man_starpad"),
    "Progression Item: Star Map (Korriban)": ItemData(base_id + 67, ItemClassification.progression, "give_item:kor_starpad"),
}

# Real in-game item resref for each Progression System item above, keyed
# by the SHORT key used everywhere else (suppression script tables,
# reconciliation) -- redundant with the arm_name's give_item:<resref>
# suffix above, kept as its own explicit table since the suppression/
# reconciliation side needs to go resref -> key just as often as key ->
# resref (e.g. "I found ptar_sitharmor already in inventory -- is that
# one of the 8 tracked progression items, and if so is it legitimately
# AP-granted yet?"). All 8 confirmed via the game's own compiled
# scripts -- see FutureDesign.md's 2026-09-08 entries. (desert_map and
# starmap_dantooine dropped 2026-09-08 -- see the comment above the item
# table itself for why.)
PROGRESSION_ITEM_RESREFS: typing.Dict[str, str] = {
    "sith_armor": "ptar_sitharmor",
    "sith_papers": "ptar_sithpapers",
    "shield_codes": "ptar_shieldcodes",
    "enviro_suit": "man28_envirosuit",
    "starmap_tatooine": "tat_starpad",
    "starmap_kashyyyk": "kas_starpad",
    "starmap_manaan": "man_starpad",
    "starmap_korriban": "kor_starpad",
}

# Traps (2026-09-08): 12 items, gated by EnableTraps, guaranteed placement
# (added to mandatory_names in __init__.py's create_items() exactly like
# Additional Feats/Progression System above) whenever the option is on --
# NOT part of the weighted _distribute_items() draw, since the design is
# "always exactly 12 exist in the pool when enabled," not "maybe a few
# show up." arm_name uses a "trap:<key>" sentinel KotorClient.py's
# _deliver_item recognizes specially (same interception pattern as
# "additional_feats:") -- every trap's REAL effect is decided at the
# moment of delivery from the character's actual live state (which half
# of their feats/force powers/inventory, which companion, how much CON
# reduction gets closest to half Max HP), never baked in at generation
# time. PC-only; never affects companions except as the deliberate
# target of Remove a Companion. See Options.py's EnableTraps docstring
# for the full player-facing description of each one. No standalone
# "Halve Constitution" item -- Cut Max Health in Half already works by
# reducing CON (the only lever this engine has for Max HP at all, see
# FutureDesign.md), so a separate CON-halving trap would just overlap
# with it; STR/DEX/INT/WIS/CHA are the 5 standalone ability traps.
TRAP_ITEMS: typing.Dict[str, ItemData] = {
    "Trap: Remove All Credits": ItemData(base_id + 70, ItemClassification.trap, "trap:remove_credits"),
    # Cut Level in Half retired 2026-09-08 (base_id+71 kept, not
    # renumbered) -- SetXP can't reduce XP below the current level's
    # threshold once it's already banked (confirmed live: level dropped,
    # XP didn't), leaving an inconsistent character. Reduce a Skill reuses
    # EffectSkillDecrease, the same plain-effect approach already proven
    # live for the 5 ability traps below -- no threshold to fight.
    "Trap: Reduce a Skill": ItemData(base_id + 71, ItemClassification.trap, "trap:reduce_skill"),
    "Trap: Remove Half Known Feats": ItemData(base_id + 72, ItemClassification.trap, "trap:remove_half_feats"),
    "Trap: Remove Half Known Force Powers": ItemData(base_id + 73, ItemClassification.trap, "trap:remove_half_powers"),
    "Trap: Cut Max Health in Half": ItemData(base_id + 74, ItemClassification.trap, "trap:cut_max_hp"),
    "Trap: Remove a Companion": ItemData(base_id + 75, ItemClassification.trap, "trap:remove_companion"),
    "Trap: Remove Half Inventory Items": ItemData(base_id + 76, ItemClassification.trap, "trap:remove_half_inventory"),
    "Trap: Halve Strength": ItemData(base_id + 77, ItemClassification.trap, "trap:reduce_str"),
    "Trap: Halve Dexterity": ItemData(base_id + 78, ItemClassification.trap, "trap:reduce_dex"),
    "Trap: Halve Intelligence": ItemData(base_id + 80, ItemClassification.trap, "trap:reduce_int"),
    "Trap: Halve Wisdom": ItemData(base_id + 81, ItemClassification.trap, "trap:reduce_wis"),
    "Trap: Halve Charisma": ItemData(base_id + 82, ItemClassification.trap, "trap:reduce_cha"),
}
item_table.update(TRAP_ITEMS)

# LootMode=destroy/replace safety net (2026-09-09): both modes unconditionally
# destroy a picked-up non-whitelisted item on the spot (see Options.py's
# LootMode and scripts/patch_item_suppression.py), and Security Spikes
# (g_i_secspike01/02) are real, non-quest_dependent, non-whitelisted pickups
# per gear_items.json -- meaning every spike a player would normally find in
# the world is silently destroyed under either mode. Security is one of the
# only skills whose checks (locked doors/containers) consume a physical
# item to attempt at all, so a player who never buys spikes manually could
# reach a mandatory locked point with zero in inventory and no way to
# proceed. Precollected (see __init__.py's generate_early()) rather than
# pool-placed -- this is a safety net against an option-caused problem, not
# a real gameplay reward, so it shouldn't compete with the weighted item
# draw or ever NOT show up when the mode is on. Count of 20 is a deliberate
# fixed constant (not consumable_stack_count-derived, see KotorClient.py's
# _do_deliver give_item: parsing) -- comfortably more than a single
# playthrough would ever need, cheap insurance either way.
item_table["Starting Item: Security Spikes (Loot Safety Net)"] = ItemData(
    base_id + 83, ItemClassification.useful, "give_item:g_i_secspike01:20")

# Curated gear (weapons/armor/equipment/consumables) lives in gear_items.json,
# not here -- it's meant to stay live-editable by hand without a code
# regeneration step, so it's loaded at runtime instead of baked into this
# table. Only rows flagged included_as_item go in the pool; arm_name is the
# give_item:<resref> sentinel KotorClient.py's _deliver_item recognizes and
# routes to CreateItemOnObject via the extender.
gear_base_id = base_id + 100000  # clear of base_id+0..+30 above, room to grow


def read_gear_json() -> dict:
    """Reads gear_items.json via importlib.resources rather than a plain
    open(os.path.dirname(__file__)-relative path) -- found broken live
    2026-09-04: this world ships for real distribution inside a zip-loaded
    kotor.apworld, where __file__ resolves to a synthetic path that
    doesn't exist on any real filesystem. A plain open()/os.path.exists()
    check against that path always silently "fails to find" the file --
    meaning EVERY seed generated through a packaged .apworld was silently
    missing every gear item from the pool entirely, with no error printed
    anywhere (each call site here used to treat "not found" as a normal,
    quiet empty-result case, not a bug). importlib.resources.files() reads
    package data correctly whether the package is a loose folder (this
    dev checkout) or a real zip archive (what actually ships), so this
    works in both without needing to know which. Returns {} only if the
    file is genuinely missing from the package -- a real packaging error,
    not the normal case."""
    try:
        raw = importlib.resources.files(__package__).joinpath("gear_items.json").read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError):
        return {}
    return json.loads(raw)


def _load_gear_items() -> typing.Dict[str, ItemData]:
    gear = read_gear_json()
    if not gear:
        return {}

    # sorted() by resref keeps codes stable across regens as long as the
    # underlying JSON's key set doesn't change.
    included = [(resref, data) for resref, data in sorted(gear.items()) if data.get("included_as_item")]
    name_counts: typing.Dict[str, int] = {}
    for _, data in included:
        name_counts[data["name"]] = name_counts.get(data["name"], 0) + 1

    entries: typing.Dict[str, ItemData] = {}
    used_names: typing.Set[str] = set()
    for index, (resref, data) in enumerate(included):
        name = data["name"]
        if name_counts[name] > 1:
            name = f"{name} ({resref})"
        while name in used_names:  # defensive: guarantee uniqueness even beyond the count check above
            name = f"{name}_"
        used_names.add(name)
        entries[name] = ItemData(gear_base_id + index, ItemClassification.useful, f"give_item:{resref}")
    return entries


item_table.update(_load_gear_items())

item_name_to_id: typing.Dict[str, int] = {name: data.code for name, data in item_table.items()}
lookup_id_to_name: typing.Dict[int, str] = {data.code: name for name, data in item_table.items()}
# arm_name -> item display name -- every entry's arm_name is unique, so
# this reverse lookup is unambiguous. Single source of truth for the
# "which item name grants this arm" question, used by both
# generate_early() and _skill_ability_pools() in __init__.py (previously
# each rebuilt this same dict independently).
arm_name_to_item: typing.Dict[str, str] = {data.arm_name: name for name, data in item_table.items()}

# Filler items are the ones that pad the pool out to match location count --
# both are safely repeatable with no upper bound concern (skills cap at 127
# via KSE, xp/credits have no meaningful ceiling).
filler_items = ["Experience Points", "Republic Credits"]
