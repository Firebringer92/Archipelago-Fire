from BaseClasses import MultiWorld
from worlds.generic.Rules import set_rule, add_rule, add_item_rule

from .Options import Goal
from .Locations import COMPANION_SUBPLOT_LOCATIONS
from .StoryGates import apply_story_gate_rules

# The Progression System's access rules live in StoryGates.py (story-beat gates, see
# DEVELOPMENT_HISTORY.md section 17). This module keeps the rules that apply to every seed.

# All 6 Genoharadan-region locations: the questline turned out to be
# genuinely ambiguous/multi-planet -- real script tracing confirmed the
# questline's OWN start (k_psennispawn)
# fires identically from Kashyyyk, Korriban, OR Tatooine -- whichever the
# player visits first -- and the finale's completing script proved
# genuinely hard to pin to one location too. Rather than keep chasing
# exact per-stage planet gates for a quest this path-dependent, these 6
# locations never hold a progression-classified item at all, full stop --
# same add_item_rule mechanism as the alignment/level fix above, applied
# unconditionally (not gated behind progression_system -- always). With
# progression_system on, StoryGates.py's access rules still apply to them
# -- this is purely an additional item-placement safety net, not a
# replacement for the reachability gating.
ALL_GENOHARADAN_LOCATIONS = [
    "Genoharadan: Ithorak", "Genoharadan: Lorgal", "Genoharadan: Rulan",
    "Genoharadan: Vorn", "Genoharadan: Zuulan", "Genoharadan",
]


def set_rules(multiworld: MultiWorld, player: int) -> None:
    world = multiworld.worlds[player]

    # Companion personal-subplot self-guard, found while
    # auditing the game for companion-dependent checks. Confirmed via a game-wide NCS disassembly
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
    # "datapad" (the boss datapad checks): depends on killing and looting that boss, which a route can
    # miss or a bug can swallow, so a required item must never be placed there.
    NON_PROGRESSION_LOCATION_TYPES = {"alignment", "alignment_bonus", "level", "bounty", "datapad"}
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

    apply_story_gate_rules(world)


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
    elif goal == Goal.option_reach_leviathan:
        # The first Leviathan area ("Visited: Leviathan - Prison Block"). With
        # progression_system on, that location already requires all 4 Star
        # Maps (STAR_FORGE_ENDGAME_LOCATIONS), so the goal carries that
        # requirement with it.
        multiworld.completion_condition[player] = lambda state: state.has("Reached Leviathan", player)
