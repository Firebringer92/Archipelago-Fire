from BaseClasses import MultiWorld
from worlds.generic.Rules import set_rule, add_rule, add_item_rule

from .Options import Goal
from .Locations import COMPANION_SUBPLOT_LOCATIONS

# Progression System's real access-rule layer. Every gate here
# is confirmed via the game's OWN compiled scripts (raw byte search across
# every .ncs in the game for each item's tag, cross-checked against the
# real dialogue/area data), not guessed from memory. Two real
# corrections were found along
# the way (the Sith Base keycard turned out to be a redundant alternate
# path already covered by the armor+papers gate, not a separate item; the
# Davik's estate computer pass is used on an internal terminal, not the
# estate's own entry, so it's not a real progression gate either -- both
# were dropped from the original 12-item candidate list for exactly this
# reason). Two further items were dropped after tracing each candidate's
# REAL checkpoint script (not just its pickup script), not merely its
# vanilla acquisition location -- Tatooine Desert Map because literally
# nothing in the entire game (chitin + Override, every resource type)
# ever checks whether the player possesses it, and Dantooine's Star Map
# because it turned out not to be part of the same completion gate as the
# other 4 (see below) and isn't a travel barrier either. Also added: an
# ARTIFICIAL travel gate for the 4 remaining Star Map planets
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
# Progression System item list entirely since it's neither
# a travel barrier nor part of this completion gate.
ALL_STAR_MAPS = [
    "Progression Item: Star Map (Tatooine)", "Progression Item: Star Map (Kashyyyk)",
    "Progression Item: Star Map (Manaan)", "Progression Item: Star Map (Korriban)",
]
# FIXED (real bug): each planet's own "Star Map: X"
# location has region=X (the planet name) like every other quest/
# exploration check on that planet -- but the generic per-planet travel-
# gate loop below adds a rule requiring state.has(that SAME planet's Star
# Map item) to every location whose region matches, with no exception.
# Applied to the Star Map location itself, that's a hard self-lock: you'd
# need to already possess the exact item that location is meant to award
# before you could ever check it. Confirmed -- a real generation
# placed "Progression Item: Star Map (Manaan)" on a Manaan-region
# location, unreachable as a direct result of this bug. Excluded here so
# the loop's rule is skipped for these 4 specifically; every OTHER
# location on that planet still correctly requires the Star Map item
# (that part was never wrong -- AP's own reachability-based fill already
# guarantees the item itself can't be placed at any of those other
# locations either, since none of them are reachable without it).
PLANET_OWN_STARMAP_LOCATION = {
    "Kashyyyk: Star Map: Kashyyyk", "Korriban: Star Map: Korriban",
    "Manaan: Star Map: Manaan", "Tatooine: Star Map: Tatooine",
}

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

# --- Artificial travel-gate location set ---
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

# Companion recruits and Genoharadan bounty targets confirmed (via real
# GIT Creature List / journal-tag tracing, not guessed) to
# physically sit on one of the 4 gated planets despite their `region`
# being "Companions"/"Genoharadan" rather than a planet name. Every OTHER
# companion's real recruit point traced back to Endar Spire/Taris/
# Dantooine (none of which are gated), so only these 2 needed adding.
COMPANION_PLANET_OVERRIDE = {
    "Companion Recruited: HK-47": "Tatooine",        # tat_m17ac (tat17_08hk47_01)
    # Same physical recruit trigger as the entry above (new_companion only
    # swaps the character, not the location) -- needed as its own entry
    # because this dict is keyed by AP location NAME, and "Companion
    # Recruited: New Companion" is a separate name/id from "...: HK-47"
    # (see Locations.py). Without this, COMPANION_PLANET_OVERRIDE.get(name)
    # silently returns None for her under new_companion=on, dropping the
    # Tatooine gate for progression_system instead of crashing -- caught
    # by the pre-change checklist, not a live symptom.
    "Companion Recruited: New Companion": "Tatooine",
    "Companion Recruited: Jolee Bindo": "Kashyyyk",  # kas_m24aa (p_jolee001)
}

