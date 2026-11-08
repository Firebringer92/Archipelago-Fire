"""Options of the KOTOR 2 world (first draft). Defaults are for the first playthrough: story gates on, every randomiser off.

Options whose game side is not built yet say so in their text; they are recorded in the seed so the client and game can use them later.
"""
import typing
from dataclasses import dataclass

from Options import Choice, DeathLink, DefaultOnToggle, OptionSet, PerGameCommonOptions, Range, Toggle

from .Items import EXTRA_COMPANION_NAMES, TRAP_TYPE_KEYS


class Goal(Choice):
    """What ends the run.
    defeat_kreia: finish the game (Kreia is defeated and the ending plays).
    defeat_nihilus: defeat Darth Nihilus on the Ravager; a shorter run that ends before Malachor.
    high_level: reach the level set by goal_level.
    influence_crew: reach the high (75 or more) or low (25 or less) end of influence with influence_goal_count companions (needs companions).
    cult_leader: recruit every companion your seed offers (every recruit check, and every companion item in ap_gated); needs companions.
    Game side: only defeat_kreia is detected in the game today; the others are built in the world and the client."""
    display_name = "Goal"
    option_defeat_kreia = 0
    option_defeat_nihilus = 1
    option_high_level = 2
    option_influence_crew = 3
    option_cult_leader = 4
    default = 0


class GoalLevel(Range):
    """The level to reach when goal is high_level. The story alone gives roughly level 20 to 25 (level 20 = 190,000 XP, level 25 = 300,000 XP), so the
    experience options must be able to supply this level; the generator checks that."""
    display_name = "Goal Level"
    range_start = 10
    range_end = 50
    default = 25


class InfluenceGoalCount(Range):
    """How many companions must reach the high or low end of influence when goal is influence_crew."""
    display_name = "Influence Goal Count"
    range_start = 1
    range_end = 12
    default = 6


class LevelTarget(Range):
    """The highest level that gets a level check (a location, not a goal). The game's maximum is 50; story content gives roughly level 20 to 25, so higher
    targets need experience supplied by the experience options."""
    display_name = "Level Target"
    range_start = 5
    range_end = 50
    default = 20


class ShortenedPeragus(Toggle):
    """Condense the Peragus opening ("short hallway"): Atton is freed at once, the T3-M4 trip, the mining tunnels, the outside walk and the dormitories are cut, the
    Sith arrive by a docking movie, and the Harbinger's locked doors and the hangar door are opened for you. Kept: Kreia, the HK-50 scene, Atton and T3-M4
    joining, the Sion duel, the turret scene and the first Hawk visit. The checks that only exist in the cut parts (Mining Tunnels, Asteroid Exterior and
    Dormitories visits, Rescue, Turbolift Lockdown and Voiceprint Protocol quests) leave the seed. The seed carries the plan; the game side is not built yet, so
    nothing happens in the game."""
    display_name = "Shortened Peragus"


class StoryGates(DefaultOnToggle):
    """Hold the story beats listed in the gates table until enough progression items of the right family are owned."""
    display_name = "Story Gates"


class DisabledGates(OptionSet):
    """Gate ids to switch off for this seed (for example NAR1, DXN2). A disabled gate needs no tokens and is not enforced in the game."""
    display_name = "Disabled Gates"
    valid_keys = frozenset({"TEL1", "TEL2", "TEL3", "NAR1", "NAR2", "NAR3", "DXN1", "DXN2", "DXN3", "DAN1", "DAN2", "DAN3",
                            "KOR1", "KOR2", "KOR3", "FIN1", "FIN2", "FIN3", "FIN4"})
    default = frozenset()


class Companions(Choice):
    """How companions work in this version. A companion that is unlocked can be chosen for the active party; the others stay out of the party selection
    (they can still be met on the Ebon Hawk).
    default: story joins stay as in the base game; recruit and influence checks are used.
    ap_gated: companions arrive as items from the multiworld and become selectable for the party when received.
    ap_limited: no companion items; the next companion unlocks after each companion_unlock_step percent of your own completed checks (the twelve
    base companions first, then the extra ones).
    none: no companions; no recruit or influence checks."""
    display_name = "Companions"
    option_none = 0
    option_default = 1
    option_ap_gated = 2
    option_ap_limited = 3
    alias_vanilla = 1
    alias_ap_items = 2
    default = 1


