"""
The 32-slot party selection screen's layout file (Override\\partyselection.gui), built from the player's own copy of the game's partyselection.gui.

The paged party screen (extender/src_k1se/party32_gui.inc) binds sixteen portrait records by tag (BTN_NPC0-15, LBL_CHAR0-15, LBL_NA0-15) and two page buttons
(BTN_PAGE_PREV, BTN_PAGE_NEXT); the stock layout only has nine slots. The layout this builds is the game's file with the nine slots moved into a grid of four columns and
the extra controls added, as in the Patch Manager mod PartyRosterLimit32K1 (MIT, Vriff and Patch Manager contributors, see PATCH_MANAGER_LICENSE.txt), whose layout the
recipe was worked out from.

Nothing of the game's is shipped: party_layout.json holds only numbers (positions, ids, links between controls) and the names of stock controls to copy. build() reads
the game's file, copies controls from it and applies the numbers. It is called by build_game_assets.py like the other categories.

  python party_layout.py --make-recipe <upstream .gui> [--game-dir DIR]     (development only) regenerates party_layout.json from the upstream layout
  python party_layout.py --check <upstream .gui> [--game-dir DIR]           (development only) proves build() reproduces the upstream layout control by control
"""
import argparse
import copy
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECIPE_PATH = os.path.join(REPO_ROOT, "scripts", "party_layout.json")
DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
LAYOUT_NAME = "partyselection.gui"
# Needles LayoutReady() in the extender looks for in the installed file.
REQUIRED_TAGS = ("BTN_NPC31", "LBL_NA31", "BTN_PAGE_PREV", "BTN_PAGE_NEXT")


# ---------------------------------------------------------------- generic GFF <-> JSON helpers (only the field kinds a gui control uses)

def _gff():
    from pykotor.resource.formats.gff import GFFStruct, GFFList, GFFFieldType, read_gff, write_gff, bytes_gff
    return GFFStruct, GFFList, GFFFieldType, read_gff, bytes_gff


def _to_json(value):
    from pykotor.common.misc import ResRef
    GFFStruct, GFFList, _t, _r, _b = _gff()
    if isinstance(value, GFFStruct):
        return {"struct": {label: _to_json(v) for label, _ft, v in value}}
    if isinstance(value, GFFList):
        return {"list": [_to_json(s) for s in value]}
    if isinstance(value, ResRef):
        return {"resref": str(value)}
    if hasattr(value, "x") and hasattr(value, "y") and hasattr(value, "z"):
        return {"v3": [value.x, value.y, value.z]}
    if isinstance(value, (int, float, str)):
        return value
    raise TypeError(f"party_layout: a gui field of type {type(value).__name__} is not handled")


def _flat(struct, prefix=""):
    """{path: [field kind, json value]} for every leaf of a control struct (nested structs are walked, lists are leaves)."""
    out = {}
    for label, ft, value in struct:
        path = prefix + label
        js = _to_json(value)
        if isinstance(js, dict) and "struct" in js:
            out.update(_flat(value, path + "/"))
        else:
            out[path] = [ft.name.lower(), js]
    return out


def _set_leaf(struct, path, entry):
    """Sets one leaf (path like 'EXTENT/LEFT') on a struct from [field kind, json value]; adds the field when the template control has none.
    A nested struct is a copy when read, so it is edited and written back."""
    from pykotor.common.misc import ResRef
    kind, js = entry
    parts = path.split("/")
    if len(parts) > 1:
        sub = struct.get_struct(parts[0])
        _set_leaf(sub, "/".join(parts[1:]), entry)
        struct.set_struct(parts[0], sub)
        return
    label = parts[0]
    if isinstance(js, dict) and "resref" in js:
        struct.set_resref(label, ResRef(js["resref"]))
    elif isinstance(js, dict) and "v3" in js:
        if struct.exists(label):
            vector = type(struct.get_vector3(label))
        else:
            from pykotor.utility.common.geometry import Vector3 as vector
        struct.set_vector3(label, vector(*js["v3"]))
    else:
        getattr(struct, "set_" + kind)(label, js)


def _by_tag(root):
    return {str(c.get_string("TAG")): c for c in root.get_list("CONTROLS")}


