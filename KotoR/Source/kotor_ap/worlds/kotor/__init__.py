import typing

from BaseClasses import Region
from worlds.AutoWorld import World, WebWorld

from . import EntranceRando
from .Items import KotorItem, item_table, item_name_to_id, filler_items, arm_name_to_item, read_gear_json
from .Locations import KotorLocation, location_table, location_name_to_id
from .Options import (
    KotorOptions, STARTING_ABILITY_ARMS, STARTING_SKILL_ARMS,
)
from .Rules import set_rules, set_completion_rules

JEDI_CLASS_ITEMS = {
    0: "Class Switch: Jedi Guardian",
    1: "Class Switch: Jedi Consular",
    2: "Class Switch: Jedi Sentinel",
}
# StartingClass=random_class -- item name for each of all 6 classes, keyed by
# class NAME (unlike JEDI_CLASS_ITEMS above, which is keyed by jedi_class's
# own option index) since random_class ignores jedi_class and rolls a
# class name directly via ALL_CLASS_NAMES below.
CLASS_NAME_TO_ITEM = {
    "guardian": "Class Switch: Jedi Guardian",
    "consular": "Class Switch: Jedi Consular",
    "sentinel": "Class Switch: Jedi Sentinel",
    "soldier": "PC Class: Soldier",
    "scout": "PC Class: Scout",
    "scoundrel": "PC Class: Scoundrel",
}
COMPANION_ITEM_NAMES = [
    "Companion: Bastila Shan", "Companion: Canderous Ordo", "Companion: Carth Onasi",
    "Companion: HK-47", "Companion: Jolee Bindo", "Companion: Juhani",
    "Companion: Mission Vao", "Companion: T3-M4", "Companion: Zaalbar",
]

# CompanionClass (Options.py) -- the 7 non-droid companions, and the 4 of
# those who are NOT already Jedi in vanilla (jedi_companion mode only ever
# touches these 4; Bastila/Jolee/Juhani keep their vanilla Jedi class in
# that mode). Keys match KotorClient.py's COMPANION_IDX_TO_ARM suffix
# ("companion_<key>") and generate_trampoline_batch.py's _COMPANION_TAGS.
COMPANION_CLASS_KEYS = ["bastila", "canderous", "carth", "jolee", "juhani", "mission", "zaalbar"]
NON_JEDI_COMPANION_KEYS = ["carth", "canderous", "zaalbar", "mission"]
BASE_CLASS_NAMES = ["soldier", "scout", "scoundrel"]
JEDI_CLASS_NAMES = ["guardian", "consular", "sentinel"]
ALL_CLASS_NAMES = BASE_CLASS_NAMES + JEDI_CLASS_NAMES

# The completion-condition markers (Rules.py's set_completion_rules) --
# real items (see Items.py's own comment on why NOT code=None Events)
# locked via place_locked_item() at their matching Locations.py locations
# instead of drawing a normal random reward. Location name -> item name.
# Two are dedicated new locations (Level 20 Reached/Malak Defeated); the
# true_balance pair reuses two EXISTING alignment locations instead of
# adding new ones. Locked unconditionally regardless of which Goal option
# is actually selected -- simpler, deterministic pool math beats varying
# the location set by option choice for 4 checks out of 220. See
# create_items() for the matching pool-count adjustment.
GOAL_EVENT_LOCATIONS: typing.Dict[str, str] = {
    "Malak Defeated": "Malak Defeated",
    "Level 20 Reached": "Reached Level 20",
    "Alignment: Dark Side 0": "Reached Dark Side 0",
    "Alignment: Light Side 100": "Reached Light Side 100",
}

# equipment_slot values (gear_items.json) that count as "Armor/Equipment"
# for item_distribution_type's weighted draw -- everything else with a
# blank slot is a Consumable, and "Weapon" is its own category. See
# KotorWorld._gear_category_pools().
_ARMOR_SLOTS = {"Arm", "Belt", "Body", "Hands", "Hands/Implant", "Head", "Implant"}