class CompanionUnlockStep(Range):
    """With companions ap_limited: the percent of your own checks that unlocks each further companion. Base companions come first, then the extra
    ones; at 5 percent the twelve base companions are all out at 60 percent and four extras by 80 percent."""
    display_name = "Companion Unlock Step"
    range_start = 1
    range_end = 20
    default = 5


class ExtraCompanions(OptionSet):
    """Extra companions on the new party slots (12 to 31), in the modes ap_gated and ap_limited. They have no recruit or influence checks, no conversation and are
    never required. Each is a generic companion body with the character's name, class and look (the look is a disguise; the KotOR 1 characters need your own KotOR 1 install for
    their real look and portrait, else they get a generic look and a portrait of the same sex). Built, but not yet tried in the game."""
    display_name = "Extra Companions"
    valid_keys = frozenset(EXTRA_COMPANION_NAMES)
    default = frozenset()


class ApCompanions(Range):
    """How many generated companions (a different race and look each, named after players of this multiworld) are offered as items in the modes ap_gated and
    ap_limited. The looks are Twi'lek, Devaronian, human and alien (Rodian, Duros, Sullustan, Trandoshan, Quarren, Gran, Bith) characters, never a story companion's look;
    armour shows on the first three kinds only, gear can be equipped on all. Built, but not yet tried in the game."""
    display_name = "AP Companions"
    range_start = 0
    range_end = 8
    default = 0


class CompanionClass(Choice):
    """How companion classes are handled. The seed decides each companion's class (the three droids are never changed); the game applies it when the companion
    arrives, which waits for the companion work, so nothing happens in the game yet.
    default: untouched. jedi_companion: every non-Jedi companion becomes a base Jedi class when they arrive. no_jedi: Jedi companions become non-Jedi.
    droid: every companion who is not a droid becomes a Combat or Expert Droid: class and race droid, and the droid look through a changed copy of their own creature
    template (a companion who already joined in an old save keeps the look the save stored). randomize_base: each companion gets a random base class (never a prestige class)."""
    display_name = "Companion Class"
    option_default = 0
    option_jedi_companion = 1
    option_no_jedi = 2
    option_droid = 3
    option_randomize_base = 4
    default = 0


class MulticlassCompanion(Choice):
    """A second class for companions. random_class is decided by the seed (the game applies it, which waits for the companion work); prestige is not built.
    off: none. prestige: an item upgrades a companion to a Jedi prestige class. random_class: a random second class once the companion is level 15."""
    display_name = "Multiclass Companion"
    option_off = 0
    option_prestige = 1
    option_random_class = 2
    default = 0


class StartingClass(Choice):
    """How your character's class is handled. All values are built; none has been tried in the game yet.
    default: as chosen in character creation. non_force_user: your class is swapped for Soldier, Scout or Scoundrel, with the Jedi content removed.
    random_class: a random base class (Soldier, Scout, Scoundrel, Jedi Guardian, Consular or Sentinel). prestige_start: you begin as a random prestige class.
    prestige_gated: a "Prestige Class" item is in the pool; when it arrives you gain a light or dark prestige class of one pair chosen by the seed (Vanguard /
    Marauder, Shadow / Assassin, Sage / Sorcerer), the side following your alignment (a random side when exactly neutral).
    droid: you start as a Combat or Expert Droid and your race is droid (no Force); your appearance is not changed."""
    display_name = "Starting Class"
    option_default = 0
    option_non_force_user = 1
    option_random_class = 2
    option_prestige_start = 3
    option_prestige_gated = 4
    option_droid = 5
    default = 0


STARTING_ABILITIES = ["Strength", "Dexterity", "Constitution", "Intelligence", "Wisdom", "Charisma"]
STARTING_SKILLS = ["Computer Use", "Demolitions", "Stealth", "Awareness", "Persuade", "Repair", "Security", "Treat Injury"]


