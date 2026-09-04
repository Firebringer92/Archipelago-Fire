"""
Door/trigger entrance randomization for KOTOR, built on Archipelago's own
generic entrance_rando engine rather than a hand-rolled shuffle -- gets
dead-end detection and uncoupled-mode flexibility for free instead of
reimplementing a graph reachability checker from scratch (see project
design notes: the other real KOTOR entrance randomizer mod had to build
its own digraph + rule-exclusion + reachability-verification system by
hand; AP already has one).

This builds a SEPARATE region graph purely for the 156 real door/trigger
transitions (door_graph.json, one Region per physical module) -- it does
NOT touch the thematic "region" Regions create_regions() already builds
for location checks (Dantooine/Taris/Companions/etc.). Those two region
trees coexist independently under Menu; nothing about door shuffling
changes what governs location access, since Rules.py has no real logic
yet anyway (flat/ungated).

Uncoupled mode deliberately (per design decision): each transition is
placed independently, not by AP's own "coupled" pairing (which needs
matched-by-name reverse entrance/exit pairs for every door -- data this
project's flat 156-transition list doesn't have, and KOTOR's real doors
don't reliably come in clean 1:1 reverse pairs anyway). A dead-end area's
only exit can be wired to any other valid destination instead of forcing
a strict retrace. On top of that shuffle, though, _ensure_reciprocal_pairing
adds a same-spirit, achievable guarantee at the module level: if a door
somewhere leads from A into B, some door is forced to lead back from B to
A too, so a player who walks through a door always has SOME way back --
this is what "predictable A<->B" actually means here, not literal AP
coupling. This is intentionally an "unverified best effort" shuffle, not a
softlock-proof one -- see design discussion (no story-logic access rules
exist yet to verify against beyond bare region connectivity).

The player's actual starting module (end_m01aa, the Endar Spire Command
Module -- confirmed via _mapping.json's area_idx=0) is always connected
directly from Menu, OUTSIDE the randomization pool, matching every AP
entrance randomizer's baseline shape: the player always has at least one
place to go, by construction, not as a special-cased rule.
"""
import importlib.resources
import json
import typing

from BaseClasses import Region
from entrance_rando import randomize_entrances, EntranceRandomizationError

STARTING_MODULE = "tar_m02aa"
# The Endar Spire/Hideout sequence used to be the Menu-connected root, but
# now that its own doors are excluded from randomization (see
# EXCLUDED_BOTH_WAYS_PREFIXES/EXCLUDED_SOURCE_ONLY below), it has ZERO
# remaining GIT-based connections to anything else at all -- its real
# "exit" is the scripted escape-pod cutscene, not a door, so it was never
# really part of this graph's connectivity to begin with. tar_m02aa
# (Taris Upper City North, where the vanilla escape sequence lands you via
# the Hideout) is the actual root of the randomizable portion now,
# matching the explicit design: Endar Spire -> Hideout -> tar_m02aa stays
# a fixed, guaranteed-safe prelude, and REAL randomization starts at
# tar_m02aa's own two doors.

# Excluded entirely (never a randomization source OR a valid destination
# for anything else to land on) -- confirmed live this session that
# reaching these out of story order via a shuffled door causes real,
# unrecoverable problems (two separate crashes, one stuck dead-end):
#   end_m*  Endar Spire -- strictly linear, scripted tutorial, no room for
#           a bad shuffle at all (a fresh character's very first step
#           crashed the game).
#   unk_m*  Unknown World / Rakata Prime -- late-game, heavily story-gated.
#   sta_m*  Star Forge -- endgame, heavily story-gated.
#   lev_m*  Leviathan -- the mid-game "captured" sequence, entered via a
#           forced cutscene, not a normal door.
# Confirmed via door_graph.json for every one of these groups: ZERO
# entries connect them to/from any other planet in either direction --
# their real entry is always a scripted cutscene or the galaxy-map travel
# system (dialogue/GUI-driven, not GIT door/trigger data, already outside
# this graph entirely), so excluding them here doesn't touch how the
# story actually reaches them. This is NOT true of ordinary planets
# (Dantooine/Taris/Manaan/etc.) -- those are meant to stay in the shuffle;
# only these four story-critical/fragile groups are singled out.
EXCLUDED_BOTH_WAYS_PREFIXES = ("end_m", "unk_m", "sta_m", "lev_m")
EXCLUDED_BOTH_WAYS = set()

