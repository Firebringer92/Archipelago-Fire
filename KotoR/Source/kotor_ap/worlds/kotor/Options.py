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


class NewCompanion(Toggle):
    """Replaces HK-47 with a new human companion, Meetra Surik (a Jedi
    Sentinel), occupying his exact party slot -- not an addition, a swap.
    His recruitment mechanism (the Tatooine droid-purchase trigger) is
    unchanged; only who you get is different. His personal Ebon Hawk
    subplot is removed entirely and replaced with a single placeholder
    greeting -- the "Ebon Hawk: HK-47" journal check is removed from the
    pool rather than left permanently uncompletable.

    When on, every AP-facing name that would otherwise say "HK-47" for
    his companion item/location (relevant under companion_mode=ap_gated,
    where his companion item is a real placed check) instead reads "New
    Companion" -- this uses a second, always-present item/location pair
    rather than renaming the vanilla HK-47 entries, since AP's item/
    location name-to-id mapping can't vary per player within the same
    multiworld game.

    She is also folded into companion_class and additional_feats exactly
    like the other 7 non-droid companions (no_jedi/randomize_all can
    reroll her; jedi_companion is unaffected -- she's not one of its 4
    target companions).

    Off (default): vanilla HK-47, unchanged."""
    display_name = "New Companion"
    default = False


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
    are droids and never affected; if new_companion is on, Meetra Surik
    is folded in as an 8th eligible companion in his place). Independent
    of starting_class/jedi_class, which only ever control the PC's own
    class.

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


class AdditionalFeats(Toggle):
    """Whether "Additional Feats" items exist in the pool at all. When on,
    one such item is placed per eligible character -- just the PC when
    companion_mode is "none", otherwise the PC plus all 7 non-droid
    companions (Bastila, Canderous, Carth, Jolee, Juhani, Mission,
    Zaalbar -- HK-47 and T3-M4 are droids and never eligible; if
    new_companion is on, Meetra Surik is eligible in his place).

    Receiving one doesn't grant anything immediately -- which 3 feats it
    grants is decided later, once that character is actually recruited
    AND their class has settled (so a Randomize_class-in-progress
    character is never granted feats against a class that's about to
    change out from under them). The 3 feats are drawn randomly from a
    fixed pool spanning every class's weapon/armor proficiencies and
    signature abilities -- e.g. a Scoundrel could end up with Lightsaber
    Proficiency, letting them wield a weapon their own class never would.
    Off (default): no such items exist."""
    display_name = "Additional Feats"
    default = False


class ProgressionSystem(Toggle):
    """Gates 8 real main-questline items (Sith Armor, Sith Papers, Taris
    Shield Codes, Manaan Enviro Suit, and 4 Star Maps -- Tatooine/
    Kashyyyk/Manaan/Korriban) behind real AP checks instead of their
    normal vanilla pickup. (Tatooine Desert Map and the Dantooine Star
    Map were dropped from an original 10-item design after tracing each
    item's real vanilla gate -- neither one turned out to gate anything
    at all.)

    Two different mechanisms depending on the item: Sith Armor/Papers/
    Shield Codes/Enviro Suit are suppressed at their normal vanilla
    acquisition point and granted once the paired check clears, same as
    before. The 4 Star Maps use a DIFFERENT mechanism -- vanilla KOTOR
    has no travel restriction to any planet at all (confirmed via the
    real galaxy-map script), so this option creates an artificial one:
    Tatooine/Kashyyyk/Manaan/Korriban are unreachable via the galaxy map
    until that planet's Star Map check clears.

    A real access-rule layer rides on this (see Rules.py): Taris' Lower
    City and everything past it requires Sith Armor, the Sith Base
    additionally requires Sith Papers, Escaping Taris requires the Shield
    Codes, Manaan's Hrakert Rift (and its own Star Map) requires the
    Enviro Suit, EVERY location on the 4 travel-gated planets requires
    that planet's own Star Map item, and Leviathan/Unknown World/Star
    Forge/the ending require ALL 4 Star Maps. This is a REAL logic layer,
    not flavor -- Archipelago's own generation-time reachability sweep
    uses it to guarantee the seed is actually completable, the same
    mechanism every other Archipelago game's world uses for progression
    gating.

    Off (default): vanilla -- all 8 items behave normally, no access
    rules, no suppression, no artificial travel gate.

    INCOMPATIBLE with area_randomizer -- door/entrance randomization would
    make the reachability logic above impossible to reason about (the
    whole point of the rules above is knowing which real locations sit on
    which side of each gate; scrambling area connections breaks that
    entirely). Enabling both raises an error at generation time, not just
    a description note.

    Also REQUIRES goal to be defeat_malak or reach_leviathan -- true_balance
    and max_level don't require ever reaching the Leviathan or later, so a
    player could legitimately "win" without needing (or ever finding) the
    Star Maps this option gates -- confirmed live: a real seed left 2 of 4
    Star Maps permanently unfound with no narrative pull to go get them.
    Enabling progression_system with an incompatible goal raises an error
    at generation time, same as the area_randomizer check above."""
    display_name = "Progression System"
    default = False


