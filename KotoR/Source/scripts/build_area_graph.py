"""
Builds a static area-connectivity graph: for each of the 78 covered areas,
which OTHER covered areas are directly reachable via a transition trigger
or door. Source of truth is the game's own transition data (GIT TriggerList
/DoorList entries with a LinkedToModule set), not observed play -- gives
complete coverage from the start instead of only learning edges after
someone has actually walked them (a real gap for a hub with unused exits).

Output: extender/area_trampolines/_graph.json, {base: [neighbor_base, ...]}.
Only edges where BOTH ends are one of our 78 covered areas are kept --
neighbors that land in an uncovered/excluded module (e.g. a STUNT_* cutscene
or an excluded duplicate) are dropped, since there's nothing to arm there.
"""
import json
import os
from pykotor.resource.formats.rim import read_rim
from pykotor.resource.type import ResourceType
from pykotor.resource.formats.gff import read_gff

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
TRAMPOLINE_SRC_DIR = os.path.join(REPO_ROOT, "extender", "area_trampolines")

with open(os.path.join(TRAMPOLINE_SRC_DIR, "_mapping.json")) as f:
    mapping = json.load(f)
covered_bases = set(mapping.keys())


def get_git_data(base):
    r = read_rim(rf"{GAME_DIR}\modules\{base}.rim")
    for res in r:
        if res.restype == ResourceType.GIT:
            return res.data
    return None


def linked_modules_from_list(gff_root, list_name):
    """Pull every non-empty LinkedToModule from a GIT struct list (triggers
    or doors), tolerating the field being absent on a given instance."""
    modules = []
    if not gff_root.exists(list_name):
        return modules
    lst = gff_root.get_list(list_name)
    for i in range(len(lst)):
        struct = lst.at(i)
        if struct.exists("LinkedToModule"):
            dest = str(struct.get_resref("LinkedToModule"))
            if dest:
                modules.append(dest.lower())
    return modules


graph = {}
missing_git = []
for base in sorted(covered_bases):
    git_data = get_git_data(base)
    if git_data is None:
        missing_git.append(base)
        graph[base] = []
        continue
    gff = read_gff(git_data)
    dests = set()
    dests.update(linked_modules_from_list(gff.root, "TriggerList"))
    dests.update(linked_modules_from_list(gff.root, "Door List"))

    neighbors = sorted({d for d in dests if d in covered_bases and d != base})
    graph[base] = neighbors

if missing_git:
    print(f"WARNING: no GIT found for: {missing_git}")

total_edges = sum(len(v) for v in graph.values())
isolated = [b for b, v in graph.items() if not v]
print(f"{len(graph)} areas, {total_edges} directed edges, {len(isolated)} areas with zero covered neighbors")
if isolated:
    print(f"isolated (no covered neighbor found): {isolated}")

out_path = os.path.join(TRAMPOLINE_SRC_DIR, "_graph.json")
with open(out_path, "w") as f:
    json.dump(graph, f, indent=2, sort_keys=True)
print(f"Wrote {out_path}")
