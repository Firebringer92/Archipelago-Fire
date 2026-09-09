from BaseClasses import MultiWorld
from worlds.generic.Rules import set_rule, add_rule

from .Options import Goal
from .Locations import location_table

# 2026-09-08: Progression System's real access-rule layer. Every gate here
# is confirmed via the game's OWN compiled scripts (raw byte search across
# every .ncs in the game for each item's tag, cross-checked against the
# real dialogue/area data), not guessed from memory -- see
# FutureDesign.md's 2026-09-08 Progression System entries for the full
# derivation of each one, including the 2 real corrections found along
# the way (the Sith Base keycard turned out to be a redundant alternate
# path already covered by the armor+papers gate, not a separate item; the
# Davik's estate computer pass is used on an internal terminal, not the
# estate's own entry, so it's not a real progression gate either -- both
# were dropped from the original 12-item candidate list for exactly this
# reason).
#
# 2026-09-08 UPDATE: two more items dropped after tracing each candidate's
# REAL checkpoint script (not just its pickup script), not merely its
# vanilla acquisition location -- Tatooine Desert Map because literally
# nothing in the entire game (chitin + Override, every resource type)
# ever checks whether the player possesses it, and Dantooine's Star Map
# because it turned out not to be part of the same completion gate as the
# other 4 (see below) and isn't a travel barrier either. Also added this
# session: an ARTIFICIAL travel gate for the 4 remaining Star Map planets
# (Tatooine/Kashyyyk/Manaan/Korriban), since the vanilla game turned out
# to have NO such gate at all -- k_sup_galaxymap (the galaxy map script)
# contains zero availability checks; every planet is selectable from the
# start. Progression System creates this lock itself via a
# k_sup_galaxymap wrapper (blocks travel) plus a k_pla_actmap wrapper
# (blocks the underlying completion flag as a safety net) -- see
# scripts/patch_item_suppression.py. AP's own placement logic needs to
# know about this artificial lock too, so it doesn't strand a required
# item behind a location that's genuinely unreachable until that planet's
# Star Map check arrives.

# Everywhere the Sith disguise checkpoint gates -- confirmed via
# ptar_sitharmor/ptar_sithpapers being checked together across ~30
# scripts in modules m02ad/m02ae (Taris' Sith Military Base and its own
# checkpoint). Sith Armor ALONE clears the general Lower City checkpoint;
# Sith Base itself additionally checks for the papers.
TARIS_ARMOR_ONLY_LOCATIONS = [
    "Visited: Taris - Lower City",
    "Visited: Taris - Lower City Apartments (tar_m03ab)",
    "Visited: Taris - Lower City Apartments (tar_m03ad)",
    "Visited: Taris - Javyar's Cantina",
    "Visited: Taris - Swoop Platform",
    "Visited: Taris - Undercity",
    "Visited: Taris - Lower Sewers",
    "Visited: Taris - Upper Sewers",
    "Visited: Taris - Davik's Estate",
    "Visited: Taris - Black Vulkar Base (tar_m10aa)",
    "Visited: Taris - Black Vulkar Base (tar_m10ab)",
    "Visited: Taris - Black Vulkar Base (tar_m10ac)",
    "Visited: Taris - Hidden Bek Base (tar_m11aa)",
    "Visited: Taris - Hidden Bek Base (tar_m11ab)",
]
TARIS_ARMOR_AND_PAPERS_LOCATIONS = [
    "Visited: Taris - Sith Base",
]

# Confirmed via tar09_acquire/k_ptar_candcode -- the codes needed to
# launch off Taris without being shot down by the Sith's own orbital
# cannons. Only "Escaping Taris" itself needs this; nothing else on
# Taris depends on it.
TARIS_SHIELD_CODES_LOCATIONS = [
    "Taris: Escaping Taris",
]

# Confirmed via k_pman_airlock01/k_pman_suituse -- the Hrakert Station
# airlock leading to the underwater trench walk to Manaan's own Star Map.
# Includes the Star Map check ITSELF, not just what it leads to
# afterward -- the physical Star Map sits past this airlock, so that
# check is not really reachable without the suit either.
MANAAN_ENVIRO_SUIT_LOCATIONS = [
    "Visited: Manaan - Sea Floor",
    "Visited: Manaan - Kolto Control",
    "Visited: Manaan - Hrakert Rift",
    "Manaan: Star Map: Manaan",
]