# The 5 planets with covered shops, keyed by name (used as fill_slot_data's
# per-planet shop_stock dict key) -- module-prefix mapping duplicated in
# generate_trampoline_batch.py/arm_orchestrator.py since those are separate
# dev-tooling scripts, not part of this apworld package. Same real module
# prefixes EntranceRando.py already relies on elsewhere in this file.
PLANET_MODULE_PREFIXES: typing.Dict[str, str] = {
    "taris": "tar_m",
    "dantooine": "danm",
    "kashyyyk": "kas_m",
    "manaan": "manm",
    "korriban": "korr_m",
}

# Fixed baseline used when item_distribution_type is "normal" -- a
# sensible mix that doesn't need any tuning. Player-decided weights are
# read from the matching Options.py Range fields instead; "randomized"
# rolls its own per-seed. See Options.py's ItemDistributionType docstring.
_DEFAULT_DISTRIBUTION_WEIGHTS: typing.Dict[str, int] = {
    "weapon": 30, "armor": 20, "consumable": 30,
    "exp": 20, "credit": 10, "skill": 5, "ability": 5,
}


def _shop_pool() -> typing.List[str]:
    """resrefs flagged shop_randomize in gear_items.json, sorted for a
    deterministic sample() regardless of the JSON's own key order (which
    can shift as the user hand-edits it)."""
    gear = read_gear_json()
    return sorted(resref for resref, data in gear.items() if data.get("shop_randomize"))


class KotorWebWorld(WebWorld):
    theme = "stone"
    tutorials = []


