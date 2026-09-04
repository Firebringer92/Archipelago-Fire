import typing
from dataclasses import dataclass

from Options import Choice, DeathLink, PerGameCommonOptions, Range, Toggle


class CompanionMode(Choice):
    """Controls how the 9 companions are handled.

    ap_gated: companions are real AP checks/items. Their vanilla recruit
    trigger is suppressed; the moment would-be-recruit is still reported as
    a completed check, but the companion only actually joins once you
    receive that companion's item from the multiworld.

    normal: companions join exactly like stock KOTOR, with no AP gating --
    the recruit moment still registers as a completed check (for tracking),
    but it self-fulfills instantly instead of waiting on a received item.

    none: companions never join at all. Their 9 locations are removed
    from the pool entirely rather than left permanently uncompletable.
    """
    display_name = "Companion Mode"
    option_ap_gated = 0
    option_normal = 1
    option_none = 2
    default = 1


class StartingClass(Choice):
    """Controls how (and whether) you become a Jedi, using the class
    chosen in jedi_class.

    off (default): vanilla -- no AP item at all, the normal Dantooine
    trials handle your class change exactly like stock KOTOR.

    jedi_start: the class chosen in jedi_class is already in your starting
    inventory -- you have it from the moment you connect.

    jedi_granted: the class chosen in jedi_class is a real item placed
    somewhere in the shuffled pool instead of your starting inventory --
    you become a Jedi partway through the game, whenever that item
    reaches you through the multiworld, same as any other received item.
    Guaranteed to be placed somewhere (like the companions), not subject
    to the weighted item_distribution_type draw, so choosing this always
    results in becoming a Jedi at some point, never a matter of luck.

    random_class: ignores jedi_class entirely -- your OWN starting class
    is independently rolled to any of all 6 classes (Soldier/Scout/
    Scoundrel/Guardian/Consular/Sentinel), applied immediately at the
    start of the game like "jedi_start" above, not item-gated. A Jedi roll
    becomes a real multiclass exactly like jedi_start/jedi_granted
    (AddMultiClass); a base-class roll REPLACES your character-creation
    class instead, using the same direct class-write mechanism
    CompanionClass already uses for companions.

    Under any mode except "off", Dantooine's real trial-completion script
    is suppressed so simply playing through it normally can't ALSO grant
    (or duplicate) a class outside this option's own control.
    """
    display_name = "Starting Class"
    option_off = 0
    option_jedi_start = 1
    option_jedi_granted = 2
    option_random_class = 3
    default = 0


class JediClass(Choice):
    """Which Jedi class you become. Only consulted when starting_class is
    jedi_start or jedi_granted -- ignored entirely by random_class, which
    rolls its own class independently."""
    display_name = "Jedi Class"
    option_guardian = 0
    option_consular = 1
    option_sentinel = 2
    default = 0


class CompanionClass(Choice):
    """Randomizes the class of the 7 non-droid companions (Bastila,
    Canderous, Carth, Jolee, Juhani, Mission, Zaalbar -- HK-47 and T3-M4
    are droids and never affected). Independent of starting_class/jedi_class,
    which only ever control the PC's own class.

    off (default): vanilla -- every companion keeps their normal class.

    no_jedi: all 7 companions independently roll one of Soldier/Scout/
    Scoundrel, including Bastila/Jolee/Juhani -- guarantees no Jedi
    companions at all, applied automatically the moment each one joins.

    jedi_companion: only the 4 non-Jedi companions (Carth, Canderous,
    Zaalbar, Mission) independently roll one of Guardian/Consular/
    Sentinel. Unlike the other two modes, this is item-gated: each
    eligible companion gets exactly one guaranteed-placement item (the
    class was already decided by the roll), and their class only changes
    once that item is received -- works regardless of whether they're
    recruited yet. Bastila/Jolee/Juhani are untouched.

    randomize_all: all 7 companions independently roll one of all 6
    classes (Soldier/Scout/Scoundrel/Guardian/Consular/Sentinel), applied
    automatically at recruit like no_jedi.
    """
    display_name = "Companion Class"
    option_off = 0
    option_no_jedi = 1
    option_jedi_companion = 2
    option_randomize_all = 3
    default = 0