class Traps(Choice):
    """Whether "Trap" items exist in the pool, and how many.

    off (default): no trap items exist, vanilla filler distribution
    unaffected.

    item_filler: trap items are folded into the normal proportional
    item_distribution_type draw as their own weighted category (see
    trap_weight, same shape as weapon_weight/armor_weight/etc.) -- the
    NUMBER of traps in the pool scales with total item count and weight
    like every other category, and the same trap type can appear more
    than once. Under "normal" distribution the baseline trap weight is 5
    (same "shows up occasionally" tier as Skills/Abilities).

    fixed_amount: exactly 12 trap items (one of each type below) are
    guaranteed in the pool, unconditionally, regardless of
    item_distribution_type. This is the original EnableTraps=true
    behavior; a YAML still saying `enable_traps: true` maps here, and
    `false` maps to off.

    A trap item does something purely punishing to whichever character
    receives it (the PC only -- companions are never affected, except as
    the TARGET of the "remove a companion" trap below), and never repeats
    itself: once delivered, that's it, no re-triggering on a later
    reconnect or area transition.

    The 12 traps: Remove All Credits, Reduce a Skill (one randomly-picked
    known skill, halved), Remove Half Known Feats, Remove Half Known Force
    Powers, Cut Max Health (as close to half as the character's build
    allows -- see below), Remove a Companion (a random currently-recruited
    one; does nothing if none are recruited yet), Remove Half Inventory
    Items (backpack only, equipped gear is safe, quest items are never
    eligible), and one dedicated item per remaining ability score
    (Strength/Dexterity/Intelligence/Wisdom/Charisma) that halves that
    specific score -- Constitution has no standalone item since Cut Max
    Health in Half already works by reducing it (the only lever this
    engine has for Max HP at all), so a separate CON trap would just
    overlap.

    "Cut Level (and XP) in Half" was retired: the engine's SetXP silently
    refuses to reduce XP below whatever the character's CURRENT level
    already requires (same no-op class as TakeGoldFromCreature), leaving
    the level field dropped but the XP unchanged -- an inconsistent
    character. Replaced by Reduce a Skill, which reuses the same
    EffectSkillDecrease approach already proven live for the 5 ability
    traps above (a plain vanilla effect, no threshold to fight).

    Several are decided at the moment of delivery, not at generation
    time, since they depend on the character's real current state: which
    half of their feats/force powers/inventory gets picked, which
    companion (if any) gets removed, what "half" actually means for their
    current level/HP/stat. If a character has 0 or 1 of something a trap
    would normally halve (feats, force powers, inventory items), that
    trap is a safe no-op rather than forcing a removal.

    Max HP has no direct in-memory field in this engine -- it's always
    computed from class levels + a Constitution bonus term. The trap
    reduces Constitution as far as needed to get AS CLOSE to half Max HP
    as achievable; for some high-level/high-hit-die characters, exactly
    half may not be reachable through Constitution alone, so the actual
    reduction can fall short of a true 50% cut."""
    display_name = "Traps"
    option_off = 0
    option_item_filler = 1
    option_fixed_amount = 2
    alias_false = 0
    alias_true = 2
    default = 0


class TrapWeight(Range):
    """Relative weight for Trap items in the distributed pool. Only
    consulted when item_distribution_type is player_decided AND traps
    is item_filler (the fixed_amount mode ignores weights entirely; off
    has no trap items at all). Kept low by default -- same "show up
    occasionally" tier as Skills/Abilities."""
    display_name = "Trap Distribution Weight"
    range_start = 0
    range_end = 100
    default = 5


