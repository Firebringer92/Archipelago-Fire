"""Builds the new lightsaber crystal colours for TSL into assets/crystals/ (nothing is deployed here).

Method (the same shape the K1 project used, see add_saber_crystal_colors.py in the K1 mirror): a blade's colour is only a texture name
inside the model, so each new hilt model is a copy of TSL's own blue model with that name swapped (same length, so the file layout is
unchanged). Per colour this writes: three hilt models (long, short, double: .mdl and .mdx), the blade texture (.tga and .txi), a crystal
item and three hilt items (.uti, clones of TSL's blue ones), icons, and the rows of an upcrystals.2da that adds the new colours.

Names and numbers:
  hilt model variation 11..16 (TSL's own models stop at 10 for long hilts and 9 for short and double ones); hilt item names 21..26,
  crystal item u_l_colo_11..16 with ModelVariation 50..55 (TSL's crystals use 1..49 except 19),
  textures: K1's silver and purple files share their names with TSL's own silver and violet blades, so they are renamed here.
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import tsl_data as T  # noqa: E402
from pykotor.common.language import LocalizedString  # noqa: E402
from pykotor.extract.installation import Installation  # noqa: E402
from pykotor.resource.formats.gff import GFF, GFFContent, write_gff  # noqa: E402
from pykotor.resource.formats.tpc import TPC, TPCTextureFormat, read_tpc, write_tpc  # noqa: E402
from pykotor.resource.formats.twoda import TwoDA, write_2da  # noqa: E402
from pykotor.resource.generics.uti import construct_uti, dismantle_uti  # noqa: E402
from pykotor.resource.type import ResourceType  # noqa: E402

RT = T.RT
MIRROR = r"C:\Users\User\Documents\GitHub\Archipelago-Fire\KotoR\Source\extender\raw_override_files"
OUT = os.path.join(ROOT, "assets", "crystals")

# texture names are 14 characters like the blue one they replace; "src" says where the texture file comes from.
COLOURS = [
    dict(alpha=1.5, name="Cyan",    tex="w_lsabrecyan01", src=("mirror", "w_lsabrecyan01"), var=11, crystal="u_l_colo_11", cvar=50, k1_crystal_icon="iw_sbrcrstl_022", k1_hilt=10),
    dict(alpha=1.5, name="Orange",  tex="w_lsabreorng01", src=("mirror", "w_lsabreorng01"), var=12, crystal="u_l_colo_12", cvar=51, k1_crystal_icon="iw_sbrcrstl_023", k1_hilt=11),
    dict(alpha=1.5, name="Bronze",  tex="w_lsabrebrnz01", src=("mirror", "w_lsabrebrnz01"), var=13, crystal="u_l_colo_13", cvar=52, k1_crystal_icon="iw_sbrcrstl_025", k1_hilt=13),
    dict(alpha=None, name="Black",   tex="w_lsabreblak01", src=("mirror", "w_lsabreblak01"), var=14, crystal="u_l_colo_14", cvar=53, k1_crystal_icon="iw_sbrcrstl_027", k1_hilt=15),
    dict(alpha=1.5, name="Argent",  tex="w_lsabreargn01", src=("k1", "w_lsabresilv01"),     var=15, crystal="u_l_colo_15", cvar=54, k1_crystal_icon="iw_sbrcrstl_026", k1_hilt=14),
    dict(alpha=1.0, name="Magenta", tex="w_lsabremgnt01", src=("mirror", "w_lsabrepurp01"), var=16, crystal="u_l_colo_16", cvar=55, k1_crystal_icon=None,              k1_hilt=None),
]
FORMS = [
    dict(label="long",   model="w_lghtsbr_001",  internal="w_Lghtsbr_",  out="w_lghtsbr_",  hilt="g_w_lghtsbr01",  newhilt="g_w_lghtsbr%02d",  icon="iw_lghtsbr_",  title="Lightsaber"),
    dict(label="short",  model="w_shortsbr_001", internal="w_ShortSbr_", out="w_shortsbr_", hilt="g_w_shortsbr01", newhilt="g_w_shortsbr%02d", icon="iw_shortsbr_", title="Short Lightsaber"),
    dict(label="double", model="w_dblsbr_001",   internal="w_Dblsbr_",   out="w_dblsbr_",   hilt="g_w_dblsbr001",  newhilt="g_w_dblsbr0%02d",  icon="iw_dblsbr_",   title="Double-Bladed Lightsaber"),
]
OLD_TEX = b"w_lsabreblue01"


def res_bytes(rt, name):
    d = T.find(name, rt)
    if d is None:
        raise RuntimeError("not found in TSL: " + name)
    return bytes(d if isinstance(d, (bytes, bytearray)) else d.data())


def patch_model(data, internal_old, internal_new, tex_new):
    if len(tex_new) != len(OLD_TEX):
        raise RuntimeError("texture names must keep the same length")
    if OLD_TEX not in data:
        raise RuntimeError("blue texture name not found in the model")
    out = data.replace(OLD_TEX, tex_new.encode("ascii"))
    old = internal_old.encode("ascii")
    new = internal_new.encode("ascii")
    if len(old) != len(new) or old not in out:
        raise RuntimeError("internal model name not found or length differs")
    return out.replace(old, new)


def clone_item(source, resref, name, variation, description=None):
    root = T.gff(source, RT.UTI)
    wrapper = GFF(GFFContent.UTI)
    wrapper.root = root
    uti = construct_uti(wrapper)
    uti.resref = type(uti.resref)(resref)
    uti.tag = resref
    uti.name = LocalizedString.from_english(name)
    if description is not None:
        uti.description = LocalizedString.from_english(description)
    uti.model_variation = variation
    return dismantle_uti(uti)


def mirror_file(stem, ext):
    for f in os.listdir(MIRROR):
        if f.lower() == (stem + ext).lower():
            return os.path.join(MIRROR, f)
    return None


def add_alpha(path, factor):
    """Blade textures without a transparency channel draw their black background as a solid slab around the blade, so the alpha
    is derived from brightness (black becomes transparent, the glow stays). `factor` makes the glow more (above 1) or less solid."""
    tpc = read_tpc(open(path, "rb").read())
    tpc.convert(TPCTextureFormat.RGBA)
    m = tpc.get(0, 0)
    data = bytearray(m.data)
    for i in range(0, len(data), 4):
        data[i + 3] = min(255, int(max(data[i], data[i + 1], data[i + 2]) * factor))
    out = TPC()
    out.set_single(data, TPCTextureFormat.RGBA, m.width, m.height)
    write_tpc(out, path, ResourceType.TGA)


def write_icon_from_tsl(stem, out_name):
    tpc = T.inst().texture(stem)
    write_tpc(tpc, os.path.join(OUT, out_name + ".tga"), ResourceType.TGA)


def main():
    os.makedirs(OUT, exist_ok=True)
    inst1 = Installation(r"C:\Program Files (x86)\Steam\steamapps\common\swkotor")
    manifest = []
    rows = []
    for c in COLOURS:
        kind, stem = c["src"]
        if kind == "mirror":
            shutil.copyfile(mirror_file(stem, ".tga"), os.path.join(OUT, c["tex"] + ".tga"))
            shutil.copyfile(mirror_file(stem, ".txi"), os.path.join(OUT, c["tex"] + ".txi"))
        else:
            tpc = inst1.texture(stem)
            write_tpc(tpc, os.path.join(OUT, c["tex"] + ".tga"), ResourceType.TGA)
            with open(os.path.join(OUT, c["tex"] + ".txi"), "w", encoding="ascii") as f:
                f.write(tpc.txi or "")
        if c["alpha"] is not None:
            add_alpha(os.path.join(OUT, c["tex"] + ".tga"), c["alpha"])
        with open(os.path.join(OUT, c["tex"] + ".txi"), "w", encoding="ascii") as f:
            f.write("blending 1\ndecal 1")      # the settings of TSL's own blade textures
        hilts = {}
        for fm in FORMS:
            mdl = patch_model(res_bytes(RT.MDL, fm["model"]), fm["internal"] + "001", fm["internal"] + "%03d" % c["var"], c["tex"])
            mdx = res_bytes(RT.MDX, fm["model"])
            base = "%s%03d" % (fm["out"], c["var"])
            with open(os.path.join(OUT, base + ".mdl"), "wb") as f:
                f.write(mdl)
            with open(os.path.join(OUT, base + ".mdx"), "wb") as f:
                f.write(mdx)
            resref = fm["newhilt"] % (c["var"] + 10)   # item names 21..26: TSL already uses g_w_lghtsbr01..11 and the matching short and double names
            hilts[fm["label"]] = resref
            write_gff(clone_item(fm["hilt"], resref, fm["title"], c["var"]), os.path.join(OUT, resref + ".uti"))
            icon_name = "%s%03d" % (fm["icon"], c["var"])
            k1 = mirror_file("%s%03d" % (fm["icon"], c["k1_hilt"]), ".tga") if c["k1_hilt"] is not None else None
            if k1:
                shutil.copyfile(k1, os.path.join(OUT, icon_name + ".tga"))
            else:
                write_icon_from_tsl("%s%03d" % (fm["icon"], 5), icon_name)     # TSL's own violet hilt icon
        root = T.gff("u_l_colo_01", RT.UTI)
        desc = ""
        if root.exists("DescIdentified"):
            desc = T.tlk_text(root.get_locstring("DescIdentified").stringref) or ""
        desc = desc.replace("Blue", c["name"]) if desc else "Blade Color: " + c["name"]
        write_gff(clone_item("u_l_colo_01", c["crystal"], "Crystal, " + c["name"], c["cvar"], desc), os.path.join(OUT, c["crystal"] + ".uti"))
        cicon = "iw_sbrcrstl_%03d" % c["cvar"]
        k1c = mirror_file(c["k1_crystal_icon"], ".tga") if c["k1_crystal_icon"] else None
        if k1c:
            shutil.copyfile(k1c, os.path.join(OUT, cicon + ".tga"))
        else:
            write_icon_from_tsl("iw_sbrcrstl_017", cicon)                       # TSL's own violet crystal icon
        rows.append((c["name"].upper(), c["crystal"], hilts["short"], hilts["long"], hilts["double"]))
        manifest.append("%-8s crystal %s (variation %d)  hilts %s %s %s  texture %s" % (c["name"], c["crystal"], c["cvar"], hilts["long"], hilts["short"], hilts["double"], c["tex"]))

    base = T.twoda("upcrystals")
    new = TwoDA(base.get_headers())
    ours = {c["crystal"] for c in COLOURS}      # the table is read through the Override folder too: do not copy our own rows back
    n = 0
    for i in range(base.get_height()):
        if base.get_cell(i, "template") in ours:
            continue
        new.add_row(str(n), {h: base.get_cell(i, h) for h in base.get_headers()})
        n += 1
    for label, crystal, short, long_, dbl in rows:
        new.add_row(str(n), {"label": label, "template": crystal, "shortmdlvar": short, "longmdlvar": long_, "doublemdlvar": dbl})
        n += 1
    write_2da(new, os.path.join(OUT, "upcrystals.2da"))
    with open(os.path.join(OUT, "MANIFEST.txt"), "w") as f:
        f.write("\n".join(manifest) + "\n")
    print("\n".join(manifest))
    print("files:", len(os.listdir(OUT)))


if __name__ == "__main__":
    main()