class StartingStats(Choice):
    """Your abilities and skills at the start of the run.
    default: as character creation made them.
    randomized: each of the six abilities and each of the eight skills is set to a random value from 1 to 20 (decided by the seed, set once when the game starts;
    the level-up screen and the ability and skill items build on those values)."""
    display_name = "Starting Stats"
    option_default = 0
    option_randomized = 1
    default = 0


class ExperienceMode(Choice):
    """How AP-driven experience reaches you.
    off: untouched; no experience items.
    ap_limited: no items; each completed check of yours grants experience_limiter XP.
    ap_gated: "Experience Points" items in the pool, each worth experience_item XP.
    In both ap modes the client keeps your XP at the total the seed entitles: XP from kills and quests is brought back to it at each area change."""
    display_name = "EXP Mode"
    option_off = 0
    option_ap_limited = 1
    option_ap_gated = 2
    default = 0


class ExperienceLimiter(Range):
    """XP granted per completed check of yours when experience_mode is ap_limited."""
    display_name = "EXP Limiter"
    range_start = 500
    range_end = 20000
    default = 1000


class ExperienceItem(Range):
    """XP each "Experience Points" item grants when experience_mode is ap_gated."""
    display_name = "EXP Item"
    range_start = 500
    range_end = 20000
    default = 8000


class CreditMode(Choice):
    """How AP-driven credits reach you; the same three modes as experience_mode (off, ap_limited, ap_gated)."""
    display_name = "Credit Mode"
    option_off = 0
    option_ap_limited = 1
    option_ap_gated = 2
    default = 0


class CreditLimiter(Range):
    """Credits granted per completed check of yours when credit_mode is ap_limited."""
    display_name = "Credit Limiter"
    range_start = 1
    range_end = 20000
    default = 100


class CreditItem(Range):
    """Credits each "Republic Credits" item grants when credit_mode is ap_gated."""
    display_name = "Credit Item"
    range_start = 1
    range_end = 20000
    default = 5000


class AreaVisitChecks(DefaultOnToggle):
    """The first visit to each of 53 areas is a check."""
    display_name = "Area Visit Checks"


class AlignmentChecks(DefaultOnToggle):
    """16 checks for alignment thresholds, the same list as the KotOR 1 world. These never hold progression."""
    display_name = "Alignment Checks"


class QuestItemChecks(Toggle):
    """Holding a listed quest item for the first time is a check. Off by default: the list is a draft of 37 items taken from the game's data
    (docs/QUEST_ITEM_CANDIDATES.md) and is being replaced by a list built from play-through logs of main-story items.""" 
    display_name = "Quest Item Checks"


class Bazaar(DefaultOnToggle):
    """The Archipelago Bazaar: a Jawa trader in the cargo hold of the Ebon Hawk. 5 purchase checks, bought with credits (1,000 for the first, then 2,000 more for each), and
    20 token-exchange checks, bought with Bazaar tokens (5 each) that are hidden in containers as you explore (100 in all). These checks never hold progression items."""
    display_name = "Archipelago Bazaar"


class TrapPercentage(Range):
    """Percent of the filler items that are traps."""
    display_name = "Trap Percentage"
    range_start = 0
    range_end = 100
    default = 10


class TrapTypes(OptionSet):
    """Which traps may appear. lose_credits (a tenth of your credits), dark_side_push and light_side_push (10 alignment points), lose_influence (8 influence with
    one companion), reduce_skill (one known skill halved), cut_max_health (constitution lowered towards half your maximum health), remove_companion
    (a random companion in your party goes back to the Ebon Hawk), remove_half_inventory (half of the backpack that is not quest gear), halve_strength,
    halve_dexterity, halve_intelligence, halve_wisdom and halve_charisma (that score halved, never below 3). A trap with nothing to take does nothing."""
    display_name = "Trap Types"
    valid_keys = frozenset(TRAP_TYPE_KEYS)
    default = frozenset(TRAP_TYPE_KEYS)