class TrapLink(Toggle):
    """DeathLink's shape, for Traps. When on, every time a trap resolves
    against you (a real received Trap item, not an admin /ap_apply test),
    every other TrapLink-enabled player in the multiworld gets a trap too
    -- and when any of THEM triggers one, you do. Unlike DeathLink this
    is NOT a mirrored event: each recipient rolls their OWN random trap
    type locally from the 12 above, so two linked KotOR players hit by
    the same trigger usually get two different traps, and a linked
    non-KotOR game's trap is just "a trap" as far as this side cares.

    Linked traps resolve the same way a received Trap item does (next
    poll cycle, from your live character state, safe no-op if there's
    nothing to halve). They are never sent back out again, so a linked
    trap can't ping-pong between two players forever.

    If traps is off for you, an incoming linked trap is ignored (no
    trap types are enabled for this slot) -- matching DeathLink's own
    "nothing to do" precedent rather than inventing a fallback."""
    display_name = "TrapLink"
    default = False


class GalacticShop(Toggle):
    """Cross-multiworld item trading ("Void Trade"), built on Archipelago's
    shared Data Storage. When on, one crate in the Ebon Hawk's cargo hold
    (renamed "Galactic Shop") becomes the trade box: put any item in it
    and it vanishes into a pool shared by EVERY KotOR player in this
    multiworld, and you get a Galactic Coin back. Put a Galactic Coin in
    and you get a random item that some OTHER KotOR player deposited
    (never one of your own -- the whole point is that you can't dump junk
    and immediately reclaim it). If nobody else has anything in the pool
    right now, you get a Medpac instead of nothing.

    What comes back is delivered exactly like any other AP item grant --
    on your next area transition, not instantly -- because the pool
    lookup is a real network round trip. Requires the KOTOR Client to be
    connected to the AP server at the moment you use the box; a deposit or
    coin used while offline is remembered locally and settled the next
    time the client connects.

    Off (default): the cargo-hold crates stay ordinary containers."""
    display_name = "Galactic Shop"
    default = False


class AdditionalEnemies(Choice):
    """Adds brand-new hostile creatures alongside whatever's already
    placed in an area -- existing enemies/scripts/encounters are never
    touched or removed, this only adds more. Locations are fixed per
    module (precomputed, safety-checked spots -- see
    extender/area_trampolines/_enemy_spawn_points.json), only WHICH
    creature goes in each slot is decided per seed.

    off (default): vanilla, no additions.

    area_appropriate: each new creature is drawn only from OTHER
    creatures native to that area's own planet, matched to roughly that
    area's own existing difficulty range -- e.g. Endar Spire would only
    ever get more Sith troopers/soldiers, never something from a
    completely different planet.

    random_sane: any creature from the safe pool (any planet), but still
    matched to roughly that specific area's own existing CR (challenge
    rating) range -- more variety than area_appropriate, but still
    difficulty-consistent with where you actually are.

    fully_random: any creature from the safe pool, no planet or
    difficulty restriction at all -- can be significantly
    over/under-tuned for wherever it lands (e.g. a CR 14 creature dropped
    into an opening-hours area can kill a low-level character fast).
    Most variety, least predictable difficulty.
    """
    display_name = "Additional Enemies"
    option_off = 0
    option_area_appropriate = 1
    option_random_sane = 2
    option_fully_random = 3
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
    trying to "restore" money you just spent. Credits can be set to an
    exact value in either direction (not just topped up -- see
    KSE_SetCredits), which is what makes this clamp-down design possible
    at all; the old GiveGoldToCreature/TakeGoldFromCreature mechanism
    could only ever increase credits.

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
    of something you can only wear/wield one of at a time.

    Only affects AP item grants (a consumable arriving through the
    multiworld). Has no effect on shop stock (shop_item_count) or
    found/looted consumables (loot_mode) -- those are separate mechanisms
    and always grant/stock exactly the item's own real vanilla quantity."""
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
    somewhere other than their vanilla destination, using Archipelago's own
    entrance randomization engine. Most doors (110 of 156, the ones with a
    real, identifiable door leading back) are genuinely COUPLED: whatever
    room a shuffled door leads you into, you can always walk straight back
    out through the same physical door. A small number of doors (8, none
    of which have any real return door in the vanilla game at all -- an
    elevator, a dive suit sequence, or similar) always keep their normal
    vanilla destination, as do a handful of story-critical zones (Endar
    Spire, the Leviathan, the Star Forge, Unknown World) that are excluded
    from shuffling entirely. On the rare seed where the shuffle can't fully
    resolve on its own, a small repair step guarantees every area still has
    a real way in, at the cost of that one connection not necessarily
    leading back the way you came. The mapping is fixed once per seed:
    every door leads to the same shuffled destination for the whole
    playthrough. Off means every door/trigger keeps its normal vanilla
    destination. Like item suppression, this is a real, game-file-level
    patch applied once by a standalone script (not something the live AP
    client toggles), so this option's actual effect depends on that patch
    step having been run for the seed you're playing."""
    display_name = "Area Randomizer"
    default = False


