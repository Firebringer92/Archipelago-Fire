"""Builds the shop randomizer's two data tables from the research output (research/vendors/stores.json, research/items/tsl_items.json).

  data/shops.json       the placed stores: module, store template resref, tag, planet and whether the randomizer leaves it alone; the stock scripts the randomizer silences
  data/shop_pool.json   the item resrefs a randomized shop may stock, and the staples every randomized shop carries besides

Only identifiers are written (resrefs, tags, module names): no names, descriptions or other game text. Re-run after the research is refreshed:
  python tools/build_shop_data.py
"""
import json
import os

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# The Pazaak dealers keep their card stock: the Pazaak minigame and its side quests need the cards, and they are not shops in the loot sense.
LEAVE_ALONE_TAGS = {"m_207_001", "DahniStore", "patostore"}

# Medpacs, droid repair kits and the two spike kinds are not in the random pool (the research marks them as quest-referenced), but a randomized shop without them would
# leave a seed with no way to buy healing, so every randomized shop carries these besides its random items.
STAPLES = ["g_i_medeqpmnt01", "g_i_medeqpmnt02", "g_i_medeqpmnt03", "g_i_drdrepeqp001", "g_i_drdrepeqp002", "g_i_drdrepeqp003", "g_i_progspike01", "g_i_secspike01"]


def main() -> int:
    with open(os.path.join(ROOT, "research", "vendors", "stores.json"), encoding="utf-8") as f:
        stores = json.load(f)["stores"]
    with open(os.path.join(ROOT, "research", "items", "tsl_items.json"), encoding="utf-8") as f:
        items = json.load(f)
    placed = [s for s in stores if s["placed_in_git"]]
    planets = []
    rows = []
    for s in placed:
        if s["planet"] not in planets:
            planets.append(s["planet"])
        rows.append({"module": s["module"], "utm": s["utm_resref"], "tag": s["tag"], "planet": s["planet"], "leave_alone": s["tag"] in LEAVE_ALONE_TAGS})
    scripts = sorted({name for s in stores for name in (s.get("stock_scripts") or [])})
    # Scripts the research does not tie to a placed store but that exist in the module archives and stock a store on talking (Geeda's, and Akkere's, whose script
    # names a store tag that is not the placed one): found by scanning every module archive for compiled scripts named a_stock*; 16 in all.
    scripts = sorted(set(scripts) | {"a_stock_geeda", "a_stock_geedaond", "a_stock_akkere"})
    pool = sorted(r for r, d in items.items() if d["shop_randomize"] and not d["plot_flag"] and d["cost"] > 0 and not d["quest_dependent"])
    staples = [r for r in STAPLES if r in items]
    with open(os.path.join(ROOT, "data", "shops.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump({"planets": planets, "stores": rows, "stock_scripts": scripts}, f, indent=1)
        f.write("\n")
    with open(os.path.join(ROOT, "data", "shop_pool.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump({"pool": pool, "staples": staples}, f, indent=1)
        f.write("\n")
    print("%d stores (%d left alone), %d planets, %d stock scripts, pool %d, staples %d" %
          (len(rows), sum(1 for r in rows if r["leave_alone"]), len(planets), len(scripts), len(pool), len(staples)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