class TrapLink(Toggle):
    """When a trap item hits you, every other TrapLink player gets a trap too, and the reverse. Each player rolls their own trap type from the ones listed in trap_types. A trap that arrives through the link is never sent on."""
    display_name = "TrapLink"


class KotorTwoDeathLink(DeathLink):
    """A death in the game sends a death to every DeathLink player, and the reverse. A death that came from the link is not sent on."""


class CraftingMode(Choice):
    """Crafting mode. In any mode other than off the workbench can build every ordinary piece of gear in the game (360 recipes: armor, robes, belts, gloves,
    masks, implants, droid parts, ranged and melee weapons, lightsabers), on top of the recipes it already has. The cost in Components comes from the item's value
    and the skill rank from the recipe; the console (an item you carry, opened from the inventory) opens the workbench with the seed's table.
    off: normal.
    simple: gear recipes ask for a rank that follows the item's value and cost their normal amount.
    complex: every rank 6 higher (the game's own recipes too, at most 32) and gear costs double.
    random_requirements: every rank random from 1 to 32 and every gear cost a random multiple (half to four times).
    Gear items in the pool (gear_items) and the Vendor's supply menu go with it. Not built yet in the game: loot turning into materials."""
    display_name = "Crafting Mode"
    option_off = 0
    option_simple = 1
    option_complex = 2
    option_random_requirements = 3
    default = 0


class LootMode(Choice):
    """What loot_randomizer does to the ordinary gear in containers and dropped by creatures (quest items, credits and the like are never touched).
    replace: each piece of gear becomes a random piece from the shop pool; a creature keeps and uses its own gear but drops the random piece instead.
    bonus: everything stays and every container that holds gear, and every creature that carries something, gets one more random piece.
    With a crafting mode, the same two words will decide whether materials replace the gear or come on top (the seed carries the flag; the game side is not built)."""
    display_name = "Loot Mode"
    option_replace = 0
    option_bonus = 1
    default = 0


class CraftingGated(Toggle):
    """Each crafting type is locked until its own item arrives: the five workbench tabs (armor and robes, ranged weapons, melee weapons, lightsabers, belts, gloves and
    other gear; only with a crafting_mode), the game's own upgrade parts and upgrade screen, and the chemical lab. Seven items go into the pool (two without a
    crafting_mode, which gate the game's own crafting). The recipes and console entries of a locked type are hidden; whether the game reads a rewritten recipe table
    while it runs, or only after a restart, is not yet known."""
    display_name = "Crafting Gated"


class AreaRandomizer(Toggle):
    """The doors and walk-through exits between the areas of Telos and the Citadel, Nar Shaddaa, Dxun, Onderon and Dantooine are re-linked in coupled pairs
    (walk back through the door you came by and you are where you were). Every area stays reachable from the landing of its planet. The opening (Peragus and the
    Harbinger), the Ebon Hawk, the Ravager, Korriban's duel and visions, Malachor and the minigames keep their doors, and so do travel by the galaxy map, the
    shuttles and the guides. The way to a place is part of the logic, so its checks need the tokens that the route needs. Applies when you connect."""
    display_name = "Area Randomizer"


class EnemyRandomizer(Toggle):
    """Adds new hostile creatures to the combat areas (27 of them, 311 fixed spots chosen to be walkable and clear of objects). Nothing that is already there is
    touched, removed or replaced; the extra creatures only come on top. Which creature stands at each spot is decided per seed by enemy_mode. Story set pieces
    (the yacht fight, Vash, the vision modules, Nihilus and the Malachor proving ground) get none. Applies when you connect, before the game loads the areas."""
    display_name = "Enemy Randomizer"


class EnemyMode(Choice):
    """How enemy_randomizer picks the creature for each spot.
    area_appropriate: the kind of creature that dominates the area (beasts, Sith soldiers, droids, ...), matched to that area's own difficulty.
    random_sane: any creature from the safe pool, still matched to that area's own difficulty.
    fully_random: any creature from the safe pool with no difficulty limit; a very strong creature can land in an early area."""
    display_name = "Enemy Mode"
    option_area_appropriate = 0
    option_random_sane = 1
    option_fully_random = 2
    default = 1


