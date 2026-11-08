"""Lists the plot-flagged items a play-through logged (the client's items_seen.csv, written when ap_item_log=1 is set in the extender's config.txt),
so the quest-item list can be chosen from what the player actually met.

For each item: where and when it first appeared, whether it is still held (an item that vanished was consumed, handed over or destroyed), and whether the
current draft list (data/quest_items.json) already has it. Items are listed in the order met, which is the story order of the run.

  python tools/item_log_report.py [path to items_seen.csv]
"""
import csv
import json
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DEFAULT = os.path.join(os.environ.get("LOCALAPPDATA", "."), "K2SE", "ap", "items_seen.csv")


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    try:
        with open(path, newline="", encoding="utf-8") as f:
            rows = sorted(csv.DictReader(f), key=lambda r: r["first_time"])
    except OSError:
        print("No item log at %s. Put ap_item_log=1 on its own line in %%LOCALAPPDATA%%\\K2SE\\config.txt, play with the client connected, then run this." % path)
        return 1
    try:
        with open(os.path.join(ROOT, "data", "quest_items.json"), encoding="utf-8") as f:
            draft = {c["tag"].lower(): c["verdict"] for c in json.load(f)["items"]}
    except OSError:
        draft = {}
    print("%d plot items met. 'kept' = still held at the last report; 'gone' = it left the inventory (where). 'draft' = in the current list.\n" % len(rows))
    print("%-3s %-24s %-34s %-8s %-6s %s" % ("#", "tag", "name", "first at", "state", "draft"))
    for i, r in enumerate(rows, 1):
        state = "kept" if r["held"] == "1" else "gone@" + (r["lost_module"] or "?")
        print("%-3d %-24s %-34s %-8s %-6s %s" % (i, r["tag"][:24], r["name"][:34], r["first_module"], state, draft.get(r["tag"].lower(), "-")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
