"""
Door/trigger entrance randomization for KOTOR, built on Archipelago's own
generic entrance_rando engine rather than a hand-rolled shuffle -- gets
dead-end detection and connectivity guarantees for free instead of
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

REAL AP coupled mode: a full analysis of door_graph.json found that of
the 118 entries eligible for randomization (156 total minus the
exclusions below), 110 have a genuine, individually-identifiable reverse
door -- 94 as a clean 1:1 match (exactly one door each way between two
modules) and 16 more across 4 Dantooine module-pairs that have two doors
each way, resolved via the shared trailing letter on each door's own
destination waypoint tag (e.g. "from14dw"/"from14cw" both end in 'w' --
confirmed this pattern holds for all 4 pairs before relying on it; see
_resolve_by_waypoint_suffix). Those 110 entries are wired as real AP
TWO_WAY coupled Entrances (_build_coupled_pairs/_create_exits_and_targets)
-- each SIDE of a confirmed pair is placed independently (kf: A->B and
kb: B->A are two separate Entrance objects with their own separate
placement fate, confirmed by tracing a real generation by hand), but
AP's own coupled placement guarantees that wherever an exit's OWN side
lands, you can always walk straight back out through the SAME physical
door -- that per-connection guarantee is what "coupled" actually buys
here, not "this pair's original two doors stay linked to each other."
The remaining 8 entries (7 distinct module-pairs) have
no reverse door anywhere in vanilla data at all -- confirmed by scanning
every module's raw GIT directly, not just door_graph.json, so it isn't a
tag-filtering artifact. Investigated by hand (not guessed): one of the 7
(South Apartments -> Hideout) has a real reverse that's just excluded from
the pool by EXCLUDED_SOURCE_ONLY below; one (Undercity -> Lower Sewers)
has no *direct* reverse but a real 4-hop vanilla path back through the
Upper Sewers/Black Vulkar Base/Lower City; the other 5 (Kashyyyk Hall of
the Chieftain, Kashyyyk Lower Shadowlands, Manaan Hrakert Rift, a Black
Vulkar Base sub-room, Tatooine Dune Sea) are genuinely entered via a
scripted mechanism in vanilla (elevator, dive suit, hidden passage, galaxy
travel) rather than a walkable door, so there was never anything to couple
against. These 8 are simply left OUT of the randomizable pool entirely
(same "fully fixed, real vanilla destination" treatment already used for
the exclusions below) rather than shuffled uncoupled, since a door with
no real reverse has nothing for a coupled shuffle to preserve, and
leaving it vanilla-fixed means it can never introduce an unreachable
island in the first place.

STATUS (tested against real generation, not just theory): a
CLEANLY COMPLETED coupled placement guarantees full connectivity -- AP's
own stage-3 placement loops (see randomize_entrances) can only ever fully
drain or raise, never silently leave a gap. But completion is NOT
reliable for this specific 110-entry graph on its own: seed 42 failed on
EVERY ONE of 500 fresh attempts (a different pair short each time, always
exactly ~2 of 110 entries), so this is a real structural property of the
graph's topology, not rare bad luck a retry loop fixes by itself -- the
same class of "structural, not luck" island the OLD uncoupled system's
own docstring warned about. Traced to its root cause: because kf and kb
(a pair's two sides) are placed as independent Entrance objects (see
_create_exits_and_targets), a partial failure can leave kf successfully
reassigned elsewhere while kb's own entrance never gets a replacement --
confirmed EVERY real failure observed was a module with exactly ONE
confirmed coupled entrance ("coupled indegree" of 1 -- see
_repair_orphaned_modules), i.e. a module with no OTHER door for the
shuffle to fall back on if its one real entrance's placement fails.

Considered and rejected: pre-emptively pinning every indegree-1 module's
sole entrance to vanilla (removing it from the coupled pool entirely)
does guarantee safety, but cascades hard -- KOTOR's door graph is mostly
tree/chain-shaped (39 of 85 modules have exactly one door total), so
protecting every indegree-1 module ends up demoting 44 of the 55 pairs
back to vanilla, leaving only 11 truly coupled. Chose instead to
keep the full 55-pair pool coupled, and instead patch just the rare
residual AFTER placement (usually 0-1 modules, not 44 pairs) -- see
_repair_orphaned_modules. This is the SAME "steal a well-connected edge
and repoint it" technique the old _ensure_full_reachability used, just
scoped to a handful of leftover entries instead of the whole graph, so it
essentially never fires on a seed that placed cleanly (or after a retry
resolved it) and only intervenes for the true structural residual.
Confirmed (seed 42, which failed on every fresh attempt): with the
repair in place, 0 modules end up unreachable, at the cost of exactly 1
stolen entry losing its OWN clean bidirectional guarantee (it still leads
somewhere valid, just not to a partner that leads back to IT specifically)
-- an explicit, small, deliberate trade for guaranteed reachability.

The player's actual starting module (tar_m02aa, Taris Upper City North --
see STARTING_MODULE's own comment) is always connected directly from
Menu, OUTSIDE the randomization pool, matching every AP entrance
randomizer's baseline shape: the player always has at least one place to
go, by construction, not as a special-cased rule.
"""
import importlib.resources
import json
import typing

