"""
Fixes a real gameplay bug found 2026-08-29: 142 of the 577 items in
gear_items.json's shop_randomize pool have a genuine in-game UTI Cost of
0 (confirmed against the real UTI templates, not gear_items.json's own
"cost" field, which is separately confirmed dead/unused -- see PHASE13.md).
A 0-cost item bought from a shop costs the player 0 credits, meaning
patch_item_suppression.py's purchase-detection check (GetGold() dropping
since the last check) never fires -- the freshly-bought item would get
wrongly suppressed/bonus-ified/replaced immediately after a "free"
purchase, exactly the failure mode the purchase check exists to prevent.

Fix: for every zero-cost shop_randomize item, write a copy of its UTI
template into Override/ with Cost set to DEFAULT_MIN_COST -- this doesn't
touch any existing base game file (all 142 currently live read-only in
templates.bif), so it's purely additive and trivially reversible (delete
the generated Override/<resref>.uti files to revert to the vanilla
0-cost original).

Usage:
  python patch_shop_item_costs.py                          -- apply
  python patch_shop_item_costs.py --game-dir "D:\...\swkotor" -- non-default install
"""
import json
import os
import sys

from pykotor.extract.installation import Installation
from pykotor.resource.formats.gff import read_gff, write_gff
from pykotor.resource.type import ResourceType

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
GEAR_JSON = os.path.join(REPO_ROOT, "Archipelago", "worlds", "kotor", "gear_items.json")
DEFAULT_MIN_COST = 500


def _arg_value(flag, default):
    for i, a in enumerate(sys.argv):
        if a == flag and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
        if a.startswith(flag + "="):
            return a.split("=", 1)[1]
    return default


GAME_DIR = _arg_value("--game-dir", DEFAULT_GAME_DIR)
OVERRIDE = os.path.join(GAME_DIR, "Override")


def main():
    with open(GEAR_JSON, encoding="utf-8") as f:
        gear = json.load(f)
    shop_resrefs = sorted(r for r, v in gear.items() if v.get("shop_randomize"))

    installation = Installation(GAME_DIR)
    fixed = 0
    already_nonzero = 0
    not_found = 0
    for resref in shop_resrefs:
        res = installation.resource(resref, ResourceType.UTI)
        if res is None:
            print(f"  {resref}: UTI not found, skipping")
            not_found += 1
            continue
        gff = read_gff(res.data)
        if not gff.root.exists("Cost"):
            print(f"  {resref}: no Cost field at all, skipping")
            continue
        cost = gff.root._fields["Cost"]._value
        if cost != 0:
            already_nonzero += 1
            continue

        gff.root.set_uint32("Cost", DEFAULT_MIN_COST)
        new_data = bytearray()
        write_gff(gff, new_data)
        out_path = os.path.join(OVERRIDE, f"{resref}.uti")
        with open(out_path, "wb") as f:
            f.write(bytes(new_data))
        print(f"  {resref}: Cost 0 -> {DEFAULT_MIN_COST}, deployed -> {out_path}")
        fixed += 1

    print(f"\nDone. Fixed {fixed} zero-cost items, {already_nonzero} already had a "
          f"real cost, {not_found} not found.")


if __name__ == "__main__":
    main()