# All 6 Genoharadan-region locations: the questline turned out to be
# genuinely ambiguous/multi-planet -- real script tracing confirmed the
# questline's OWN start (k_psennispawn)
# fires identically from Kashyyyk, Korriban, OR Tatooine -- whichever the
# player visits first -- and the finale's completing script proved
# genuinely hard to pin to one location too. Rather than keep chasing
# exact per-stage planet gates for a quest this path-dependent, these 6
# locations never hold a progression-classified item at all, full stop --
# same add_item_rule mechanism as the alignment/level fix above, applied
# unconditionally (not gated behind progression_system -- always). The
# EXISTING GENOHARADAN_PLANET_OVERRIDE access
# rules below are UNCHANGED and still apply when progression_system is
# on -- this is purely an additional item-placement safety net, not a
# replacement for the reachability gating.
ALL_GENOHARADAN_LOCATIONS = [
    "Genoharadan: Ithorak", "Genoharadan: Lorgal", "Genoharadan: Rulan",
    "Genoharadan: Vorn", "Genoharadan: Zuulan", "Genoharadan",
]

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

    # Zaalbar/Mission real-game dependency, applied regardless
    # of progression_system -- this isn't a Progression System travel gate,
    # it's a structural vanilla-game fact: confirmed via direct dialogue
    # tree inspection of tar_m05aa's missdoor_dlg/tar05_ff_dlg/tar05_ff_dlg2
    # (the 3 conversations covering every way to reach Zaalbar's cage) that
    # EVERY branch actually freeing him is gated on a Mission-presence
    # condition (k_ptar_mischk/k_con_missionnpm/k_ptar_miszalchk) -- the
    # no-Mission branches are dead-end flavor dialogue with no scripts at
    # all (Zaalbar only speaks Shyriiwook; Mission is his translator). Only
    # matters when companion_mode=ap_gated: that's the one mode where
    # "Companion: Mission Vao" is a real item that could otherwise be
    # placed AT "Companion Recruited: Zaalbar" itself by the fill
    # algorithm with no rule to prevent it -- an unrecoverable circular
    # dependency (need Mission in the party to check Zaalbar's location,
    # need to check Zaalbar's location to receive the item that gets you
    # Mission). companion_mode=normal needs no rule here: Mission's own
    # recruit is pure vanilla with no AP item gating it, so the same
    # real-game dependency is self-enforcing through ordinary play.
    if world.options.companion_mode == 0:  # ap_gated
        add_rule(multiworld.get_location("Companion Recruited: Zaalbar", player),
                  lambda state: state.has("Companion: Mission Vao", player))

    # Companion personal-subplot self-guard, found while
    # auditing the game for other companion-dependent checks after the
    # Zaalbar/Mission fix above. Confirmed via a game-wide NCS disassembly
    # scan (every module's .rim, ~230 files) for scripts calling
    # IsNPCPartyMember/IsAvailableCreature with a real NPC_* constant:
    # each companion's own "Ebon Hawk: ..." personal-subplot journal entry
    # (Locations.py's "Ebon Hawk" region) requires THAT SAME companion to
    # be an active party member when their personal-subplot messenger
    # trigger fires (danm13's k_pdan_trig1301 spawns Bastila's mother's
    # contact/Canderous's rival Jagi/Mission's brother's contact/Juhani's
    # nemesis Xor only if that companion is IsNPCPartyMember at that
    # moment -- confirmed directly in that script's disassembly), and
    # Juhani's own final-act epilogue slide (unk_m44ac's k_punk_bastesc)
    # is directly gated on IsNPCPartyMember(Juhani) with no other branch
    # granting the same journal update. See Locations.py's
    # COMPANION_SUBPLOT_LOCATIONS for which entries were directly
    # confirmed this way vs. included defensively, and why (also the
    # single source of truth for __init__.py's companion_mode=none
    # location-removal filter, so the two never drift apart). Without
    # this rule, the fill algorithm could place a companion's own
    # guaranteed item AT their own personal-subplot check, which needs
    # that companion already available -- an unrecoverable circular
    # dependency. Only matters for companion_mode=ap_gated, the one mode
    # where these items are real gates on availability at all.
    #
    # `if loc_name in active` guard is required here: without it, this
    # loop iterates the raw dict directly, which is only safe as long as
    # nothing that removes a subplot location can coexist with
    # companion_mode==0 above. new_companion=on removes "Ebon
    # Hawk: HK-47" from _active_locations() independently of companion_mode
    # (see __init__.py), so companion_mode=ap_gated + new_companion=on
    # would call multiworld.get_location() on a location that was never
    # created and crash generation outright -- the same bug class
    # world._active_locations() (vs. raw location_table) already guards
    # against elsewhere for companion_mode=none.
    if world.options.companion_mode == 0:  # ap_gated
        active = world._active_locations()
        for loc_name, item_name in COMPANION_SUBPLOT_LOCATIONS.items():
            if loc_name not in active:
                continue
            add_rule(multiworld.get_location(loc_name, player),
                      lambda state, item_name=item_name: state.has(item_name, player))

    # Alignment/level progression restriction, applied regardless of
    # progression_system -- same as the two
    # rules just above, this isn't a Progression System mechanic, it's a
    # general fact about these 32 locations). "alignment"/"alignment_bonus"/
    # "level" locations (Locations.py's "Character" region) are entirely
    # player-choice-driven, not gated by any concrete quest/exploration
    # action -- a normal defeat_malak playthrough might never touch an
    # alignment extreme at all, and level is subject to however much a
    # player grinds or avoids combat. Neither is something the generator
    # should treat as "guaranteed reachable in a normal playthrough" the
    # way a real quest completion is, so a required progression item could
    # end up stranded behind a threshold a real player has no reason to
    # ever cross.
    #
    # FIRST ATTEMPT used LocationProgressType.EXCLUDED in
    # __init__.py's create_regions() instead of this -- reverted after a
    # REAL live generation failure: EXCLUDED locations draw ONLY from
    # Fill.py's filleritempool specifically (not "anything non-progression"
    # -- useful-classified items are a separate pool used later), and this
    # seed's filler supply wasn't large enough to cover 32 newly-excluded
    # locations on top of whatever was already excluded ("Not enough
    # filler items for excluded locations. There are 17 more excluded
    # locations than excludable items."). add_item_rule is the correct,
    # less-restrictive tool: it filters candidate items by a predicate
    # (item.advancement here) without touching which POOL the location
    # draws from at all, so useful/filler items both remain eligible --
    # only real progression items are excluded.
    # "bounty" (Additional Enemies' 40 kill-count checks) added
    # here rather than getting its own loop: same reasoning as alignment/
    # level exactly -- reaching a given bounty count isn't a guaranteed-
    # reachable quest action, it depends on how much a player explores/
    # fights, so a required progression item could end up effectively
    # locked behind however much combat a given playthrough happens to do.
    NON_PROGRESSION_LOCATION_TYPES = {"alignment", "alignment_bonus", "level", "bounty"}
    for name, data in world._active_locations().items():
        if data.location_type in NON_PROGRESSION_LOCATION_TYPES:
            add_item_rule(multiworld.get_location(name, player),
                           lambda item: not item.advancement)

    # Genoharadan item-placement safety net -- see ALL_GENOHARADAN_LOCATIONS'
    # own comment above for why. Applied unconditionally, same as the
    # alignment/level restriction just above.
    for name in ALL_GENOHARADAN_LOCATIONS:
        add_item_rule(multiworld.get_location(name, player),
                       lambda item: not item.advancement)

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

    # FIXED (real bug, found via a real generation):
    # "Progression Item: Sith Armor"/"Sith Papers"/"Taris Shield Codes"
    # are needed to ever LEAVE Taris at all ("Taris: Escaping Taris" is
    # gated on Shield Codes, which itself sits past the armor+papers
    # checkpoints) -- but nothing previously restricted WHERE these 3
    # items themselves could be placed. A real generation put "Sith
    # Papers" on a Dantooine location, an unrecoverable circular lock:
    # Dantooine is only reachable AFTER escaping Taris, so the item
    # needed to escape was stranded somewhere only reachable by having
    # already escaped. Fix: restrict these 3 items to ONLY ever
    # be placed on Taris (including the separately-named "Sith Base"
    # sub-region, physically part of Taris) or the Endar Spire (the
    # prologue ship, chronologically before Taris and always reachable
    # from the very start) -- same add_item_rule mechanism as the
    # alignment/level and Genoharadan fixes, applied unconditionally
    # within the progression_system branch (these 3 items only exist in
    # the pool at all when progression_system is on).
    TARIS_ESCAPE_ITEMS = {
        "Progression Item: Sith Armor", "Progression Item: Sith Papers",
        "Progression Item: Taris Shield Codes",
    }
    TARIS_ESCAPE_ITEM_SAFE_REGIONS = {"Taris", "Sith Base", "Endar Spire"}
    for name, data in world._active_locations().items():
        if data.region not in TARIS_ESCAPE_ITEM_SAFE_REGIONS:
            add_item_rule(multiworld.get_location(name, player),
                           lambda item: item.name not in TARIS_ESCAPE_ITEMS)
    for name in MANAAN_ENVIRO_SUIT_LOCATIONS:
        set_rule(multiworld.get_location(name, player),
                  lambda state: state.has("Progression Item: Manaan Enviro Suit", player))
    for name in STAR_FORGE_ENDGAME_LOCATIONS:
        set_rule(multiworld.get_location(name, player),
                  lambda state: state.has_all(set(ALL_STAR_MAPS), player))

    # FIXED (real bug, found via a real generation):
    # the state.has_all(ALL_STAR_MAPS) rule just above controls REACHABILITY
    # only -- it says nothing about what item can be PLACED at these
    # locations. Nothing previously stopped a Star Map item itself from
    # landing in the endgame it requires all 4 Star Maps to reach at all --
    # a real generation put "Progression Item: Star Map (Korriban)" inside
    # the Star Forge/Leviathan/Unknown World endgame, an unrecoverable
    # circular lock (need all 4 maps to get in, one of the 4 is inside).
    # Same shape as the Taris escape-items fix above: exclude just the 4
    # Star Map items specifically (other progression items, e.g. a
    # companion, are fine to place at the literal endgame -- nothing
    # needs them afterward since this IS the end).
    for name in STAR_FORGE_ENDGAME_LOCATIONS:
        add_item_rule(multiworld.get_location(name, player),
                       lambda item: item.name not in ALL_STAR_MAPS)

    # Artificial travel gate: layered on with add_rule (AND-combine), not
    # set_rule, since some of these locations (e.g. Manaan's Sea Floor/
    # Kolto Control/Hrakert Rift/Star Map, above) already got an
    # item-specific rule and both need to hold at once.
    #
    # Must use world._active_locations(), NOT the raw location_table
    # import -- a real bug, caught while testing companion_mode=none:
    # location_table unconditionally includes all 9 "Companion Recruited:
    # ..." entries, but companion_mode=none never creates Location objects
    # for them at all (see _active_locations()'s own docstring). Iterating
    # the raw table here crashed generation outright with progression_system
    # ALSO on (COMPANION_PLANET_OVERRIDE's HK-47/Jolee entries hit
    # multiworld.get_location() for a location that was never built) --
    # every other loop in this function targets a fixed, companion-mode-
    # agnostic location list, so this is the only one that needed it.
    for name, data in world._active_locations().items():
        if name in PLANET_OWN_STARMAP_LOCATION:
            continue  # see PLANET_OWN_STARMAP_LOCATION's own comment -- self-lock otherwise
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
    # Was a no-op -- AP's own test suite (test_implemented.py's
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