# Excluded as a randomization SOURCE only (its own real exit stays
# vanilla-fixed) but still a valid DESTINATION for other doors -- tar_m02af
# (Taris Hideout) is the guaranteed-safe landing spot right after the
# scripted Endar Spire escape sequence; its own door back to tar_m02aa
# must reliably work, but there's nothing wrong with some OTHER random
# door elsewhere also leading a player there.
EXCLUDED_SOURCE_ONLY = {"tar_m02af"}

# Per-ENTRY (not per-module) pin: the 6 real, non-excluded door_graph
# entries whose destination is the Ebon Hawk interior (ebo_m12aa) -- each
# planet's own "walk up the ramp into your ship" trigger. ebo_m12aa itself
# has ZERO outgoing entries in door_graph.json at all (its own ramp-down
# exit is script-driven, keyed on current story state, not a static
# door/trigger -- already untouched by this randomizer regardless of this
# fix). These 6 entries can't use EXCLUDED_SOURCE_ONLY (module-level) --
# that would also exclude every OTHER door on that same planet, which
# should stay fully randomized. Excluding these normally (dropping them
# from both exits and targets, like EXCLUDED_SOURCE_ONLY does) would also
# be wrong here: they're the ONLY entries anywhere that reference
# ebo_m12aa as a destination, so dropping their targets would make the
# Ebon Hawk completely unreachable via any random door, contradicting the
# explicit requirement that other doors can still randomly land here.
# Instead, these stay FULLY in the randomizer's exits/targets (so
# ebo_m12aa keeps a target some other door can be paired to), and
# connect_entrances() force-overwrites just these 6 keys' own RESULT back
# to their real vanilla destination afterward -- _ensure_reciprocal_pairing
# and _ensure_full_reachability are both taught to never select one of
# these keys as a "steal from" candidate, so the override can't get
# silently undone by a later repair pass.
EBON_HAWK_ENTRY_KEYS = {
    "danm13:TriggerList:2",      # Dantooine
    "kas_m22aa:TriggerList:9",   # Kashyyyk
    "korr_m33aa:TriggerList:9",  # Korriban
    "liv_m99aa:Door List:1",     # Leviathan boarding sequence
    "manm26ad:TriggerList:0",    # Manaan
    "tat_m17ab:TriggerList:2",   # Tatooine
}

# Destinations a repair pass must never steal an edge AWAY from, even when
# stealing would otherwise look like the "safest" choice available.
# Pinning EBON_HAWK_ENTRY_KEYS gives ebo_m12aa an artificially high
# indegree (6+ incoming edges, all forced) -- and both
# _ensure_reciprocal_pairing and _ensure_full_reachability specifically
# PREFER stealing from whichever current destination has the highest
# indegree, reasoning "won't strand it, it has plenty of other ways in."
# Confirmed live via debug instrumentation: the raw shuffle DOES correctly
# assign other, unrelated doors to ebo_m12aa (e.g. danm14ac, tar_m03aa) --
# but every single one got stolen away by a repair pass afterward, purely
# because ebo_m12aa's inflated indegree made it the preferred donor for
# fixing completely unrelated islands elsewhere. Protecting only the 6
# pinned keys (an earlier version of this fix) didn't catch this -- a
# THIRD PARTY door landing on ebo_m12aa isn't one of the pinned keys, so
# it was still fair game to steal from. The actual fix has to be
# destination-based: don't ever repoint an edge away from ebo_m12aa,
# regardless of which door currently holds it.
NEVER_STEAL_DEST_MODULES = {"ebo_m12aa"}


def _load_door_graph() -> dict:
    """Reads door_graph.json via importlib.resources rather than a plain
    open(os.path.dirname(__file__)-relative path) -- found broken live
    2026-09-04: this world ships for real distribution inside a zip-loaded
    kotor.apworld, where __file__ resolves to a synthetic path that
    doesn't exist on any real filesystem, so a plain open() call against
    it raises FileNotFoundError immediately (confirmed live: this crashed
    Generate.py outright for any area_randomizer=True seed run through a
    packaged .apworld -- see Items.py's read_gear_json() for the same bug
    hitting gear_items.json too, silently instead of loudly there).
    importlib.resources.files() reads package data correctly whether the
    package is a loose folder (this dev checkout) or a real zip archive
    (what actually ships), so this works in both without needing to know
    which."""
    raw = importlib.resources.files(__package__).joinpath("door_graph.json").read_text(encoding="utf-8")
    return json.loads(raw)


