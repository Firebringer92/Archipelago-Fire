r"""
Human-readable review report for the door/area randomizer (Options.py's
AreaRandomizer) -- lets the user personally judge whether a seed's door
shuffle is correct using their own gameplay knowledge, without booting the
game and manually walking all 156 transitions.

Three sources are compared side by side for every entry in door_graph.json:
  1. vanilla   -- the real, unshuffled destination (door_graph.json itself).
  2. generated -- what EntranceRando.py's connect_entrances() decided for
                  the CONNECTED seed (read from the same _slot_data.json
                  patch_door_randomizer.py consumes). Falls back to vanilla
                  for every entry if area_randomizer was off, or nothing
                  has connected yet.
  3. live      -- what's ACTUALLY sitting in the installed game's own
                  module GIT files right now, read directly off disk
                  (read-only, never written). Comparing this against
                  "generated" is what actually answers "did the patch step
                  apply, and is it stale from a different seed" -- the same
                  class of question this project's own staleness bugs this
                  session came from, applied to doors instead of abilities.

Every entry is also labeled with WHY it is or isn't randomizable, mirroring
EntranceRando.py's own classification (excluded story-critical zones,
Ebon Hawk boarding pins, no-reverse-door fixed entries, multi-door pairs
resolved via waypoint suffix, repaired-orphan entries) rather than dumping
one undifferentiated list. The classification logic
below is a deliberate READ-ONLY duplicate of EntranceRando.py's pure
functions (not an import): that module's own top-level imports
(BaseClasses, entrance_rando) require the full Archipelago core on
sys.path, which this standalone script has no reason to depend on just to
re-derive door_graph.json category membership. Keep the two in sync by
hand if EntranceRando.py's exclusion sets or pairing rules ever change.

Usage:
  python review_door_mapping.py                              -- write + print report
  python review_door_mapping.py --game-dir "D:\...\swkotor"   -- against a non-default install
  python review_door_mapping.py --out "C:\...\report.txt"     -- custom report path
  python review_door_mapping.py --slot-data "C:\...\dump.json" -- review a test
      generation's own dump (see EntranceRando.py's KOTOR_DEBUG_DOOR_DUMP)
      instead of the real, live-connected seed's _slot_data.json
"""
import json
import os
import sys

from pykotor.extract.installation import Installation
from pykotor.resource.formats.rim import read_rim
from pykotor.resource.formats.gff import read_gff
from pykotor.resource.type import ResourceType

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
DOOR_GRAPH_PATH = os.path.join(REPO_ROOT, "Archipelago", "worlds", "kotor", "door_graph.json")
# Same path patch_door_randomizer.py reads -- see its own copy of this
# constant's comment for the full reasoning.
SLOT_DATA_PATH = os.path.join(REPO_ROOT, "extender", "area_trampolines", "_slot_data.json")
DEFAULT_OUT_PATH = os.path.join(REPO_ROOT, "door_mapping_review.txt")


def _arg_value(flag, default):
    for i, a in enumerate(sys.argv):
        if a == flag and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
        if a.startswith(flag + "="):
            return a.split("=", 1)[1]
    return default


GAME_DIR = _arg_value("--game-dir", DEFAULT_GAME_DIR)
MOD_DIR = os.path.join(GAME_DIR, "modules")
OUT_PATH = _arg_value("--out", DEFAULT_OUT_PATH)
# Override for reviewing a test generation's own dump (see EntranceRando.py's
# KOTOR_DEBUG_DOOR_DUMP hook) instead of the real, live-connected seed's
# slot data -- avoids overwriting SLOT_DATA_PATH with throwaway test data
# just to look at it.
SLOT_DATA_OVERRIDE = _arg_value("--slot-data", None)

# ---------------------------------------------------------------------------
# Classification -- deliberate duplicate of EntranceRando.py's own pure
# exclusion/pairing logic (see module docstring for why this isn't imported).
# ---------------------------------------------------------------------------

EXCLUDED_BOTH_WAYS_PREFIXES = ("end_m", "unk_m", "sta_m", "lev_m")
EXCLUDED_SOURCE_ONLY = {"tar_m02af"}
EBON_HAWK_ENTRY_KEYS = {
    "danm13:TriggerList:2",
    "kas_m22aa:TriggerList:9",
    "korr_m33aa:TriggerList:9",
    "liv_m99aa:Door List:1",
    "manm26ad:TriggerList:0",
    "tat_m17ab:TriggerList:2",
}


