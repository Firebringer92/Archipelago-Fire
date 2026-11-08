"""Builds the candidate list for the quest-item checks (data/quest_items.json and docs/QUEST_ITEM_CANDIDATES.md) from the item research.

A quest-item check fires the first time the player holds a listed item (the game reports the tags it finds by possession). The list comes from the
quest-protected item templates of research/items/item_review.csv: a plot flag, or an item a dialogue or script checks, in a category the player can
hold. Each candidate gets a verdict and a reason; the user vetoes by editing the EXCLUDE / FORCE_INCLUDE tables below (or the json) and rerunning.

Rules for "in": the item exists in the install (placed somewhere or given by a script), it has a player-facing name, it is not a crafting part, a
lightsaber part, a consumable or a spike, it is not destroyed in the same step that creates it, and it is not a shared base item (a common weapon, a
pazaak card) that the player may already own.

  python tools/build_quest_items.py
"""
import csv
import json
import os
from collections import Counter, defaultdict

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

CATEGORIES = {"datapad", "aesthetic item", "plot item", "arm gear", "droid equipment", "weapon", "armor", "robe", "creature item", "pazaak"}
# tag -> reason for leaving it out (the user's veto list goes here too)
EXCLUDE = {
    "brokenitem": "junk the game puts in bashed containers; not a quest item",
    "pl_fakeholocron": "a prop given and taken inside one conversation",
    "g_i_pazdeck": "the pazaak tutorial deck; given for free at the start of Telos",
    "w_melee_01": "a common sword used as a prop by two fights; the player may already own one",
    "w_melee_17": "a common blade; the player may already own one",
    "w_melee_x02": "a prop weapon of the Twi'lek fight",
    "w_melee_x03": "a prop weapon of the Twi'lek fight",
    "g_w_vbroswrd002": "destroyed in the same script that creates it (the duel forfeit)",
    "a_shield_01": "an ordinary shield that Bao-Dur's dialogue checks; the player may buy or find one",
    "mine_datapad001": "lies in loot containers across several modules (not a quest chain)",
    "mine_datapad002": "lies in loot containers across several modules (not a quest chain)",
    "a_band_x01": "sold by a vendor script; not a quest reward",
    "a_light_x08": "sold by a vendor script; not a quest reward",
    "100_fore01": "an ordinary mining shield from a loot container",
}
FORCE_INCLUDE = {}
LATE = {"nihilusmask": "after the Ravager: the goal ends the run first"}


def planet_requires():
    """module -> the requirement string of the quests in it (the least restrictive one)."""
    best = {}
    with open(os.path.join(ROOT, "data", "location_gate_requirements.csv"), newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            for m in [x.strip() for x in r["modules"].replace(",", ";").split(";") if x.strip()]:
                cur = best.get(m)
                if cur is None or len(r["requires"].split()) < len(cur.split()):
                    best[m] = r["requires"]
    return best


def main():
    with open(os.path.join(ROOT, "research", "items", "item_review.csv"), newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    with open(os.path.join(ROOT, "research", "items", "tsl_items.json"), encoding="utf-8") as f:
        items = json.load(f)
    by_module = planet_requires()
    out = []
    for r in rows:
        if not (r["quest_dependent"] == "True" or r["plot_flag"] == "True") or r["category"] not in CATEGORIES:
            continue
        info = items.get(r["resref"], {})
        tag = (info.get("tag") or r["resref"]).strip()
        modules = [m for m in r["modules"].split(";") if m]
        evidence = r["evidence"]
        why = None
        if r["resref"] in FORCE_INCLUDE:
            why = None
        elif r["resref"] in EXCLUDE:
            why = EXCLUDE[r["resref"]]
        elif not modules:
            why = "not placed in any module (a placeholder)"
        elif r["category"] in ("pazaak", "creature item"):
            why = "a %s, not a quest item" % r["category"]
        elif "[destroys]" in evidence and "script_create" in evidence and "script_check" in evidence and "dialogue_check" not in evidence and r["plot_flag"] != "True":
            why = "destroyed by the script that checks it"
        elif r["review_group"].startswith("template never referenced"):
            why = "never referenced by an area, store, script or dialogue (may be cut)"
        elif r["resref"] in LATE:
            why = LATE[r["resref"]]
        verdict = "out" if why else "in"
        requires = ""
        reqs = [by_module[m] for m in modules if m in by_module]
        if reqs:
            requires = min(reqs, key=lambda s: len(s.split()))
        out.append({"tag": tag, "resref": r["resref"], "name": " ".join(r["name"].replace("<", "").replace(">", "").split()), "category": r["category"],
                    "modules": modules, "requires": requires, "known_requirement": bool(reqs), "verdict": verdict, "reason": why or "",
                    "consumed_somewhere": "[destroys]" in evidence, "source": [e for e in evidence.split(" | ") if e.startswith(
                        ("script_create", "dialogue_give", "source:", "key_for"))][:3]})
    out.sort(key=lambda c: (c["verdict"] != "in", c["category"], c["tag"]))
    tags = Counter(c["tag"].lower() for c in out)
    assert all(n == 1 for n in tags.values()), [t for t, n in tags.items() if n > 1]
    with open(os.path.join(ROOT, "data", "quest_items.json"), "w", encoding="utf-8") as f:
        json.dump({"_doc": "Candidates for the quest-item checks, made by tools/build_quest_items.py. verdict 'in' becomes a location; edit EXCLUDE/FORCE_INCLUDE in the "
                           "tool to change it. requires is the least restrictive requirement of the quests in the item's modules ('' = no story gate known).",
                   "items": out}, f, indent=1)
    ins = [c for c in out if c["verdict"] == "in"]
    outs = [c for c in out if c["verdict"] == "out"]
    lines = ["# Quest-item check candidates (for the user to veto)", "",
             "Generated by `tools/build_quest_items.py` from the item research. **%d proposed, %d left out.** A check fires the first time you hold the item "
             "(the game reports items by their tag). To veto: tell me the tags, or move one between the lists." % (len(ins), len(outs)), "",
             "`Needs` is the story requirement of the quests in the item's modules (blank = no known requirement, so it can hold only filler). "
             "`Consumed` marks items a script destroys somewhere: the check still fires when you hold it, but an item given and taken in one step can be missed.", "",
             "## Proposed (%d)" % len(ins), "", "| Tag | Name | Kind | Modules | Needs | Consumed |", "|---|---|---|---|---|---|"]
    for c in ins:
        lines.append("| `%s` | %s | %s | %s | %s | %s |" % (c["tag"], c["name"], c["category"], ", ".join(c["modules"][:4]) + ("..." if len(c["modules"]) > 4 else ""),
                                                       c["requires"] or "-", "yes" if c["consumed_somewhere"] else ""))
    lines += ["", "## Left out (%d)" % len(outs), "", "| Tag | Name | Why |", "|---|---|---|"]
    for c in outs:
        lines.append("| `%s` | %s | %s |" % (c["tag"], c["name"] or "(no name)", c["reason"]))
    with open(os.path.join(ROOT, "docs", "QUEST_ITEM_CANDIDATES.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    print("%d candidates: %d in, %d out" % (len(out), len(ins), len(outs)))


if __name__ == "__main__":
    main()