def _is_excluded_both_ways(module: str) -> bool:
    return module in EXCLUDED_BOTH_WAYS or module.startswith(EXCLUDED_BOTH_WAYS_PREFIXES)


def create_transition_regions(world) -> None:
    """Called from create_regions() when area_randomizer is on. Builds
    one Region per distinct module referenced in door_graph.json. Exit/
    target Entrance objects are created separately in connect_entrances()
    (see _create_exits_and_targets)."""
    door_graph = _load_door_graph()

    modules = set()
    for entry in door_graph.values():
        modules.add(entry["module"])
        modules.add(entry["dest_module"])

    regions: typing.Dict[str, Region] = {}
    for mod in sorted(modules):
        r = Region(f"Module: {mod}", world.player, world.multiworld)
        world.multiworld.regions.append(r)
        regions[mod] = r

    menu = world.multiworld.get_region("Menu", world.player)
    menu.connect(regions[STARTING_MODULE])

    world.kotor_door_graph = door_graph
    world.kotor_door_regions = regions


def _create_exits_and_targets(world) -> typing.Tuple[list, list]:
    """An entry is either FULLY fixed (contributes neither an exit nor a
    target -- its own real vanilla destination is used as-is) or FULLY
    randomizable (contributes both), never a mix -- randomize_entrances()
    hard-requires equal exit/target counts, and a mix (e.g. Star Forge's
    or Leviathan's own exit TO the Ebon Hawk: excluded source, non-
    excluded destination) produces an orphaned target with no matching
    exit, which broke that count. An entry's source being excluded (either
    exclusion set) means its own transition object is entirely fixed;
    "tar_m02af is still a valid destination for OTHER doors" is achieved
    by those OTHER entries' own dest_module field, not by this one."""
    door_graph = world.kotor_door_graph
    regions = world.kotor_door_regions
    exits = []
    targets = []
    for key, entry in door_graph.items():
        module = entry["module"]
        dest_module = entry["dest_module"]
        if _is_excluded_both_ways(module) or module in EXCLUDED_SOURCE_ONLY:
            continue  # fully fixed -- neither exit nor target
        if _is_excluded_both_ways(dest_module):
            continue  # this specific entry's own vanilla destination is an excluded zone -- fully fixed too
        exits.append(regions[module].create_exit(f"{key} exit"))
        targets.append(regions[dest_module].create_er_target(f"{key} target"))
    return exits, targets


