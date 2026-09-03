"""
Scans every module's GIT for door/trigger transition points (LinkedToModule
set) and builds the raw door graph: for each transition object, its own tag,
which module it lives in, and its vanilla (destination module, destination
waypoint tag). This is the source data the kotor apworld's entrance
randomization reads to build its Region/Entrance graph, and what
patch_door_randomizer.py later uses to know which GIT struct to rewrite for
a given door.

Confirmed via prior research: 156 transition points (116 doors + 40
triggers) game-wide, each carrying LinkedToModule/LinkedTo/LinkedToFlags as
plain instance fields -- no script involved for the vast majority.

Output: Archipelago/worlds/kotor/door_graph.json by default (alongside
gear_items.json -- this is world-generation reference data the apworld
reads at generate time, not a live-trampoline runtime file, so it lives
with the other apworld data rather than under extender/area_trampolines/).
Pass --worlds-dir=<path> to target a different worlds/kotor checkout (e.g.
a trimmed source export that doesn't have a full Archipelago/ folder
alongside it) instead of editing OUT_PATH by hand.
  { "<module>:<list>:<index>": {"module": <module the door lives in>,
               "list": "Door List"|"TriggerList", "index": <list index>,
               "tag": <the door/trigger's own Tag -- NOT reliably unique,
                       kept for reference/patching only>,
               "kind": "door"|"trigger",
               "dest_module": <vanilla destination>,
               "dest_waypoint": <vanilla destination waypoint tag>} }
"""
import json
import os
import sys
from pykotor.resource.formats.rim import read_rim
from pykotor.resource.formats.gff import read_gff
from pykotor.resource.type import ResourceType

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
MOD_DIR = os.path.join(GAME_DIR, "modules")
WORLDS_DIR = os.path.join(REPO_ROOT, "Archipelago", "worlds", "kotor")
OUT_PATH = os.path.join(WORLDS_DIR, "door_graph.json")


def get_git_gff(base):
    r = read_rim(os.path.join(MOD_DIR, f"{base}.rim"))
    for res in r:
        if res.restype == ResourceType.GIT:
            return read_gff(res.data)
    return None


def main():
    global OUT_PATH
    for a in sys.argv[1:]:
        if a.startswith("--worlds-dir="):
            OUT_PATH = os.path.join(a.split("=", 1)[1], "door_graph.json")

    rim_files = sorted(
        f[:-4] for f in os.listdir(MOD_DIR)
        if f.lower().endswith(".rim") and not f.lower().endswith("_s.rim")
    )

    graph = {}
    for base in rim_files:
        try:
            git = get_git_gff(base)
        except Exception as e:
            print(f"  {base}: could not read GIT ({e}), skipping")
            continue
        if git is None:
            continue

        for list_name, kind in (("Door List", "door"), ("TriggerList", "trigger")):
            lst = git.root.get_list(list_name) if git.root.exists(list_name) else None
            if lst is None:
                continue
            for i in range(len(lst)):
                inst = lst.at(i)
                linked_module = inst.get_resref("LinkedToModule").get() if inst.exists("LinkedToModule") else ""
                if not linked_module:
                    continue
                tag = inst.get_string("Tag") if inst.exists("Tag") else ""
                linked_to = inst.get_string("LinkedTo") if inst.exists("LinkedTo") else ""
                if not tag:
                    continue
                # Tags aren't reliably unique even within one module's own
                # list (confirmed: "KashyyykDoor1" appears twice in the
                # same kas_m23aa list), let alone globally (20 confirmed
                # cross-module collisions, e.g. "KashyyykDoor2" used
                # identically in 3 different modules) -- key on
                # module+list+index, which is unique by construction, and
                # keep tag/index as data so the patcher can address this
                # exact GIT struct directly rather than searching by tag.
                key = f"{base}:{list_name}:{i}"
                graph[key] = {
                    "module": base,
                    "list": list_name,
                    "index": i,
                    "tag": tag,
                    "kind": kind,
                    "dest_module": linked_module,
                    "dest_waypoint": linked_to,
                }

    with open(OUT_PATH, "w") as f:
        json.dump(graph, f, indent=2, sort_keys=True)

    doors = sum(1 for v in graph.values() if v["kind"] == "door")
    triggers = sum(1 for v in graph.values() if v["kind"] == "trigger")
    print(f"Wrote {OUT_PATH}: {len(graph)} transitions ({doors} doors, {triggers} triggers)")


if __name__ == "__main__":
    main()