class ExperienceMode(Choice):
    """Controls how (and whether) you receive AP-driven XP. Either way
    besides off, vanilla combat/quest XP is clamped down to an "expected"
    total on every area transition.

    off (default): pure vanilla XP, completely untouched -- no clamping,
    no items, combat/quest XP behaves exactly like stock KOTOR.

    ap_limited: no items involved. Your expected XP is computed directly
    from how many of YOUR OWN locations you've checked off so far, times
    experience_limiter -- independent of what anyone sends you, so your
    level tracks your own progress through the game rather than the
    multiworld's item flow.

    ap_gated: XP comes from "Experience Points" items received through the
    multiworld. Each item is worth experience_item XP. Your level is gated
    on what other players send you, same as any other AP item.
    """
    display_name = "EXP Mode"
    option_off = 0
    option_ap_limited = 1
    option_ap_gated = 2
    default = 0


class ExperienceLimiter(Range):
    """XP granted per YOUR OWN completed check, when experience_mode is
    "ap_limited". Total expected XP = (your own checks completed) x this
    value, recalculated as you complete more checks, up to ~200 real
    locations at full completion. Max matches experience_item's own max
    (both are per-unit values multiplied by essentially the same ~200-item/
    check ceiling, so equal maxes keep the two modes' total-XP ceilings
    equivalent). Default of 600 lands a full-completion run around
    120,000 XP (level 16 per exptable.2da), matching experience_item's own
    default outcome under the default 7-category item distribution."""
    display_name = "EXP Limiter"
    range_start = 1
    range_end = 20000
    default = 600


class ExperienceItem(Range):
    """How much XP each "Experience Points" item grants, when
    experience_mode is "ap_gated". Grounded in KOTOR's real cumulative
    level table (exptable.2da: level 10 = 45000, level 15 = 105000,
    level 16 = 120000, level 20/cap = 190000). With the default 7-category
    item distribution (Weapon 30/Armor 20/Consumable 30/EXP 20/Credit 10/
    Skill 5/Ability 5), a full playthrough lands around 32 Experience
    Points items -- the default of 4000 puts that at ~128,000 total XP,
    comfortably in the level 16-17 range, not a forced grind to the
    level-20 cap and not a stalled-out early game either. Raise it for a
    faster/easier power curve, lower it to make leveling scarcer. Note:
    the actual item count varies with your other options (gear/credits
    toggles, item_distribution_type) since it's drawn from a weighted
    pool, not a fixed count -- this default is calibrated against the
    "everything enabled, normal distribution" baseline specifically."""
    display_name = "EXP Item"
    range_start = 1
    range_end = 20000
    default = 4000


class CreditMode(Choice):
    """Controls how (and whether) you receive AP-driven credits. Mirrors
    experience_mode's shape exactly -- both ap_limited and ap_gated clamp
    vanilla credit gains (loot, quest rewards, selling items) down to an
    "expected" total, correcting once per poll rather than once per area
    transition (spending is granular enough -- shop purchases especially --
    that waiting for a transition would be too coarse). A real spend
    (credits going down) is never fought -- detected and treated as
    legitimate, lowering the expected total by the same amount instead of
    trying to "restore" money you just spent. Confirmed live 2026-09-03:
    credits can now be set to an exact value in either direction (not just
    topped up -- see KSE_SetCredits), which is what makes this clamp-down
    design possible at all; the old GiveGoldToCreature/TakeGoldFromCreature
    mechanism could only ever increase credits.

    off (default): pure vanilla credits, completely untouched -- no
    clamping, no items, credits behave exactly like stock KOTOR.

    ap_limited: no items involved -- your expected credit total is
    computed directly from how many of YOUR OWN locations you've checked
    off so far, times credit_limiter -- independent of what anyone sends
    you, so your credits track your own progress through the game rather
    than the multiworld's item flow.

    ap_gated: credits come from "Republic Credits" items received through
    the multiworld. Each item is worth credit_item credits. Your credit
    total is gated on what other players send you, same as any other AP
    item.
    """
    display_name = "Credit Mode"
    option_off = 0
    option_ap_limited = 1
    option_ap_gated = 2
    default = 0