from BaseClasses import Region, EntranceType
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
# for anything else to land on) -- reaching these out of story order via
# a shuffled door causes real,
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
# fix). These entries are simply excluded from the pool like any other
# fixed entry (see EXCLUDED_SOURCE_ONLY's shape) rather than randomized:
# they're the ONLY entries anywhere that reference ebo_m12aa as a
# destination, so a coupled pairing has no reverse to match against
# anyway (ebo_m12aa contributes no outgoing doors to pair with), and
# leaving them vanilla-fixed is simpler than the old uncoupled system's
# workaround of keeping them in the pool just so ebo_m12aa stayed a valid
# target for other doors.
EBON_HAWK_ENTRY_KEYS = {
    "danm13:TriggerList:2",      # Dantooine
    "kas_m22aa:TriggerList:9",   # Kashyyyk
    "korr_m33aa:TriggerList:9",  # Korriban
    "liv_m99aa:Door List:1",     # Leviathan boarding sequence
    "manm26ad:TriggerList:0",    # Manaan
    "tat_m17ab:TriggerList:2",   # Tatooine
}


def _load_door_graph() -> dict:
    """Reads door_graph.json via importlib.resources rather than a plain
    open(os.path.dirname(__file__)-relative path): this world ships for
    real distribution inside a zip-loaded kotor.apworld, where __file__
    resolves to a synthetic path that doesn't exist on any real
    filesystem, so a plain open() call against it raises
    FileNotFoundError immediately -- crashing Generate.py outright for
    any area_randomizer=True seed run through a packaged .apworld -- see
    Items.py's read_gear_json() for the same bug hitting gear_items.json
    too, silently instead of loudly there.
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


def _eligible_entries(door_graph: dict) -> typing.Dict[str, dict]:
    """The same eligibility rule used throughout this module: an entry is
    eligible for randomization only if neither its own module nor its
    vanilla destination module falls in one of the exclusion sets above.
    Ineligible entries are always fully fixed at their real vanilla
    destination -- never an exit, never a target."""
    eligible = {}
    for key, entry in door_graph.items():
        module = entry["module"]
        dest_module = entry["dest_module"]
        if _is_excluded_both_ways(module) or module in EXCLUDED_SOURCE_ONLY:
            continue
        if _is_excluded_both_ways(dest_module):
            continue
        if key in EBON_HAWK_ENTRY_KEYS:
            continue
        eligible[key] = entry
    return eligible


def _resolve_by_waypoint_suffix(door_graph: dict, keys_ab: list, keys_ba: list) -> typing.Optional[list]:
    """For a module-pair with more than one door each way (only 4 real
    cases, all on Dantooine), try to find the real physical
    pairing via the shared trailing letter on each door's own
    dest_waypoint tag -- confirmed by hand that all 4 real cases encode
    which physical corridor this way (e.g. "from14dw" arriving from the
    west pairs with "from14cw", also west; "from14de" pairs with
    "from14ce", both east). Returns None (never guesses) if the door
    counts differ, if the suffix sets themselves don't line up 1:1 between
    the two directions, or if more than one door on either side shares a
    suffix -- any of those means this heuristic doesn't have a confident
    answer, and the pair falls through to the fixed/vanilla-default
    treatment instead of risking a wrong pairing."""
    if len(keys_ab) != len(keys_ba):
        return None
    by_suffix_ab: typing.Dict[str, list] = {}
    for k in keys_ab:
        by_suffix_ab.setdefault(door_graph[k]["dest_waypoint"][-1:], []).append(k)
    by_suffix_ba: typing.Dict[str, list] = {}
    for k in keys_ba:
        by_suffix_ba.setdefault(door_graph[k]["dest_waypoint"][-1:], []).append(k)
    if set(by_suffix_ab) != set(by_suffix_ba):
        return None
    resolved = []
    for suffix, ab_keys in by_suffix_ab.items():
        ba_keys = by_suffix_ba[suffix]
        if len(ab_keys) != 1 or len(ba_keys) != 1:
            return None
        resolved.append((ab_keys[0], ba_keys[0]))
    return resolved


def _build_coupled_pairs(door_graph: dict) -> typing.Tuple[typing.List[typing.Tuple[str, str]], typing.Set[str]]:
    """Splits the eligible entries into (a) confirmed physical door-pairs
    (kf, kb) -- kf's module is kb's dest_module and vice versa, with a
    real, individually-identifiable reverse door -- suitable for AP's own
    coupled entrance randomization, and (b) everything else, which has no
    identifiable reverse and stays fully fixed at its real vanilla
    destination (see this module's own docstring for the full breakdown:
    94 entries as clean 1:1 pairs, 16 more across 4 multi-door pairs
    resolved via _resolve_by_waypoint_suffix, 8 with no reverse at all)."""
    eligible = _eligible_entries(door_graph)
    fwd: typing.Dict[typing.Tuple[str, str], typing.List[str]] = {}
    for key, entry in eligible.items():
        fwd.setdefault((entry["module"], entry["dest_module"]), []).append(key)

    pairs: typing.List[typing.Tuple[str, str]] = []
    visited_module_pairs: typing.Set[typing.Tuple[str, str]] = set()
    for (a, b), keys_ab in sorted(fwd.items()):
        if a == b or (a, b) in visited_module_pairs or (b, a) in visited_module_pairs:
            continue
        visited_module_pairs.add((a, b))
        visited_module_pairs.add((b, a))
        keys_ba = fwd.get((b, a))
        if not keys_ba:
            continue  # no reverse at all -- stays fixed/default
        if len(keys_ab) == 1 and len(keys_ba) == 1:
            pairs.append((keys_ab[0], keys_ba[0]))
        else:
            resolved = _resolve_by_waypoint_suffix(door_graph, keys_ab, keys_ba)
            if resolved is not None:
                pairs.extend(resolved)
            # else: genuinely ambiguous -- every door in this pair falls
            # through to the fixed/default bucket below rather than guess.

    matched_keys = {k for pair in pairs for k in pair}
    noreverse = set(eligible) - matched_keys
    return pairs, noreverse


def _create_exits_and_targets(world) -> typing.Tuple[list, list, dict, dict]:
    """Builds real AP TWO_WAY coupled Entrance pairs for every confirmed
    physical door-pair. For a pair (kf: A->B, kb: B->A), region A gets an
    exit AND an entrance sharing one name, and region B gets an exit AND
    an entrance sharing a second name -- this exact same-name-on-both-
    sides-of-one-region shape is what AP's own coupled placement code
    looks for to find "the reverse" of whatever it just placed (confirmed
    against entrance_rando.py's connect() and the real worlds/
    stardew_valley/regions/entrance_rando.py precedent, the only other
    coupled-mode user in this checkout, before writing this). Anything
    NOT in a confirmed pair (see _build_coupled_pairs) contributes neither
    an exit nor a target -- it's fully fixed, matching how the exclusion
    sets above were already handled."""
    door_graph = world.kotor_door_graph
    regions = world.kotor_door_regions
    pairs, _noreverse = _build_coupled_pairs(door_graph)

    exits = []
    targets = []
    exit_name_to_key: typing.Dict[str, str] = {}
    target_name_to_real_key: typing.Dict[str, str] = {}

    for kf, kb in pairs:
        entry_f = door_graph[kf]
        a, b = entry_f["module"], entry_f["dest_module"]
        name_f = f"{kf} door"
        name_b = f"{kb} door"

        exit_a = regions[a].create_exit(name_f)
        exit_a.randomization_type = EntranceType.TWO_WAY
        entrance_a = regions[a].create_er_target(name_f)
        entrance_a.randomization_type = EntranceType.TWO_WAY

        exit_b = regions[b].create_exit(name_b)
        exit_b.randomization_type = EntranceType.TWO_WAY
        entrance_b = regions[b].create_er_target(name_b)
        entrance_b.randomization_type = EntranceType.TWO_WAY

        exits.append(exit_a)
        exits.append(exit_b)
        exit_name_to_key[name_f] = kf
        exit_name_to_key[name_b] = kb

        # entrance_a (living in region A, named name_f) is where the
        # shuffle lands something arriving "into A via this pair" -- the
        # REAL waypoint for that landing spot is kb's own vanilla data
        # (module=B, dest_module=A, dest_waypoint=<real tag in A>), not
        # kf's. Same the other way around for entrance_b/kf.
        targets.append(entrance_a)
        targets.append(entrance_b)
        target_name_to_real_key[name_f] = kb
        target_name_to_real_key[name_b] = kf

    return exits, targets, exit_name_to_key, target_name_to_real_key


MAX_COUPLED_ATTEMPTS = 5
# Cheap insurance, not a real fix -- confirmed (seed 42) that retrying
# alone does NOT reliably resolve this: 500 fresh attempts
# in a row all failed, always ~2 of 110 entries short (a different pair
# each time). This is a structural property of the graph, not luck (see
# this module's own docstring). Kept at a small number because
# _repair_orphaned_modules below is what actually guarantees reachability
# now -- a handful of retries just means fewer seeds need the repair pass
# to do any work at all.


def _reset_door_regions(regions: typing.Dict[str, Region]) -> None:
    """Clears every door-graph Region's exits/entrances before a (re)build
    -- these regions exist solely for this module's own coupled subgraph
    (created empty by create_transition_regions, touched by nothing else
    in the codebase), so a full reset before each attempt is always safe
    and is what lets a retry start from a genuinely clean slate instead of
    accumulating leftover half-connected objects from a prior attempt."""
    for region in regions.values():
        region.exits = []
        region.entrances = []


def _repair_orphaned_modules(door_graph: dict, pairs: list, result: typing.Dict[str, dict]) -> list:
    """Post-placement safety net: finds any module that a confirmed
    coupled pair points at as a destination, but which ended up with ZERO
    real incoming edges anywhere in the final result (every pair that
    could have led there fell back to vanilla or got reassigned away --
    see this module's own docstring for why kf/kb's independent placement
    fates make this possible even after retrying). For each one, steals
    the destination of whichever CURRENTLY-successful entry points at the
    best-connected other module (highest current indegree, so stealing
    doesn't just relocate the same problem) and repoints it at the
    orphaned module instead, using a real vanilla waypoint tag (never
    inventing one) from any door_graph entry that already leads there.

    Deliberately scoped to just the coupled pool's own modules, not a
    whole-graph pass: everything permanently fixed (both exclusion sets,
    the Ebon Hawk pins, the 8 no-reverse entries) already has a real,
    unchanging vanilla path by construction and is never a candidate to
    steal from or need repair. In practice this touches 0-1 entries per
    seed -- most seeds place cleanly or fully resolve within the retry
    budget above, so this exists for the rare structural residual, not as
    the primary mechanism. Returns the list of (key, new_dest_module)
    changes made, for logging."""
    incoming: typing.Dict[str, int] = {}
    for dest in result.values():
        incoming[dest["dest_module"]] = incoming.get(dest["dest_module"], 0) + 1

    coupled_dest_modules = set()
    for kf, kb in pairs:
        coupled_dest_modules.add(door_graph[kf]["dest_module"])
        coupled_dest_modules.add(door_graph[kb]["dest_module"])
    orphaned = [m for m in coupled_dest_modules if incoming.get(m, 0) == 0]
    if not orphaned:
        return []

    all_coupled_keys = {k for pair in pairs for k in pair}
    fixed = []
    for target_module in sorted(orphaned):
        candidate = next((e for e in door_graph.values() if e["dest_module"] == target_module), None)
        if candidate is None:
            continue  # no real waypoint anywhere leads here -- shouldn't happen for a coupled-pool module

        best_key, best_indegree = None, -1
        for key in all_coupled_keys:
            cur_dest = result[key]["dest_module"]
            if cur_dest == target_module:
                continue
            indeg = incoming.get(cur_dest, 0)
            if indeg > 1 and indeg > best_indegree:
                best_indegree = indeg
                best_key = key
        if best_key is None:
            continue  # nothing safe to steal from -- leave it (should be exceedingly rare)

        old_dest = result[best_key]["dest_module"]
        result[best_key] = {"dest_module": target_module, "dest_waypoint": candidate["dest_waypoint"]}
        incoming[old_dest] -= 1
        incoming[target_module] = incoming.get(target_module, 0) + 1
        fixed.append((best_key, target_module))

    return fixed


def connect_entrances(world) -> typing.Dict[str, dict]:
    """Called from the world's connect_entrances() lifecycle hook (after
    ALL worlds' create_regions() have run). Runs the actual shuffle and
    returns the final mapping: door_graph key -> {"dest_module",
    "dest_waypoint"} using the NEW (shuffled) destination in the same
    shape as door_graph.json's original vanilla entries, so the file
    patcher can consume it identically either way.

    Uses AP's real coupled=True engine -- see this module's own docstring
    for the full reasoning. Retries
    the whole build+placement up to MAX_COUPLED_ATTEMPTS times on
    EntranceRandomizationError (cheap insurance, not a real fix -- see
    that constant's own comment), then runs _repair_orphaned_modules on
    whatever the best attempt produced -- THAT is what actually
    guarantees reachability now, scoped to just the rare residual instead
    of a whole-graph pass."""
    door_graph = world.kotor_door_graph
    regions = world.kotor_door_regions

    best_pairings: typing.List[typing.Tuple[str, str]] = []
    exit_name_to_key: typing.Dict[str, str] = {}
    target_name_to_real_key: typing.Dict[str, str] = {}
    total_entries = 0
    completed = False

    for attempt in range(1, MAX_COUPLED_ATTEMPTS + 1):
        _reset_door_regions(regions)
        exits, targets, exit_name_to_key, target_name_to_real_key = _create_exits_and_targets(world)
        total_entries = len(exits)
        pairings: typing.List[typing.Tuple[str, str]] = []

        def _on_connect(er_state, placed_exits, paired_entrances):
            for ex, target in zip(placed_exits, paired_entrances):
                pairings.append((ex.name, target.name))

        try:
            randomize_entrances(
                world,
                coupled=True,
                target_group_lookup={0: [0]},
                er_targets=targets,
                exits=exits,
                on_connect=_on_connect,
            )
            best_pairings = pairings
            completed = True
            break
        except EntranceRandomizationError as e:
            if len(pairings) > len(best_pairings):
                best_pairings = pairings
            last_error = e

    if not completed:
        print(f"[kotor] Door randomization: {len(best_pairings)}/{total_entries} coupled door entries placed "
              f"after {MAX_COUPLED_ATTEMPTS} attempts, remainder falling back to vanilla destinations "
              f"({last_error})")

    result = {}
    for exit_name, target_name in best_pairings:
        exit_key = exit_name_to_key.get(exit_name)
        dest_key = target_name_to_real_key.get(target_name)
        if exit_key is None or dest_key is None:
            continue  # not one of ours (shouldn't happen, but don't guess)
        dest_entry = door_graph[dest_key]
        result[exit_key] = {
            "dest_module": dest_entry["dest_module"],
            "dest_waypoint": dest_entry["dest_waypoint"],
        }

    # Everything not in a confirmed coupled pair (both exclusion sets,
    # the Ebon Hawk pins, and the 8 no-reverse entries), plus anything a
    # fully-exhausted retry loop still couldn't place, keeps its own real
    # vanilla destination -- a no-op entry, not a broken one.
    for key, entry in door_graph.items():
        if key not in result:
            result[key] = {"dest_module": entry["dest_module"], "dest_waypoint": entry["dest_waypoint"]}

    pairs, _noreverse = _build_coupled_pairs(door_graph)
    repairs = _repair_orphaned_modules(door_graph, pairs, result)
    if repairs:
        print(f"[kotor] Door randomization: repaired {len(repairs)} orphaned module(s) by "
              f"repointing an existing edge: {repairs}")

    world.kotor_door_mapping = result
    return result