class LootMode(Choice):
    """What happens to a picked-up item NOT on the AP-allowed whitelist
    (quest_dependent items are always left alone regardless of this
    option -- see scripts/patch_loot_disturb.py). Replaces the earlier
    two-toggle randomize_loot/allow_normal_loot design (2 booleans
    producing 4 behaviors was more confusing than one 4-way choice for the
    same thing) -- same 4 behaviors, one option:

      normal (default): untouched -- pure vanilla, nothing wired up at all.
      destroy: the pickup is destroyed immediately, no replacement.
      bonus: the pickup is kept as normal, and every loot-bearing
        placeable/creature also gets one extra random item (drawn from
        the shop_randomize pool) baked directly into its item list.
      replace: every non-whitelisted item is replaced with one random
        item from the same pool, one-for-one.

    Two earlier designs were tried and abandoned: KOTOR's
    Mod_OnAcquirItem module event (scripts/patch_item_suppression.py),
    which re-fires for items the player already holds -- a confirmed,
    unfixable engine quirk that forced held-quantity-delta guards and a
    purchase-detection heuristic just to work around it (do not
    reintroduce this mechanism for any reason); and its replacement,
    OnInvDisturbed/ScriptDisturbed, which never fires at all for creature
    corpse loot -- fatal since most of this game's loot comes from
    killing enemies, not static containers. See DEVELOPMENT_HISTORY.md's
    "Loot Mode's final settled design" section for the full history.

    CURRENT design: pure static template editing. scripts/patch_loot_
    disturb.py directly rewrites each loot-bearing placeable/creature's
    item list in Override before the game loads -- the same technique
    already used for the Galactic Coin item injection and Additional
    Enemies' bounty-card creature clones. No script hook of any kind, so
    none of the earlier designs' problems apply: no relaunch requirement
    (this is static data, applied the moment a module next loads, even on
    a reload of an already-running game), and creature corpse loot works
    identically to placeable container loot since both are just template
    data edited the same way. See scripts/patch_loot_disturb.py for
    implementation detail.

    This is a real, game-file-level patch applied once by
    scripts/patch_loot_disturb.py (not something the AP client toggles
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
    Skills 5 / Abilities 5 / Traps 5) -- a sensible mix that doesn't need
    any tuning. (Traps only participate at all when traps is
    item_filler.)

    player_decided: uses the 8 weight options below instead of the fixed
    baseline. Weights are relative, not required to sum to 100 -- doubling
    every weight produces the same distribution. A category that isn't
    actually available given your other options (e.g. EXP when
    experience_mode is off, or ap_limited XP mode which doesn't use
    items at all, or Weapons/Armor/Consumables when receive_inventory_items
    is off) is skipped and the remaining weights are renormalized
    automatically.

    randomized: same as player_decided, but the 8 weights are generated
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
    item_distribution_type is player_decided.

    Only affects how many consumable AP item GRANTS end up in the pool --
    not shop stock (shop_item_count) or found/looted consumables
    (loot_mode), which are separate mechanisms with their own controls."""
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

    reach_leviathan: the game is won the moment you're captured aboard the
    Leviathan -- detected via the same "Leviathan: Captured by the
    Leviathan" journal check (lev_captured >= 99) already tracked as a
    real location. A shorter alternative to defeat_malak that still
    requires completing the same core story beats (under
    progression_system, reaching the Leviathan already requires all 4 Star
    Maps -- see ProgressionSystem's own docstring) without the long
    Star Forge/Unknown World endgame after it. The only other goal
    progression_system can be combined with.
    """
    display_name = "Goal"
    option_defeat_malak = 0
    option_true_balance = 1
    option_max_level = 2
    option_reach_leviathan = 3
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
    new_companion: NewCompanion
    starting_class: StartingClass
    jedi_class: JediClass
    companion_class: CompanionClass
    additional_feats: AdditionalFeats
    progression_system: ProgressionSystem
    # Field name kept as enable_traps (not renamed to `traps`) so every
    # tester YAML written against the old Toggle keeps working -- the
    # true/false aliases on Traps map onto fixed_amount/off.
    enable_traps: Traps
    trap_link: TrapLink
    galactic_shop: GalacticShop
    additional_enemies: AdditionalEnemies
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
    trap_weight: TrapWeight
    goal: Goal