def connect_entrances(world) -> typing.Dict[str, dict]:
    """Called from the world's connect_entrances() lifecycle hook (after
    ALL worlds' create_regions() have run). Runs the actual shuffle and
    returns the final mapping: door_graph key -> {"dest_module",
    "dest_waypoint"} using the NEW (shuffled) destination in the same
    shape as door_graph.json's original vanilla entries, so the file
    patcher can consume it identically either way.

    Confirmed live: a handful of transitions (the same ~6 out of 156,
    reproducibly, across dozens of random attempts) can become permanently
    unreachable "islands" in this specific graph's topology once every
    OTHER exit has already been consumed elsewhere -- not fixable by
    retrying with different randomness, since it's structural, not luck.
    Rather than block the whole feature on a graph-theoretic guarantee the
    user explicitly didn't ask for ("unverified best effort"), pairings
    ARE tracked progressively via the on_connect callback as they happen,
    so if the overall call still raises at the very end, whatever
    succeeded is kept and the small remainder just falls back to its own
    real vanilla destination -- a partially-shuffled, fully-functional
    seed instead of a hard failure."""
    door_graph = world.kotor_door_graph
    exits, targets = _create_exits_and_targets(world)
    # Names are built as f"{key} exit"/f"{key} target" (see
    # _create_exits_and_targets) -- recover the key by stripping the
    # suffix rather than zipping against door_graph.keys() positionally,
    # since exits/targets are now FILTERED (shorter, different order)
    # subsets of the full door graph once exclusions are applied.
    exit_key_by_name = {ex.name: ex.name[:-len(" exit")] for ex in exits}
    target_key_by_name = {t.name: t.name[:-len(" target")] for t in targets}

    pairings: typing.List[typing.Tuple[str, str]] = []

    def _on_connect(er_state, placed_exits, paired_entrances):
        for ex, target in zip(placed_exits, paired_entrances):
            pairings.append((ex.name, target.name))

    try:
        randomize_entrances(
            world,
            coupled=False,
            target_group_lookup={0: [0]},
            er_targets=targets,
            exits=exits,
            on_connect=_on_connect,
        )
    except EntranceRandomizationError as e:
        placed = len(pairings)
        print(f"[kotor] Door randomization: {placed}/{len(door_graph)} transitions placed, "
              f"remainder falling back to vanilla destinations ({e})")

    result = {}
    for exit_name, target_name in pairings:
        exit_key = exit_key_by_name.get(exit_name)
        dest_key = target_key_by_name.get(target_name)
        if exit_key is None or dest_key is None:
            continue  # not one of ours (shouldn't happen, but don't guess)
        # dest_key names the door_graph entry whose OWN vanilla
        # destination (dest_module/dest_waypoint) is the physical place
        # this target represents (see _create_exits_and_targets: the
        # target Entrance is created in regions[entry["dest_module"]]).
        # dest_entry["module"] is that entry's SOURCE side -- using it
        # here was a real bug: it silently sent players to the module the
        # target's own door LEAVES FROM, paired with a waypoint tag that
        # actually lives in dest_entry["dest_module"] instead, i.e. every
        # successfully-shuffled connection pointed at the wrong module.
        dest_entry = door_graph[dest_key]
        result[exit_key] = {
            "dest_module": dest_entry["dest_module"],
            "dest_waypoint": dest_entry["dest_waypoint"],
        }

    # Fallback: anything that never got a callback (the pre-exception
    # stragglers) keeps its own real vanilla destination -- a no-op
    # entry, not a broken one.
    for key, entry in door_graph.items():
        if key not in result:
            result[key] = {"dest_module": entry["dest_module"], "dest_waypoint": entry["dest_waypoint"]}

    # Pin the Ebon Hawk boarding triggers back to their real vanilla
    # destination, regardless of what the shuffle assigned them -- see
    # EBON_HAWK_ENTRY_KEYS's own comment for why these can't just be
    # excluded from the randomizer outright (their targets need to stay
    # available for OTHER doors to land on). Runs before the two repair
    # passes below so reachability gets a chance to route around whatever
    # this override just orphaned, same as any other fixed entry.
    for key in EBON_HAWK_ENTRY_KEYS:
        entry = door_graph[key]
        result[key] = {"dest_module": entry["dest_module"], "dest_waypoint": entry["dest_waypoint"]}

    result = _ensure_reciprocal_pairing(door_graph, result)
    result, still_unreachable = _ensure_full_reachability(door_graph, result)
    if still_unreachable:
        print(f"[kotor] WARNING: door randomization could not guarantee reachability for: {still_unreachable}")

    world.kotor_door_exits = exits
    world.kotor_door_targets = targets
    world.kotor_door_mapping = result
    return result