# The 4 Star Maps that actually gate the Leviathan-capture endgame --
# confirmed directly from k_pla_actmap's own disassembly: it tracks
# exactly K_STAR_MAP_MANAAN/KASHYYYK/KORRIBAN/TATOOINE and recomputes
# K_CAPTURED_LEV from those 4 booleans alone. Dantooine's own Star Map
# (DAN_STARMAP_DONE) is a completely separate global, read by neither
# k_pla_actmap nor the Leviathan-capture check -- it was dropped from the
# Progression System item list entirely (2026-09-08) since it's neither
# a travel barrier nor part of this completion gate.
ALL_STAR_MAPS = [
    "Progression Item: Star Map (Tatooine)", "Progression Item: Star Map (Kashyyyk)",
    "Progression Item: Star Map (Manaan)", "Progression Item: Star Map (Korriban)",
]
STAR_FORGE_ENDGAME_LOCATIONS = [
    "Leviathan: Captured by the Leviathan",
    "Visited: Leviathan - Prison Block", "Visited: Leviathan - Command Deck",
    "Visited: Leviathan - Hangar", "Visited: Leviathan - Bridge",
    "Unknown World: Invisible Mandalorians", "Unknown World: Rakatan Research",
    "Unknown World: Trapped on a Nameless World",
    "Visited: Unknown World - Central Beach", "Visited: Unknown World - South Beach",
    "Visited: Unknown World - North Beach", "Visited: Unknown World - Temple Exterior",
    "Visited: Unknown World - Elder Settlement", "Visited: Unknown World - Rakatan Settlement",
    "Visited: Unknown World - Temple Main Floor", "Visited: Unknown World - Temple Summit",
    "Star Forge: A Quest for the Star Forge",
    "Visited: Star Forge - Deck 1", "Visited: Star Forge - Command Center",
    "Visited: Star Forge - Viewing Platform",
    "Malak Defeated",
]

# --- Artificial travel-gate location set (2026-09-08) ---
#
# Every location whose `region` in Locations.py IS one of these 4 planet
# names is trivially in-scope. That alone misses real checks physically
# on these planets but categorized under a cross-planet region instead
# (Locations.py's own "Exploration"/"Genoharadan"/"Companions" buckets),
# so those are covered separately below, each confirmed via real game
# data (not guessed): "Exploration" entries cross-referenced against
# extender/area_trampolines/_mapping.json's module->area_idx table;
# "Companions"/"Genoharadan" entries confirmed via direct GIT/journal-tag
# tracing of where each one's real module placement/completion sits.
PLANET_STARMAP_ITEM = {
    "Tatooine": "Progression Item: Star Map (Tatooine)",
    "Kashyyyk": "Progression Item: Star Map (Kashyyyk)",
    "Manaan": "Progression Item: Star Map (Manaan)",
    "Korriban": "Progression Item: Star Map (Korriban)",
}

# area_idx values (Locations.py's "Exploration" region) physically on each
# gated planet, per extender/area_trampolines/_mapping.json's module
# prefix (kas_/korr_/man/tat_). Baked as a static set here, same as
# Locations.py's own table is generated once rather than re-derived live.
PLANET_AREA_IDX = {
    "Kashyyyk": {11, 12, 13, 14, 15},
    "Korriban": {16, 17, 18, 19, 20, 21, 22, 23},
    "Manaan": {29, 30, 31, 32, 33, 34, 35, 36, 37, 38},
    "Tatooine": {62, 63, 64, 65, 66, 67, 68, 69},
}

# Companion recruits and Genoharadan bounty targets confirmed (2026-09-08,
# via real GIT Creature List / journal-tag tracing, not guessed) to
# physically sit on one of the 4 gated planets despite their `region`
# being "Companions"/"Genoharadan" rather than a planet name. Every OTHER
# companion's real recruit point traced back to Endar Spire/Taris/
# Dantooine (none of which are gated), so only these 2 needed adding.
COMPANION_PLANET_OVERRIDE = {
    "Companion Recruited: HK-47": "Tatooine",        # tat_m17ac (tat17_08hk47_01)
    "Companion Recruited: Jolee Bindo": "Kashyyyk",  # kas_m24aa (p_jolee001)
}

# Genoharadan bounty targets: each target's own journal-advancing script
# was traced to its module directly (not the shared Manaan broker/Ebon
# Hawk tracker scripts every target's tag is ALSO referenced from, which
# don't indicate where the actual confrontation happens). Zuulan's real
# module is Dantooine (not gated, no entry needed here). Lorgal's own
# module couldn't be pinned this way -- only the shared broker script
# references him -- so Korriban is an inference by elimination against
# the other 4 confirmed targets, lower confidence than the rest; revisit
# if this turns out wrong. The overall questline-completion location
# ("Genoharadan", journal_target=102) references advancing scripts on 3
# different gated planets at once (likely a branching final confrontation
# depending on player path) and can't be pinned to one -- conservatively
# gated behind ALL 4 Star Maps below instead of a single planet.
GENOHARADAN_PLANET_OVERRIDE = {
    "Genoharadan: Ithorak": "Manaan",     # manm26ad
    "Genoharadan: Rulan": "Kashyyyk",     # kas_m24aa
    "Genoharadan: Vorn": "Tatooine",      # tat_m18ab
    "Genoharadan: Lorgal": "Korriban",    # inferred, not directly confirmed
}
GENOHARADAN_FINALE_LOCATION = "Genoharadan"


