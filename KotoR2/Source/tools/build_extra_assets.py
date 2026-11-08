"""Copies the models, textures and portraits of the KotOR 1 companions from the player's own KotOR 1 install into a folder for the KotOR 2 Override.

The KotOR 2 appearance and portrait tables already have rows for the K1 companions (appearance 4-10, portrait ids 14, 33-38), so nothing in a table has to
change: the rows name models that are only missing from the files. This takes those models (and every texture they use, and the portrait images) out of the
player's K1 files. Nothing from the game is kept in the project; nothing built here may be published.

  python tools/build_extra_assets.py --game-dir <K2 folder> --k1-dir <K1 folder> --out DIR

Output: the .mdl, .mdx and texture files in DIR, and extra_assets_report.json (what was copied, what was already in K2, what K1 does not have). A character
whose model cannot be found falls back to a K2 look (see data/extra_companions.json).
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# the K1 companions of data/extra_companions.json: name -> (appearance.2da row, portraits.2da row)
K1_ROWS = {"Bastila Shan": (4, 33), "Canderous Ordo": (5, 39), "Carth Onasi": (6, 14), "Jolee Bindo": (7, 38), "Juhani": (8, 37), "Zaalbar": (9, 36),
           "Mission Vao": (10, 35)}
MODEL_COLUMNS = ("race", "normalhead", "backuphead", "modela", "modelb", "modelc", "modeld", "modele", "modelf", "modelg", "modelh", "modeli", "modelj")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-dir", required=True)
    ap.add_argument("--k1-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", nargs="*", default=None, help="names to build (default: all seven)")
    a = ap.parse_args()
    os.environ["K2_GAME_DIR"] = a.game_dir
    import tsl_data as T
    from pykotor.extract.installation import Installation, SearchLocation
    from pykotor.resource.formats.mdl import read_mdl
    from pykotor.resource.type import ResourceType as RT

    if not os.path.isfile(os.path.join(a.k1_dir, "swkotor.exe")):
        print("swkotor.exe is not in %s: that is not a KotOR 1 folder." % a.k1_dir)
        return 2
    k1 = Installation(a.k1_dir)
    k2 = T.inst()
    os.makedirs(a.out, exist_ok=True)
    locs = [SearchLocation.OVERRIDE, SearchLocation.CHITIN, SearchLocation.TEXTURES_TPA, SearchLocation.TEXTURES_GUI, SearchLocation.TEXTURES_TPB, SearchLocation.TEXTURES_TPC]
    report = {"copied": [], "already_in_k2": [], "missing_in_k1": [], "characters": {}}
    app = T.twoda("appearance")
    por = T.twoda("portraits")

    def write(name, rtype, data):
        path = os.path.join(a.out, name.lower() + "." + rtype.extension)
        with open(path, "wb") as f:
            f.write(data)
        report["copied"].append(os.path.basename(path))

    def take(name, rtype):
        """Copy name.rtype from K1 unless K2 already has it. Returns the resource or None."""
        if k2.resource(name, rtype, locs) is not None:
            report["already_in_k2"].append("%s.%s" % (name, rtype.extension))
            return None
        res = k1.resource(name, rtype, locs)
        if res is None:
            report["missing_in_k1"].append("%s.%s" % (name, rtype.extension))
            return None
        write(name, rtype, res.data)
        return res

    for who, (arow, prow) in K1_ROWS.items():
        if a.only and who not in a.only:
            continue
        copied_before = len(report["copied"])
        models = {app.get_cell(arow, c) for c in MODEL_COLUMNS}
        for model in sorted(m for m in models if m and m != "****" and not m.isdigit()):
            res = take(model, RT.MDL)
            take(model, RT.MDX)
            mdl = res or k1.resource(model, RT.MDL, locs)
            if mdl is None:
                continue
            mdx = k1.resource(model, RT.MDX, locs)
            try:
                tree = read_mdl(mdl.data, source_ext=mdx.data if mdx else None)
            except Exception as e:                                           # a model the reader cannot parse is still copied; its textures are then guessed
                report["missing_in_k1"].append("%s textures (%s)" % (model, e))
                continue
            textures = set()
            for node in tree.all_nodes():
                if node.mesh:
                    textures |= {t for t in (node.mesh.texture_1, node.mesh.texture_2) if t and t.upper() != "NULL"}
            for tex in sorted(textures):
                if take(tex, RT.TPC) is None and k2.resource(tex, RT.TPC, locs) is None:
                    take(tex, RT.TGA)
        base = por.get_cell(prow, "baseresref")
        if base and base != "****":
            for suffix in ("", "s", "m", "l"):
                if take(base + suffix, RT.TPC) is None and k2.resource(base + suffix, RT.TPC, locs) is None:
                    take(base + suffix, RT.TGA)
        report["characters"][who] = {"appearance_row": arow, "portrait_row": prow, "files_copied": len(report["copied"]) - copied_before}
    with open(os.path.join(a.out, "extra_assets_report.json"), "w") as f:
        json.dump(report, f, indent=1)
    print("copied %d files into %s; %d already in K2; %d not found in K1" % (len(report["copied"]), a.out, len(report["already_in_k2"]),
                                                                        len(report["missing_in_k1"])))
    for who, info in report["characters"].items():
        print("  %-16s %d files" % (who, info["files_copied"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