class GearItems(Range):
    """The share of the filler items that are pieces of gear (360 different ones: armor, robes, belts, gloves, masks, implants, droid parts, ranged and melee weapons,
    lightsabers; each named by its template name). With crafting_mode off a gear item is simply given. With a crafting_mode it unlocks that piece's workbench recipe
    (the recipe stays hidden until then) and gives Components worth about a tenth of the build cost. 0 puts none in the pool."""
    display_name = "Gear Items"
    range_start = 0
    range_end = 100
    default = 20


class ShopRandomizer(Toggle):
    """Every shop that is not a Pazaak dealer is restocked, one list per planet (K1 did the same). Each planet's list is shop_count items drawn at random for this
    seed, plus medpacs, droid repair kits and spikes so healing can always be bought. The Pazaak dealers and the game's own random stock scripts are left alone or
    silenced respectively. With crafting gated, shops will sell crafting supplies only (the seed carries the flag; the game side is not built)."""
    display_name = "Shop Randomizer"


class ShopCount(Range):
    """Items drawn for each planet's shops when shop_randomizer is on (the staples come on top). How many items a K2 store holds is not measured yet, so 60 is a guess."""
    display_name = "Shop Item Count"
    range_start = 1
    range_end = 60
    default = 30


class LootRandomizer(Toggle):
    """The gear lying in containers and dropped by creatures is changed as loot_mode says. Only fixed loot: the random treasure the game rolls when a container
    or creature first appears is left alone, and the opening module is skipped. Applies when you connect, before the game loads the areas."""
    display_name = "Loot Randomizer"


class ArchipelagoVendor(Toggle):
    """Puts the Archipelago Vendor on the Ebon Hawk, in the cargo hold next to the Bazaar's Jawa. Each of his menus is hidden until you find its pass item in the
    multiworld: Skill Training (1,000 credits a rank, 5 in all), Ability Training (4,000 credits a point, 5 in all), Alignment Change (10 points toward the dark side
    for 1,000 credits paid to you, or toward the light side for 5,000 credits; no limit, refused near the ends of the scale) and, with a crafting_mode, Crafting
    Supplies (bundles of Components or Chemicals for credits, no limit). The passes are useful items, never required, and take the place of ordinary filler.
    Not in it yet: feat and Force power training and the character respec of KotOR 1's vendor."""
    display_name = "Archipelago Vendor"


@dataclass
class KotorTwoOptions(PerGameCommonOptions):
    goal: Goal
    goal_level: GoalLevel
    influence_goal_count: InfluenceGoalCount
    level_target: LevelTarget
    death_link: KotorTwoDeathLink
    story_gates: StoryGates
    disabled_gates: DisabledGates
    shortened_peragus: ShortenedPeragus
    companions: Companions
    companion_unlock_step: CompanionUnlockStep
    extra_companions: ExtraCompanions
    ap_companions: ApCompanions
    companion_class: CompanionClass
    multiclass_companion: MulticlassCompanion
    starting_class: StartingClass
    starting_stats: StartingStats
    experience_mode: ExperienceMode
    experience_limiter: ExperienceLimiter
    experience_item: ExperienceItem
    credit_mode: CreditMode
    credit_limiter: CreditLimiter
    credit_item: CreditItem
    area_visit_checks: AreaVisitChecks
    alignment_checks: AlignmentChecks
    quest_item_checks: QuestItemChecks
    bazaar: Bazaar
    trap_percentage: TrapPercentage
    trap_types: TrapTypes
    trap_link: TrapLink
    crafting_mode: CraftingMode
    loot_mode: LootMode
    crafting_gated: CraftingGated
    area_randomizer: AreaRandomizer
    enemy_randomizer: EnemyRandomizer
    enemy_mode: EnemyMode
    gear_items: GearItems
    shop_randomizer: ShopRandomizer
    shop_count: ShopCount
    loot_randomizer: LootRandomizer
    archipelago_vendor: ArchipelagoVendor