class CreditLimiter(Range):
    """Credits granted per YOUR OWN completed check, when credit_mode is
    "ap_limited". Total expected credits = (your own checks completed) x
    this value, recalculated as you complete more checks. Mirrors
    experience_limiter's shape exactly."""
    display_name = "Credit Limiter"
    range_start = 1
    range_end = 20000
    default = 100


class CreditItem(Range):
    """How many credits each "Republic Credits" item grants, when
    credit_mode is "ap_gated". Mirrors experience_item's shape exactly.
    Replaces the old fixed 5000-per-item amount with a configurable
    value."""
    display_name = "Credit Item"
    range_start = 1
    range_end = 20000
    default = 5000


# Starting ability/skill boosts -- each is an extra flat amount granted at
# game start (via precollected items), on top of whatever the player rolls
# at character creation. Default 0 on all of these = vanilla, untouched.
# These reuse the same increment-only arms already proven for skills/
# Charisma -- KOTOR has no native "set ability score to X" call, only
# relative Effect-based increases, so a "starting boost of N" fires the
# matching arm enough times to add up to N, not a hard override. Unified
# to a single 0-9 range across every ability/skill (previously abilities
# capped at 6 and skills at 10) so the whole starting-stats block reads as
# one consistent scale regardless of which stat it's for.
class StartingStrength(Range):
    """Extra Strength points granted at game start (on top of character
    creation)."""
    display_name = "Starting Strength Boost"
    range_start = 0
    range_end = 9
    default = 0


class StartingDexterity(Range):
    """Extra Dexterity points granted at game start (on top of character
    creation)."""
    display_name = "Starting Dexterity Boost"
    range_start = 0
    range_end = 9
    default = 0


class StartingConstitution(Range):
    """Extra Constitution points granted at game start (on top of character
    creation)."""
    display_name = "Starting Constitution Boost"
    range_start = 0
    range_end = 9
    default = 0


class StartingIntelligence(Range):
    """Extra Intelligence points granted at game start (on top of character
    creation)."""
    display_name = "Starting Intelligence Boost"
    range_start = 0
    range_end = 9
    default = 0


class StartingWisdom(Range):
    """Extra Wisdom points granted at game start (on top of character
    creation)."""
    display_name = "Starting Wisdom Boost"
    range_start = 0
    range_end = 9
    default = 0


class StartingCharisma(Range):
    """Extra Charisma points granted at game start (on top of character
    creation)."""
    display_name = "Starting Charisma Boost"
    range_start = 0
    range_end = 9
    default = 0


class StartingComputerUse(Range):
    """Extra Computer Use skill ranks granted at game start."""
    display_name = "Starting Computer Use Boost"
    range_start = 0
    range_end = 9
    default = 0


class StartingDemolitions(Range):
    """Extra Demolitions skill ranks granted at game start."""
    display_name = "Starting Demolitions Boost"
    range_start = 0
    range_end = 9
    default = 0


class StartingStealth(Range):
    """Extra Stealth skill ranks granted at game start."""
    display_name = "Starting Stealth Boost"
    range_start = 0
    range_end = 9
    default = 0


class StartingAwareness(Range):
    """Extra Awareness skill ranks granted at game start."""
    display_name = "Starting Awareness Boost"
    range_start = 0
    range_end = 9
    default = 0


class StartingPersuade(Range):
    """Extra Persuade skill ranks granted at game start."""
    display_name = "Starting Persuade Boost"
    range_start = 0
    range_end = 9
    default = 0


class StartingRepair(Range):
    """Extra Repair skill ranks granted at game start."""
    display_name = "Starting Repair Boost"
    range_start = 0
    range_end = 9
    default = 0