def _is_excluded_both_ways(module: str) -> bool:
    return module.startswith(EXCLUDED_BOTH_WAYS_PREFIXES)


def _resolve_by_waypoint_suffix(door_graph, keys_ab, keys_ba):
    if len(keys_ab) != len(keys_ba):
        return None
    by_suffix_ab = {}
    for k in keys_ab:
        by_suffix_ab.setdefault(door_graph[k]["dest_waypoint"][-1:], []).append(k)
    by_suffix_ba = {}
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


def classify_all(door_graph: dict) -> dict:
    """Returns {key: category_label} for every door_graph entry. Any key
    left uncategorized by the loops below (should not happen -- a built-in
    self-check, not an expected case) is caught by the final pass and
    surfaced loudly rather than silently omitted from the report."""
    categories = {}
    eligible = {}
    for key, entry in door_graph.items():
        module, dest_module = entry["module"], entry["dest_module"]
        if _is_excluded_both_ways(module):
            categories[key] = "excluded (story-critical source)"
        elif module in EXCLUDED_SOURCE_ONLY:
            categories[key] = "excluded (source-only)"
        elif _is_excluded_both_ways(dest_module):
            categories[key] = "excluded (story-critical dest)"
        elif key in EBON_HAWK_ENTRY_KEYS:
            categories[key] = "ebon hawk pin"
        else:
            eligible[key] = entry

    fwd = {}
    for key, entry in eligible.items():
        fwd.setdefault((entry["module"], entry["dest_module"]), []).append(key)

    visited = set()
    for (a, b), keys_ab in sorted(fwd.items()):
        if a == b or (a, b) in visited or (b, a) in visited:
            continue
        visited.add((a, b))
        visited.add((b, a))
        keys_ba = fwd.get((b, a))
        if not keys_ba:
            for k in keys_ab:
                categories[k] = "no-reverse (fixed)"
            continue
        if len(keys_ab) == 1 and len(keys_ba) == 1:
            categories[keys_ab[0]] = "coupled"
            categories[keys_ba[0]] = "coupled"
        else:
            resolved = _resolve_by_waypoint_suffix(door_graph, keys_ab, keys_ba)
            if resolved is not None:
                for kf, kb in resolved:
                    categories[kf] = "coupled (multi-door)"
                    categories[kb] = "coupled (multi-door)"
            else:
                for k in keys_ab + keys_ba:
                    categories[k] = "no-reverse (fixed, ambiguous multi-door)"

    for key in door_graph:
        categories.setdefault(key, "UNCLASSIFIED -- review tool bug, please report")
    return categories


# ---------------------------------------------------------------------------
# Live GIT reads (read-only -- never writes anything back)
# ---------------------------------------------------------------------------

def _read_live_destinations(door_graph: dict) -> dict:
    """Returns {key: (dest_module, dest_waypoint) or None} read straight off
    the installed game's own module RIMs. None means the RIM/GIT/entry
    couldn't be read at all (module not installed, corrupt, etc.) -- the
    report shows this as its own state, never silently as a match."""
    by_module = {}
    for key, entry in door_graph.items():
        by_module.setdefault(entry["module"], []).append((key, entry["list"], entry["index"]))

    live = {}
    for module, rows in sorted(by_module.items()):
        path = os.path.join(MOD_DIR, f"{module}.rim")
        if not os.path.exists(path):
            for key, _list_name, _index in rows:
                live[key] = None
            continue
        try:
            r = read_rim(path)
            git_res = next((res for res in r if res.restype == ResourceType.GIT), None)
            if git_res is None:
                raise ValueError("no GIT resource")
            gff = read_gff(git_res.data)
        except Exception:
            for key, _list_name, _index in rows:
                live[key] = None
            continue

        for key, list_name, index in rows:
            try:
                lst = gff.root.get_list(list_name)
                inst = lst.at(index)
                dest_module = inst.get_resref("LinkedToModule").get() if inst.exists("LinkedToModule") else ""
                dest_waypoint = inst.get_string("LinkedTo") if inst.exists("LinkedTo") else ""
                live[key] = (dest_module, dest_waypoint)
            except Exception:
                live[key] = None
    return live


def _connected_slot_data() -> dict:
    path = SLOT_DATA_OVERRIDE or SLOT_DATA_PATH
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"  (couldn't read {path}: {e})")
        return {}