def set_rules(multiworld: MultiWorld, player: int) -> None:
    world = multiworld.worlds[player]
    if not world.options.progression_system:
        # Deliberately no access rules -- all locations open from the
        # start, same flat model as before this option existed.
        return

    for name in TARIS_ARMOR_ONLY_LOCATIONS:
        set_rule(multiworld.get_location(name, player),
                  lambda state: state.has("Progression Item: Sith Armor", player))
    for name in TARIS_ARMOR_AND_PAPERS_LOCATIONS:
        set_rule(multiworld.get_location(name, player),
                  lambda state: (state.has("Progression Item: Sith Armor", player)
                                  and state.has("Progression Item: Sith Papers", player)))
    for name in TARIS_SHIELD_CODES_LOCATIONS:
        set_rule(multiworld.get_location(name, player),
                  lambda state: state.has("Progression Item: Taris Shield Codes", player))
    for name in MANAAN_ENVIRO_SUIT_LOCATIONS:
        set_rule(multiworld.get_location(name, player),
                  lambda state: state.has("Progression Item: Manaan Enviro Suit", player))
    for name in STAR_FORGE_ENDGAME_LOCATIONS:
        set_rule(multiworld.get_location(name, player),
                  lambda state: state.has_all(set(ALL_STAR_MAPS), player))

    # Artificial travel gate: layered on with add_rule (AND-combine), not
    # set_rule, since some of these locations (e.g. Manaan's Sea Floor/
    # Kolto Control/Hrakert Rift/Star Map, above) already got an
    # item-specific rule and both need to hold at once.
    for name, data in location_table.items():
        planet = None
        if data.region in PLANET_STARMAP_ITEM:
            planet = data.region
        elif data.region == "Exploration":
            for p, idxs in PLANET_AREA_IDX.items():
                if data.area_idx in idxs:
                    planet = p
                    break
        elif data.region == "Companions":
            planet = COMPANION_PLANET_OVERRIDE.get(name)
        elif data.region == "Genoharadan":
            planet = GENOHARADAN_PLANET_OVERRIDE.get(name)
        if planet is not None:
            item_name = PLANET_STARMAP_ITEM[planet]
            add_rule(multiworld.get_location(name, player),
                      lambda state, item_name=item_name: state.has(item_name, player))

    add_rule(multiworld.get_location(GENOHARADAN_FINALE_LOCATION, player),
              lambda state: state.has_all(set(PLANET_STARMAP_ITEM.values()), player))


def set_completion_rules(multiworld: MultiWorld, player: int) -> None:
    # 2026-08-29: was a no-op -- AP's own test suite (test_implemented.py's
    # test_completion_condition) correctly flagged this as a bug, not a
    # stylistic choice: AP's default completion_condition is trivially True
    # against an EMPTY CollectionState, and with set_rules() leaving every
    # location wide open (no access requirements above), can_reach_location
    # is equally trivial here -- there was no way to make a REACHABILITY-
    # based condition meaningful in this flat world without contradicting
    # that honest design. Fixed by giving each goal's relevant location(s)
    # a locked, real-item marker (see __init__.py's create_regions()/
    # GOAL_EVENT_LOCATIONS and Items.py's own comment on why these are real
    # items with real codes, not code=None Events) and checking state.has()
    # on those instead of reachability -- the standard AP idiom for a goal
    # signal in an otherwise open world.
    #
    # true_balance's real, live, in-game "have you won" signal
    # (kotor_location_tracker.py's true_balance_reached(), used by
    # KotorContext._check_goal in KotorClient.py) is EVER reaching BOTH
    # alignment extremes at ANY point in the same playthrough, using the
    # wider 80-100/0-20 bands, not simultaneously and not just the literal
    # endpoints. AP's completion_condition here is a deliberate
    # SIMPLIFICATION of that, not a claim of exact equivalence: it checks
    # only the two literal endpoint locations ("Alignment: Dark Side 0"/
    # "Alignment: Light Side 100"), not the full bands, and -- like
    # defeat_malak/max_level above -- checks "do you have the marker" (a
    # fixed point in a fully-collected state), not "did you ever hold both
    # at once during a specific playthrough's history," which
    # CollectionState has no way to represent at all. Close enough for AP's
    # own generation-time reachability/beatability checks; the client's own
    # live tracking is still what actually ends a real playthrough.
    world = multiworld.worlds[player]
    goal = world.options.goal.value
    if goal == Goal.option_defeat_malak:
        multiworld.completion_condition[player] = lambda state: state.has("Malak Defeated", player)
    elif goal == Goal.option_max_level:
        multiworld.completion_condition[player] = lambda state: state.has("Reached Level 20", player)
    elif goal == Goal.option_true_balance:
        multiworld.completion_condition[player] = lambda state: (
            state.has("Reached Dark Side 0", player) and state.has("Reached Light Side 100", player))