class StartingSecurity(Range):
    """Extra Security skill ranks granted at game start."""
    display_name = "Starting Security Boost"
    range_start = 0
    range_end = 9
    default = 0


class StartingTreatInjury(Range):
    """Extra Treat Injury skill ranks granted at game start."""
    display_name = "Starting Treat Injury Boost"
    range_start = 0
    range_end = 9
    default = 0


class ReceiveInventoryItems(Toggle):
    """Whether curated gear items (weapons, armor, and other equipment
    flagged as included_as_item in gear_items.json) are ELIGIBLE to appear
    in the AP item pool at all -- this doesn't guarantee any specific gear
    item, it just makes the Weapons/Armor/Consumables categories in
    item_distribution_type available to draw from. Off means the gear
    system is completely inert -- no gear items in the pool, no shop
    stocking either."""
    display_name = "Receive Inventory Items"
    default = False


class ConsumableStackCount(Range):
    """How many of a consumable gear item (grenades, medpacs, stims --
    anything without an equipment slot) are granted per item received,
    before being capped by that item's own real in-game stack limit.
    Equipment (weapons, armor, wearables) always grants exactly 1
    regardless of this setting -- it doesn't make sense to grant multiple
    of something you can only wear/wield one of at a time."""
    display_name = "Consumable Stack Count"
    range_start = 1
    range_end = 99
    default = 10


class ShopRandomizer(Toggle):
    """Whether shops get restocked with a curated random selection at all.
    Off (default): every shop keeps its normal vanilla inventory,
    untouched. On: shop_item_count items get drawn from the curated
    shop_randomize pool and stocked in every covered shop, replacing its
    vanilla inventory on first visit."""
    display_name = "Shop Randomizer"
    default = False


class ShopItemCount(Range):
    """How many items to stock in each shop, drawn randomly from the
    curated shop_randomize pool in gear_items.json, replacing that shop's
    entire vanilla inventory. Only consulted when shop_randomizer is On.
    Capped at 30, the batch size already proven safe for a single
    trampoline firing this session; this is a one-time restock on each
    shop's first visit, not a repeating reroll."""
    display_name = "Shop Item Count"
    range_start = 1
    range_end = 30
    default = 30


class AreaRandomizer(Toggle):
    """Whether doors and area-transition triggers are shuffled to lead
    somewhere other than their vanilla destination. Uncoupled: the door you
    use to leave a room is not guaranteed to lead back to wherever you
    entered from -- each of the 156 real transitions game-wide is
    independently randomized, using Archipelago's own entrance
    randomization engine (dead-end detection, no guessed logic beyond
    region connectivity, since this game's access rules are still flat/
    ungated). The mapping is fixed once per seed: every door leads to the
    same shuffled destination for the whole playthrough. Off means every
    door/trigger keeps its normal vanilla destination. Like item
    suppression, this is a real, game-file-level patch applied once by a
    standalone script (not something the live AP client toggles), so this
    option's actual effect depends on that patch step having been run for
    the seed you're playing."""
    display_name = "Area Randomizer"
    default = False


class LootMode(Choice):
    """What happens to a picked-up item NOT on the AP-allowed whitelist
    (quest_dependent items are always left alone regardless of this
    option -- see patch_item_suppression.py). Replaces the earlier
    two-toggle randomize_loot/allow_normal_loot design (2 booleans
    producing 4 behaviors was more confusing than one 4-way choice for the
    same thing) -- same 4 behaviors, one option:

      normal (default): untouched -- pure vanilla, nothing wired up at all.
      destroy: the pickup is destroyed immediately, no replacement.
      bonus: the pickup is kept, and a random item (drawn from the
        shop_randomize pool) is granted on top -- throttled to one bonus
        per every 5 genuine non-whitelisted items found (a running count,
        not per-pickup), immune to the engine's own item-reacquisition
        re-firing on area transitions by construction (see
        patch_item_suppression.py/generate_poll_shared.py for why).
      replace: the pickup is destroyed and replaced with one random item
        from the same pool, immediately, one-for-one.

    This is a real, game-file-level patch applied once by
    scripts/patch_item_suppression.py (not something the AP client toggles
    live), so this option's actual effect depends on that patch step
    having been run for the seed you're playing."""
    display_name = "Loot Mode"
    option_normal = 0
    option_destroy = 1
    option_bonus = 2
    option_replace = 3
    default = 0