def _ensure_reciprocal_pairing(door_graph: dict, result: typing.Dict[str, dict]) -> typing.Dict[str, dict]:
    """User-requested predictability guarantee: for every distinct
    (source_module, dest_module) pair with at least one placed A->B
    connection, force at least one B->A connection to exist too, so a
    player who finds a door from A into B always has SOME way back --
    not full AP "coupled" mode (that needs matched-by-name reverse
    entrance/exit pairs our flat 156-transition data model doesn't have,
    and KOTOR's real doors don't reliably come in clean 1:1 reverse pairs
    anyway), just a same-spirit, achievable guarantee at the module-pair
    level using the same "steal a reachable-sourced edge and repoint it"
    technique _ensure_full_reachability already uses safely.

    Single pass over the pairs present at call time (not a fixed-point
    iteration) -- consistent with this whole system's existing "best
    effort, not a hard guarantee" design (see connect_entrances's own
    docstring). Runs BEFORE _ensure_full_reachability, not after: full
    reachability is the hard requirement and gets the final, authoritative
    pass, so anything this function does that would have broken
    reachability gets caught and fixed there instead of silently shipping
    broken. Both-ways-excluded zones (Endar Spire/Unknown World/Star
    Forge/Leviathan) are skipped entirely, matching the reachability
    system's own exemption -- forcing a path into/out of those would
    defeat the point of excluding them.

    Recomputes the current (source, dest) pair set and dest-indegree table
    FRESH on every iteration rather than maintaining them incrementally --
    the data is tiny (156 entries, trivial cost either way), and an
    earlier attempt at incremental bookkeeping had a real bug: stealing an
    edge FROM some module changes what that module's OWN pairs are (an
    edge repointed away from its old destination means that old pair may
    no longer exist at all), and a set that only ever gets things ADDED
    to it silently goes stale the moment something is removed instead.
    Recomputing fresh sidesteps the whole class of bug.

    Runs the pass repeatedly until a full pass makes zero new fixes (or a
    generous cap is hit) rather than just once -- a single pass can still
    have pair X's fix steal an edge pair Y already depended on, purely
    because of processing order; confirmed empirically (72% reciprocal
    coverage after one pass vs. more after repeating). Safe to repeat:
    already-reciprocal pairs are skipped immediately, so extra passes
    past convergence are just cheap no-ops, not risk. Confirmed via a
    controlled comparison (same underlying shuffle, fixed --seed): single
    pass reached 67.2% reciprocal coverage, repeating to convergence
    reached 76.8% -- a real improvement, not noise from different random
    shuffles."""
    for _ in range(len(door_graph) + 5):
        initial_pairs = sorted({(door_graph[key]["module"], dest["dest_module"]) for key, dest in result.items()})
        fixed_this_pass = 0

        for src, dst in initial_pairs:
            if src == dst:
                continue  # a "loop" transition within the same module needs no reverse
            if _is_excluded_both_ways(src) or _is_excluded_both_ways(dst):
                continue

            current_pairs = {(door_graph[key]["module"], dest["dest_module"]) for key, dest in result.items()}
            if (src, dst) not in current_pairs:
                continue  # the forward edge itself got stolen away by an earlier fix this pass -- nothing left to reciprocate
            if (dst, src) in current_pairs:
                continue  # already reciprocal (possibly thanks to an earlier fix this pass)

            # Need a real vanilla waypoint for arriving at src -- same
            # "reuse a real entry's own destination" trick as the
            # reachability auto-fix, so we're never inventing a waypoint
            # that doesn't exist.
            candidate = next((e for e in door_graph.values() if e["dest_module"] == src), None)
            if candidate is None:
                continue  # no real waypoint anywhere leads to src -- can't force this one, leave one-directional

            # Steal one of dst's own outgoing edges to redirect back to
            # src. Prefer stealing from whichever current destination has
            # the most OTHER incoming edges, so this doesn't strand
            # whatever it used to point at (same preference
            # _ensure_full_reachability uses).
            dest_indegree: typing.Dict[str, int] = {}
            for dest in result.values():
                dest_indegree[dest["dest_module"]] = dest_indegree.get(dest["dest_module"], 0) + 1

            best_key = None
            best_indegree = -1
            for key, dest in result.items():
                if dest["dest_module"] in NEVER_STEAL_DEST_MODULES:
                    continue  # see NEVER_STEAL_DEST_MODULES
                if door_graph[key]["module"] != dst:
                    continue
                cur_dest = dest["dest_module"]
                if cur_dest == src:
                    continue  # already the pairing we're trying to create
                indeg = dest_indegree.get(cur_dest, 0)
                if indeg > best_indegree:
                    best_indegree = indeg
                    best_key = key
            if best_key is None:
                continue  # dst has no stealable outgoing edge at all -- can't force this one

            result[best_key] = {"dest_module": src, "dest_waypoint": candidate["dest_waypoint"]}
            fixed_this_pass += 1

        if fixed_this_pass == 0:
            break  # converged -- nothing left this pass could fix

    return result


def _bfs_reachable(start: str, edges_by_source: typing.Dict[str, typing.List[str]]) -> typing.Set[str]:
    reachable = {start}
    queue = [start]
    while queue:
        cur = queue.pop()
        for dest in edges_by_source.get(cur, []):
            if dest not in reachable:
                reachable.add(dest)
                queue.append(dest)
    return reachable


