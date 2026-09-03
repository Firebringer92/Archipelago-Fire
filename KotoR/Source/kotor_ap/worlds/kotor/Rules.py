from BaseClasses import MultiWorld

from .Options import Goal


def set_rules(multiworld: MultiWorld, player: int) -> None:
    # Deliberately no access rules yet -- all 100 locations are open from
    # the start. A real, story-accurate progression gate (you can't check
    # a Taris-only location before reaching Taris, etc.) needs real quest-
    # order research across the whole game; that's separate future work,
    # not something to fake with guessed rules. This flat model is honest
    # about what it is: enough to exercise the detection/delivery pipeline
    # end-to-end, not a balanced, shippable randomizer seed.
    pass


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