class ItemDistributionType(Choice):
    """Controls how almost the entire item pool is composed. Only
    companions (when companion_mode is ap_gated) are ever unconditionally
    guaranteed in the pool -- everything else (curated gear, Skills,
    Abilities, EXP, Credits) is drawn proportionally from the 7 categories
    below, across whichever pool slots aren't taken by those guaranteed
    companion items -- the starting_class class item (when starting_class
    is "granted") is ALSO unconditionally guaranteed the same way, never
    subject to this weighted draw. When starting_class is "start" it's
    precollected at game start instead, still never placed in the pool;
    when "off" there's no class item at all.

    normal (default): uses a fixed, project-chosen baseline distribution
    (Weapons 30 / Armor 20 / Consumables 30 / EXP 20 / Credits 10 /
    Skills 5 / Abilities 5) -- a sensible mix that doesn't need any
    tuning.

    player_decided: uses the 7 weight options below instead of the fixed
    baseline. Weights are relative, not required to sum to 100 -- doubling
    every weight produces the same distribution. A category that isn't
    actually available given your other options (e.g. EXP when
    experience_mode is off, or ap_limited XP mode which doesn't use
    items at all, or Weapons/Armor/Consumables when receive_inventory_items
    is off) is skipped and the remaining weights are renormalized
    automatically.

    randomized: same as player_decided, but the 7 weights are generated
    randomly per seed instead of read from your YAML.
    """
    display_name = "Item Distribution Type"
    option_normal = 0
    option_player_decided = 1
    option_randomized = 2
    default = 0


class WeaponWeight(Range):
    """Relative weight for weapons in the distributed pool. Only
    consulted when item_distribution_type is player_decided. See
    item_distribution_type's own description for how weights work."""
    display_name = "Weapon Distribution Weight"
    range_start = 0
    range_end = 100
    default = 30


class ArmorWeight(Range):
    """Relative weight for armor/equipment in the distributed pool. Only
    consulted when item_distribution_type is player_decided."""
    display_name = "Armor Distribution Weight"
    range_start = 0
    range_end = 100
    default = 20


class ConsumableWeight(Range):
    """Relative weight for consumables (grenades, medpacs, stims, and
    other unworn items) in the distributed pool. Only consulted when
    item_distribution_type is player_decided."""
    display_name = "Consumable Distribution Weight"
    range_start = 0
    range_end = 100
    default = 30


class ExpWeight(Range):
    """Relative weight for Experience Points in the distributed pool. Only
    consulted when item_distribution_type is player_decided, and only has
    any effect when experience_mode is ap_gated (Experience Points items
    don't exist at all otherwise)."""
    display_name = "EXP Distribution Weight"
    range_start = 0
    range_end = 100
    default = 20


class CreditWeight(Range):
    """Relative weight for Republic Credits items in the distributed pool.
    Only consulted when item_distribution_type is player_decided, and
    only has any effect when credit_mode is ap_gated (Republic Credits
    items don't exist at all otherwise)."""
    display_name = "Credit Distribution Weight"
    range_start = 0
    range_end = 100
    default = 10


class SkillWeight(Range):
    """Relative weight for the 8 Skill items (Computer Use, Demolitions,
    Stealth, Awareness, Persuade, Repair, Security, Treat Injury) in the
    distributed pool. Only consulted when item_distribution_type is
    player_decided. Kept low by default -- these are meant to show up
    occasionally, not dominate the pool."""
    display_name = "Skill Distribution Weight"
    range_start = 0
    range_end = 100
    default = 5