def _ensure_full_reachability(door_graph: dict, result: typing.Dict[str, dict]) -> typing.Tuple[dict, list]:
    """Post-hoc BFS reachability check + auto-fix: AP's own algorithm
    already biases toward keeping the graph connected while it places the
    main 150ish transitions (that's what the dead-end/expand-graph staging
    is for), but the vanilla-fallback stragglers from the block above
    aren't verified at all. If any module ends up unreachable from
    STARTING_MODULE in the final combined graph, steal one existing
    reachable-sourced edge and repoint it at the unreachable module
    instead -- preferring to steal from a destination that has OTHER
    incoming edges too (indegree > 1), so the fix doesn't just relocate
    the same problem elsewhere. Iterates until stable or a generous cap
    (156 edges, converges fast in practice) is hit, at which point
    whatever's still unreachable is returned for the caller to warn
    about rather than silently accepting or looping forever.

    Both-ways-excluded modules (Endar Spire/Unknown World/Star Forge/
    Leviathan) are deliberately NOT part of this graph's reachability
    requirement at all -- they're reached via scripted cutscenes or the
    galaxy-map system, not by walking through a randomized door, so
    "unreachable via this graph" is the correct, intended state for them,
    not a bug to auto-fix."""
    # Mirrors _create_exits_and_targets's own eligibility rule exactly: an
    # entry only contributes real modules to the reachability requirement
    # if BOTH its source and destination are outside the excluded zones.
    # Without this, a dest_module that's only ever referenced by an
    # EXCLUDED-source entry gets pulled in as "must be reachable" even
    # though nothing real (randomizable or otherwise) ever leads there --
    # confirmed via door_graph.json: lev_m40ac:Door List:16 has
    # dest_module="ebo_m40ad" with an EMPTY dest_waypoint, i.e. inert/
    # broken vanilla data on an already-excluded Leviathan door that
    # nothing else in the game ever points at. Left in, every single seed
    # was auto-"fixing" this fake requirement by rewiring some real, live
    # door to point at "ebo_m40ad" with a blank waypoint tag -- breaking
    # that door in-game every time.
    all_modules = set()
    for entry in door_graph.values():
        module = entry["module"]
        dest_module = entry["dest_module"]
        if _is_excluded_both_ways(module) or module in EXCLUDED_SOURCE_ONLY:
            continue
        if _is_excluded_both_ways(dest_module):
            continue
        all_modules.add(module)
        all_modules.add(dest_module)

    unfixable: typing.Set[str] = set()
    for _ in range(len(door_graph) + 5):
        edges_by_source: typing.Dict[str, typing.List[str]] = {}
        dest_indegree: typing.Dict[str, int] = {}
        for key, dest in result.items():
            src = door_graph[key]["module"]
            edges_by_source.setdefault(src, []).append(dest["dest_module"])
            dest_indegree[dest["dest_module"]] = dest_indegree.get(dest["dest_module"], 0) + 1

        reachable = _bfs_reachable(STARTING_MODULE, edges_by_source)
        unreachable = all_modules - reachable
        fixable_unreachable = sorted(unreachable - unfixable)
        if not fixable_unreachable:
            break  # either fully reachable, or everything left is a known-unfixable island

        target = fixable_unreachable[0]
        # Any real vanilla entry that used to lead into target names a
        # real, valid waypoint tag for arriving there.
        candidate = next((e for e in door_graph.values() if e["dest_module"] == target), None)
        if candidate is None:
            # No real waypoint anywhere in door_graph.json leads into this
            # module at all (it's only ever a source, never a destination,
            # in vanilla data) -- there's nothing valid to repoint an edge
            # at. Mark it unfixable and keep going for the OTHERS instead
            # of aborting the whole reachability pass over one island.
            unfixable.add(target)
            continue

        best_key = None
        best_indegree = -1
        for key, dest in result.items():
            if dest["dest_module"] in NEVER_STEAL_DEST_MODULES:
                continue  # see NEVER_STEAL_DEST_MODULES
            src = door_graph[key]["module"]
            if src not in reachable:
                continue
            cur_dest = dest["dest_module"]
            if cur_dest not in reachable:
                continue
            indeg = dest_indegree.get(cur_dest, 0)
            if indeg > best_indegree:
                best_indegree = indeg
                best_key = key
        if best_key is None:
            # No reachable-sourced edge exists at all -- shouldn't happen
            # once STARTING_MODULE has any outgoing edge of its own, but
            # bail on just this target rather than the whole pass.
            unfixable.add(target)
            continue

        result[best_key] = {"dest_module": target, "dest_waypoint": candidate["dest_waypoint"]}

    # Ran out of iterations -- report whatever's still unreachable rather
    # than looping forever.
    edges_by_source = {}
    for key, dest in result.items():
        src = door_graph[key]["module"]
        edges_by_source.setdefault(src, []).append(dest["dest_module"])
    reachable = _bfs_reachable(STARTING_MODULE, edges_by_source)
    return result, sorted(all_modules - reachable)