def _stock_root(game_dir):
    sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
    import build_game_assets
    data = build_game_assets.GameData(game_dir).resource("chitin", "partyselection", "gui")
    if data is None:
        raise FileNotFoundError("the game has no partyselection.gui")
    return _gff()[3](data).root


# ---------------------------------------------------------------- the builder

def build(game):
    """{'partyselection.gui': bytes}: the 32-slot layout made from the game's own file (game is a build_game_assets.GameData)."""
    GFFStruct, GFFList, _t, read_gff, bytes_gff = _gff()
    data = game.resource("chitin", "partyselection", "gui")
    if data is None:
        raise FileNotFoundError("the game has no partyselection.gui")
    gff = read_gff(data)
    root = gff.root
    with open(RECIPE_PATH, encoding="utf-8") as f:
        recipe = json.load(f)
    originals = {tag: copy.deepcopy(c) for tag, c in _by_tag(root).items()}
    controls = GFFList()
    for entry in recipe["controls"]:
        if "from" in entry:
            base = originals.get(entry["from"])
            if base is None:
                raise KeyError(f"the game's partyselection.gui has no control {entry['from']} to copy for {entry['tag']}")
            control = copy.deepcopy(base)
        else:
            base = originals.get(entry["tag"])
            if base is None:
                raise KeyError(f"the game's partyselection.gui has no control {entry['tag']}")
            control = copy.deepcopy(base)
        for path, value in entry["set"].items():
            _set_leaf(control, path, value)
        controls.append(control)
    root.set_list("CONTROLS", controls)
    return {LAYOUT_NAME: bytes_gff(gff)}


# ---------------------------------------------------------------- development: the recipe maker and the proof

def _distance(a, b):
    keys = set(a) | set(b)
    return sum(1 for k in keys if a.get(k) != b.get(k))


def make_recipe(stock_root, upstream_root):
    stock = _by_tag(stock_root)
    stock_flat = {tag: _flat(c) for tag, c in stock.items()}
    controls = []
    for control in upstream_root.get_list("CONTROLS"):
        tag = str(control.get_string("TAG"))
        flat = _flat(control)
        if tag in stock:
            base_tag = tag
        else:
            ctype = flat["CONTROLTYPE"]
            same = [t for t, f in stock_flat.items() if f["CONTROLTYPE"] == ctype]
            base_tag = min(same, key=lambda t: _distance(stock_flat[t], flat))
        sets = {k: v for k, v in flat.items() if stock_flat[base_tag].get(k) != v}
        entry = {"tag": tag}
        if base_tag != tag:
            entry["from"] = base_tag
        entry["set"] = sets
        controls.append(entry)
    return {"comment": "Numbers only: for each control of the 32-slot layout, the stock control to copy (when it is new) and the fields that differ from it. See party_layout.py.", "controls": controls}


def _control_dumps(root):
    return [(str(c.get_string("TAG")), _flat(c)) for c in root.get_list("CONTROLS")]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--make-recipe", metavar="UPSTREAM_GUI")
    ap.add_argument("--check", metavar="UPSTREAM_GUI")
    ap.add_argument("--game-dir", default=DEFAULT_GAME_DIR)
    args = ap.parse_args()
    if args.make_recipe:
        stock = _stock_root(args.game_dir)
        up = _gff()[3](open(args.make_recipe, "rb").read()).root
        recipe = make_recipe(stock, up)
        with open(RECIPE_PATH, "w", encoding="utf-8", newline="\n") as f:
            json.dump(recipe, f, indent=1)
        print(f"wrote {RECIPE_PATH}: {len(recipe['controls'])} controls, {sum(1 for c in recipe['controls'] if 'from' in c)} new")
    elif args.check:
        sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
        import build_game_assets
        built = _gff()[3](build(build_game_assets.GameData(args.game_dir))[LAYOUT_NAME]).root
        up = _gff()[3](open(args.check, "rb").read()).root
        a, b = _control_dumps(built), _control_dumps(up)
        same = a == b
        print("controls built:", len(a), "upstream:", len(b), "| identical control by control:", same)
        if not same:
            for (ta, fa), (tb, fb) in zip(a, b):
                if (ta, fa) != (tb, fb):
                    print("first difference:", ta, tb, {k: (fa.get(k), fb.get(k)) for k in set(fa) | set(fb) if fa.get(k) != fb.get(k)})
                    break
        sys.exit(0 if same else 1)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