class AbilityWeight(Range):
    """Relative weight for the 6 Ability Increase items (Strength,
    Dexterity, Constitution, Intelligence, Wisdom, Charisma) in the
    distributed pool. Only consulted when item_distribution_type is
    player_decided. Kept low by default -- these are meant to show up
    occasionally, not dominate the pool."""
    display_name = "Ability Distribution Weight"
    range_start = 0
    range_end = 100
    default = 5


class Goal(Choice):
    """What counts as winning the game.

    defeat_malak (default): the game is won the moment Darth Malak is
    defeated aboard the Star Forge -- detected via STA_MALAK_DEAD, a real
    globalcat.2da flag set unconditionally across every narrative branch
    of that fight (Bastila redeemed or turned, however many captive Jedi
    were drained), never reset.

    true_balance: the game is won once you've reached BOTH alignment
    extremes (Light Side 100 and Dark Side 0) at some point in the same
    playthrough -- not simultaneously, just visited each extreme at some
    point, tracked the same way the True Neutral/Fallen Jedi/Redeemed
    Sith alignment bonus checks already are.

    max_level: the game is won on reaching character level 20, KOTOR's
    real level cap (exptable.2da).
    """
    display_name = "Goal"
    option_defeat_malak = 0
    option_true_balance = 1
    option_max_level = 2
    default = 0


# arm_name -> (option field name, points-per-arm-firing) for translating a
# starting-boost Range value into "fire this arm N times" at generate time.
# Abilities grant +1 per firing, skills grant +2 per firing -- see the
# matching entries in scripts/generate_trampoline_batch.py's APPLIES table.
STARTING_ABILITY_ARMS: typing.Dict[str, str] = {
    "ability_strength": "starting_strength",
    "ability_dexterity": "starting_dexterity",
    "ability_constitution": "starting_constitution",
    "ability_intelligence": "starting_intelligence",
    "ability_wisdom": "starting_wisdom",
    "grant_test_ability": "starting_charisma",  # the only existing Charisma arm
}
STARTING_SKILL_ARMS: typing.Dict[str, str] = {
    "computer_use": "starting_computer_use",
    "demolitions": "starting_demolitions",
    "stealth": "starting_stealth",
    "awareness": "starting_awareness",
    "persuade": "starting_persuade",
    "repair": "starting_repair",
    "security": "starting_security",
    "treat_injury": "starting_treat_injury",
}


@dataclass
class KotorOptions(PerGameCommonOptions):
    companion_mode: CompanionMode
    starting_class: StartingClass
    jedi_class: JediClass
    companion_class: CompanionClass
    experience_mode: ExperienceMode
    experience_limiter: ExperienceLimiter
    experience_item: ExperienceItem
    credit_mode: CreditMode
    credit_limiter: CreditLimiter
    credit_item: CreditItem
    death_link: DeathLink
    starting_strength: StartingStrength
    starting_dexterity: StartingDexterity
    starting_constitution: StartingConstitution
    starting_intelligence: StartingIntelligence
    starting_wisdom: StartingWisdom
    starting_charisma: StartingCharisma
    starting_computer_use: StartingComputerUse
    starting_demolitions: StartingDemolitions
    starting_stealth: StartingStealth
    starting_awareness: StartingAwareness
    starting_persuade: StartingPersuade
    starting_repair: StartingRepair
    starting_security: StartingSecurity
    starting_treat_injury: StartingTreatInjury
    receive_inventory_items: ReceiveInventoryItems
    consumable_stack_count: ConsumableStackCount
    shop_randomizer: ShopRandomizer
    shop_item_count: ShopItemCount
    loot_mode: LootMode
    area_randomizer: AreaRandomizer
    item_distribution_type: ItemDistributionType
    weapon_weight: WeaponWeight
    armor_weight: ArmorWeight
    consumable_weight: ConsumableWeight
    exp_weight: ExpWeight
    credit_weight: CreditWeight
    skill_weight: SkillWeight
    ability_weight: AbilityWeight
    goal: Goal