CATEGORY_ORDER = [
    "excluded (story-critical source)",
    "excluded (story-critical dest)",
    "excluded (source-only)",
    "ebon hawk pin",
    "no-reverse (fixed)",
    "no-reverse (fixed, ambiguous multi-door)",
    "coupled (multi-door)",
    "coupled",
    "UNCLASSIFIED -- review tool bug, please report",
]


def main():
    with open(DOOR_GRAPH_PATH, encoding="utf-8") as f:
        door_graph = json.load(f)

    slot_data = _connected_slot_data()
    seed_name = slot_data.get("seed_name")
    # Raw AreaRandomizer value (0=off/1=coupled/2=decoupled) -- matches
    # Options.py's own option_off/option_coupled/option_decoupled values.
    area_randomizer_value = slot_data.get("area_randomizer", 0)
    area_randomizer_label = {0: "off", 1: "coupled", 2: "decoupled"}.get(area_randomizer_value, area_randomizer_value)
    generated_mapping = slot_data.get("door_mapping") or {}
    repaired_keys = set(slot_data.get("door_mapping_repairs") or [])

    if not generated_mapping:
        print("No connected seed's door_mapping available (area_randomizer was off, or "
              "you haven't connected with KotorClient.py yet) -- 'generated' will show each "
              "entry's own vanilla destination. This is still useful: it lets you confirm "
              "nothing from a PREVIOUS seed's patch is still sitting live on disk.")

    categories = classify_all(door_graph)
    print("Reading live GIT data from the installed game (read-only)...")
    live = _read_live_destinations(door_graph)

    print("Resolving module display names via the installation's own talktable...")
    installation = Installation(GAME_DIR)
    name_cache = {}

    def display(module: str) -> str:
        if module not in name_cache:
            try:
                name_cache[module] = installation.module_name(module) or module
            except Exception:
                name_cache[module] = module
        return f"{module} ({name_cache[module]})" if name_cache[module] != module else module

    lines = []
    lines.append("KOTOR AP Door Randomizer -- review report")
    lines.append(f"seed: {seed_name!r}   area_randomizer: {area_randomizer_label}   "
                  f"entries: {len(door_graph)}   repaired: {len(repaired_keys)}")
    if area_randomizer_value == 2:
        lines.append("NOTE: this seed used DECOUPLED mode -- the category labels below (coupled/"
                      "multi-door/no-reverse) describe which doors are PART OF the same pool used by "
                      "coupled mode, not a round-trip guarantee for this seed. In decoupled mode, "
                      "'generated' for one side of a pair tells you nothing about the other side.")
    lines.append("")

    mismatch_count = 0
    unreadable_count = 0
    by_category = {}
    for key, entry in door_graph.items():
        by_category.setdefault(categories[key], []).append(key)

    for category in CATEGORY_ORDER:
        keys = by_category.get(category)
        if not keys:
            continue
        lines.append(f"=== {category} ({len(keys)}) ===")
        for key in sorted(keys):
            entry = door_graph[key]
            vanilla_dest = (entry["dest_module"], entry["dest_waypoint"])
            gen = generated_mapping.get(key)
            generated_dest = (gen["dest_module"], gen["dest_waypoint"]) if gen else vanilla_dest
            live_dest = live.get(key)
            repaired_tag = " [REPAIRED]" if key in repaired_keys else ""

            lines.append(f"  {key} ({entry['kind']}, tag={entry['tag']}) "
                         f"-- {display(entry['module'])}{repaired_tag}")
            lines.append(f"      vanilla:   {display(vanilla_dest[0])} @ {vanilla_dest[1]}")
            lines.append(f"      generated: {display(generated_dest[0])} @ {generated_dest[1]}")
            if live_dest is None:
                lines.append("      live:      UNREADABLE (module/GIT/entry not found on disk)")
                unreadable_count += 1
            else:
                status = "" if (live_dest[0].lower() == generated_dest[0].lower()
                                 and live_dest[1] == generated_dest[1]) else "   <-- MISMATCH"
                if status:
                    mismatch_count += 1
                lines.append(f"      live:      {display(live_dest[0])} @ {live_dest[1]}{status}")
        lines.append("")

    lines.append(f"Summary: {mismatch_count} mismatch(es) between generated and live, "
                 f"{unreadable_count} unreadable entr(y/ies).")
    if mismatch_count:
        lines.append("A mismatch means the live game file does NOT match what this seed's "
                     "door_mapping says it should be -- either patch_door_randomizer.py hasn't "
                     "been run yet for this connection, or the on-disk data is stale from a "
                     "different seed/options combination.")

    report = "\n".join(lines)
    print(report)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\nWrote report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