class KotorWorld(World):
    """
    Archipelago integration for Knights of the Old Republic. Locations are
    real, game-wide quest completions (100 of KOTOR's 101 journal
    categories, spanning every planet), companion recruitments, area
    visits, alignment thresholds, character levels 2-20, and Malak's
    defeat -- see worlds/kotor/Locations.py. All detected live via the
    injected extender reading the game's own state. Items cover the full
    set of grants the extender can apply: skills, companions, class
    switches, ability increases, xp, and credits. Feats are deliberately
    not an AP item -- left entirely to normal in-game level-up choices.
    Regions are currently flat/ungated (see Rules.py) -- real progression
    gating is separate future work. The Level 20/Malak Defeated locations
    each carry a locked Event item instead of a normal reward, giving
    set_completion_rules() a real, non-trivial signal for the
    defeat_malak/max_level Goal options (true_balance's own completion
    signal is still entirely client-side -- see Rules.py).
    """
    game = "KotOR"
    web = KotorWebWorld()
    options_dataclass = KotorOptions
    options: KotorOptions

    item_name_to_id = item_name_to_id
    location_name_to_id = location_name_to_id

    def _active_locations(self) -> dict:
        """location_table filtered for companion_mode=none, which
        removes those 9 locations entirely rather than leaving them
        permanently uncompletable. Used by both create_regions() and
        create_items() so the pool size always matches what's actually
        placed -- computing this independently in each would risk the two
        silently drifting out of sync."""
        if self.options.companion_mode == 2:  # none
            return {name: data for name, data in location_table.items()
                     if data.location_type != "companion"}
        return location_table

    def create_regions(self) -> None:
        menu = Region("Menu", self.player, self.multiworld)
        self.multiworld.regions.append(menu)

        active = self._active_locations()
        region_names = sorted({data.region for data in active.values()})
        regions = {}
        for name in region_names:
            r = Region(name, self.player, self.multiworld)
            self.multiworld.regions.append(r)
            menu.connect(r)
            regions[name] = r

        for loc_name, loc_data in active.items():
            region = regions[loc_data.region]
            location = KotorLocation(self.player, loc_name, loc_data.id, region)
            region.locations.append(location)
            event_item_name = GOAL_EVENT_LOCATIONS.get(loc_name)
            if event_item_name is not None:
                # Real item with a real code (see Items.py's own comment on
                # why this can't be a code=None Event) via the normal
                # create_item() path -- NOT constructed by hand here, so it
                # goes through item_table like everything else and can't
                # drift out of sync with it.
                location.place_locked_item(self.create_item(event_item_name))

        # Separate physical-module region graph purely for door/trigger
        # entrance randomization -- does not touch the thematic regions
        # built above, which are what actually govern location access.
        # See EntranceRando.py's module docstring for why these coexist
        # independently.
        if self.options.area_randomizer:
            EntranceRando.create_transition_regions(self)

    def connect_entrances(self) -> None:
        if self.options.area_randomizer:
            EntranceRando.connect_entrances(self)

    def create_item(self, name: str) -> KotorItem:
        data = item_table[name]
        return KotorItem(name, data.classification, data.code, self.player)

    def generate_early(self) -> None:
        """Precollected (starting-inventory) items: the starting_class
        choice (only when starting_class is "jedi_start" -- "jedi_granted"
        places the same item in the shuffled pool instead, see
        create_items()) and
        any starting ability/skill boosts. These are handed to the player
        immediately rather than placed in the shuffled pool."""
        if self.options.starting_class == 1:  # jedi_start
            class_name = JEDI_CLASS_ITEMS[self.options.jedi_class.value]
            self.multiworld.push_precollected(self.create_item(class_name))
        elif self.options.starting_class == 3:  # random_class
            # Independent of jedi_class entirely -- rolls all 6 classes,
            # applied immediately like "start" above (precollected, not
            # item-gated). Same seeded-RNG-in-generate_early() pattern as
            # the CompanionClass companion rolls just below.
            rolled_class = self.random.choice(ALL_CLASS_NAMES)
            item_name = CLASS_NAME_TO_ITEM[rolled_class]
            self.multiworld.push_precollected(self.create_item(item_name))

        # CompanionClass companion rolls -- computed once, here, using this
        # player's own seeded RNG, so both create_items() (jedi_companion's
        # guaranteed item placement) and fill_slot_data() (no_jedi/
        # randomize_all's companion_class_rolls map, applied automatically at
        # recruit by KotorClient.py) see the same values. self.companion_class_rolls
        # is sent to the client as-is; self.jedi_companion_items is
        # consulted only by create_items() below (not sent directly -- the
        # class per companion is implicit in which of the 3 static items
        # gets placed).
        self.companion_class_rolls: typing.Dict[str, str] = {}
        self.jedi_companion_items: typing.Dict[str, str] = {}
        mode = self.options.companion_class.value
        if mode == 1:  # no_jedi
            for key in COMPANION_CLASS_KEYS:
                self.companion_class_rolls[key] = self.random.choice(BASE_CLASS_NAMES)
        elif mode == 2:  # jedi_companion
            for key in NON_JEDI_COMPANION_KEYS:
                self.jedi_companion_items[key] = self.random.choice(JEDI_CLASS_NAMES)
        elif mode == 3:  # randomize_all
            for key in COMPANION_CLASS_KEYS:
                self.companion_class_rolls[key] = self.random.choice(ALL_CLASS_NAMES)

        for arm_name, option_name in STARTING_ABILITY_ARMS.items():
            points = getattr(self.options, option_name).value
            item_name = arm_name_to_item[arm_name]
            for _ in range(points):  # +1 point per firing
                self.multiworld.push_precollected(self.create_item(item_name))

        for arm_name, option_name in STARTING_SKILL_ARMS.items():
            points = getattr(self.options, option_name).value
            item_name = arm_name_to_item[arm_name]
            firings = -(-points // 2)  # +2 points per firing, rounded up
            for _ in range(firings):
                self.multiworld.push_precollected(self.create_item(item_name))

    def create_items(self) -> None:
        # -len(GOAL_EVENT_LOCATIONS): those 2 locations got a locked Event
        # item in create_regions() instead of drawing from this pool --
        # without this adjustment the pool would be 2 items short of the
        # real number of fillable (non-event) location slots.
        active_count = len(self._active_locations()) - len(GOAL_EVENT_LOCATIONS)

        # Companions (when companion_mode is ap_gated) and the starting_class
        # class item (when starting_class is "jedi_granted") are the only
        # things ever unconditionally guaranteed in the pool -- "jedi_granted"
        # means the player WILL become a Jedi at some point, never a matter of
        # luck, same guarantee companions get. When starting_class is
        # "jedi_start" the item is precollected in generate_early() instead
        # (not part of this pool-sizing math at all); when "off" there's no
        # class item anywhere. Everything else -- curated gear, Skills,
        # Abilities, EXP, Credits -- is drawn through the weighted
        # distribution in _distribute_items() instead. Feats are not an AP
        # item at all any more (see Items.py) -- left entirely to normal
        # in-game level-up choices.
        mandatory_names = COMPANION_ITEM_NAMES if self.options.companion_mode == 0 else []
        if self.options.starting_class == 2:  # jedi_granted
            mandatory_names = mandatory_names + [JEDI_CLASS_ITEMS[self.options.jedi_class.value]]
        # CompanionClass=jedi_companion: same guaranteed-placement guarantee
        # as starting_class=granted -- the roll already happened in
        # generate_early(), this just places whichever of the 3 static
        # per-companion items matches it.
        for key, class_name in self.jedi_companion_items.items():
            mandatory_names = mandatory_names + [f"Jedi Training: {key.capitalize()} ({class_name.capitalize()})"]

        pool = [self.create_item(name) for name in mandatory_names]
        pool += self._distribute_items(active_count - len(pool))
        self.multiworld.itempool += pool

    def _gear_category_pools(self) -> typing.Dict[str, typing.List[str]]:
        """item_table names (already included_as_item, real AP items with
        real codes) split into weapon/armor/consumable buckets by their
        real equipment_slot in gear_items.json. Used only by
        _distribute_items() below."""
        pools: typing.Dict[str, typing.List[str]] = {"weapon": [], "armor": [], "consumable": []}
        gear = read_gear_json()
        if not gear:
            return pools
        for name, data in item_table.items():
            if not data.arm_name.startswith("give_item:"):
                continue
            resref = data.arm_name[len("give_item:"):]
            gear_data = gear.get(resref)
            if gear_data is None:
                continue
            slot = gear_data.get("equipment_slot") or ""
            if slot == "Weapon":
                pools["weapon"].append(name)
            elif slot in _ARMOR_SLOTS:
                pools["armor"].append(name)
            else:
                pools["consumable"].append(name)
        return pools

    def _skill_ability_pools(self) -> typing.Tuple[typing.List[str], typing.List[str]]:
        """Item names for the 8 Skill and 6 Ability Increase items,
        derived from Options.py's STARTING_SKILL_ARMS/STARTING_ABILITY_ARMS
        arm-name keys (the same source of truth generate_early() uses for
        starting boosts) rather than a second hand-written list."""
        skills = [arm_name_to_item[arm] for arm in STARTING_SKILL_ARMS if arm in arm_name_to_item]
        abilities = [arm_name_to_item[arm] for arm in STARTING_ABILITY_ARMS if arm in arm_name_to_item]
        return skills, abilities

    def _distribute_items(self, needed: int) -> typing.List[KotorItem]:
        """Fills `needed` pool slots -- almost the entire pool, since only
        companions are ever separately guaranteed (see create_items()) --
        by drawing from 7 weighted categories: Weapons, Armor/Equipment,
        Consumables, EXP, Credits, Skills, Abilities. "normal" uses a
        fixed baseline (_DEFAULT_DISTRIBUTION_WEIGHTS); "player_decided"
        reads the matching weight options instead; "randomized" rolls its
        own per-seed. Weights are relative, not required to sum to 100. A
        category with no real candidates given other options (e.g. EXP
        when experience_mode is off, or Weapons/Armor/Consumables
        when receive_inventory_items is off) is dropped and the rest
        renormalized automatically. See Options.py's ItemDistributionType
        docstring for the full design."""
        if needed <= 0:
            return []

        gear_pools = self._gear_category_pools() if self.options.receive_inventory_items else \
            {"weapon": [], "armor": [], "consumable": []}
        skill_pool, ability_pool = self._skill_ability_pools()
        categories: typing.Dict[str, typing.List[str]] = {
            "weapon": gear_pools["weapon"],
            "armor": gear_pools["armor"],
            "consumable": gear_pools["consumable"],
            "exp": ["Experience Points"] if self.options.experience_mode == 2 else [],
            "credit": ["Republic Credits"] if self.options.credit_mode == 2 else [],
            "skill": skill_pool,
            "ability": ability_pool,
        }

        dist_type = self.options.item_distribution_type.value
        if dist_type == 0:  # normal -- fixed project-chosen baseline
            weights = dict(_DEFAULT_DISTRIBUTION_WEIGHTS)
        elif dist_type == 2:  # randomized -- weights rolled per-seed via this player's own seeded RNG
            weights = {k: self.random.randint(1, 100) for k in categories}
        else:  # player_decided
            weights = {
                "weapon": self.options.weapon_weight.value,
                "armor": self.options.armor_weight.value,
                "consumable": self.options.consumable_weight.value,
                "exp": self.options.exp_weight.value,
                "credit": self.options.credit_weight.value,
                "skill": self.options.skill_weight.value,
                "ability": self.options.ability_weight.value,
            }

        available = {k: w for k, w in weights.items() if w > 0 and categories[k]}
        if not available:
            # Nothing biddable at all (e.g. every relevant option toggled
            # off, including skill/ability weights zeroed under
            # player_decided) -- fall back to a safely-repeatable filler
            # rather than dividing by zero on an empty weight table.
            return [self.create_item("Skill: Computer Use") for _ in range(needed)]

        total_weight = sum(available.values())
        result: typing.List[KotorItem] = []
        for _ in range(needed):
            roll = self.random.uniform(0, total_weight)
            upto = 0.0
            for key, w in available.items():
                upto += w
                if roll <= upto:
                    result.append(self.create_item(self.random.choice(categories[key])))
                    break
        return result

    def get_filler_item_name(self) -> str:
        return filler_items[0]

    def fill_slot_data(self) -> dict:
        """Exposed so KotorClient.py can read the active companion/XP/credits
        mode after connecting -- these change client-side behavior (whether
        a companion check self-fulfills, whether XP gets clamped on area
        transitions, and by how much) that can't be inferred from the item
        pool alone."""
        return {
            "companion_mode": self.options.companion_mode.value,
            "starting_class": self.options.starting_class.value,
            "experience_mode": self.options.experience_mode.value,
            "experience_limiter": self.options.experience_limiter.value,
            "experience_item": self.options.experience_item.value,
            "credit_mode": self.options.credit_mode.value,
            "credit_limiter": self.options.credit_limiter.value,
            "credit_item": self.options.credit_item.value,
            "death_link": bool(self.options.death_link),
            "receive_inventory_items": bool(self.options.receive_inventory_items),
            "consumable_stack_count": self.options.consumable_stack_count.value,
            "shop_item_count": self.options.shop_item_count.value,
            "loot_mode": self.options.loot_mode.value,
            "area_randomizer": bool(self.options.area_randomizer),
            "door_mapping": getattr(self, "kotor_door_mapping", None),
            "goal": self.options.goal.value,
            "shop_stock": self._shop_stock(),
            # CompanionClass=no_jedi/randomize_all only -- jedi_companion's
            # assignments are implicit in which "Jedi Training: ..." item
            # got placed (see create_items()), not sent here. Empty dict
            # for off/jedi_companion.
            "companion_class_rolls": self.companion_class_rolls,
        }

    def _shop_stock(self) -> typing.Dict[str, typing.List[str]]:
        """Picks shop_item_count resrefs from the shop_randomize pool
        INDEPENDENTLY per planet, using this player's seeded RNG -- each of
        the 5 covered planets (Taris/Dantooine/Kashyyyk/Manaan/Korriban)
        gets its own distinct catalog instead of one universal list shared
        by every shop (see Options.py's ShopItemCount).

        ALWAYS returns all 5 planet keys, even when shop_randomizer is off
        (empty list per planet then) -- 2026-08-29, fixing a real bug found
        live: this used to return {} when shop_randomizer was off, and
        KotorClient.py skipped sending anything at all for an empty dict,
        which meant _shop_stock.json (a file that persists across
        sessions/seeds on the player's machine, not tied to any one
        connection) never got cleared when reconnecting to a
        shop_randomizer=off seed after previously playing one with it on --
        stale stock from the OLD seed would silently keep populating any
        store the player walked into. Returning real (even if empty) lists
        for every planet, unconditionally, means every fresh Connect always
        overwrites all 5 planets' entries with the CURRENT seed's real
        answer -- never leaves a previous seed's data lying around."""
        if not self.options.shop_randomizer:
            return {planet: [] for planet in PLANET_MODULE_PREFIXES}
        count = self.options.shop_item_count.value
        pool = _shop_pool()
        return {
            planet: self.random.sample(pool, min(count, len(pool)))
            for planet in PLANET_MODULE_PREFIXES
        }

    def set_rules(self) -> None:
        set_rules(self.multiworld, self.player)
        set_completion_rules(self.multiworld, self.player)
