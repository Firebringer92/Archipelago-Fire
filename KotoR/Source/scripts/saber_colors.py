"""
The extra lightsaber crystal colors (Cyan, Orange, Bronze, Silver, Black, Purple), built on the player's machine from the player's own game files
(see build_game_assets.py). Nothing here is a copy of anyone's art:

  * models   the game's own violet blade models (w_lghtsbr_005, w_shortsbr_005, w_dblsbr_005 and their .mdx) saved under a new name with the
             four-letter colour code in the blade texture name changed (violet = "purp", all five texture names have 14 characters).
  * textures a radial glow (a bright core in the blade colour inside a soft halo), drawn here, plus its .txi.
  * templates the game's own *05 templates (hilt and crystal) with a new resref, tag and model variation; the crystal also gets a name,
             description and price.
  * icons    the game's own crystal and hilt icons with the saturated glow re-tinted to the new colour.
  * upcrystals.2da  the game's own table with one row per new colour: this is what makes a crystal change the hilt.

The names, variations and prices below are the ones the world's gear_items.json refers to (g_w_sbrcrstl22 ... g_w_sbrcrstl29), so they must not change.
"""
import colorsys
import math
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pykotor.common.language import LocalizedString
from pykotor.extract.installation import SearchLocation
from pykotor.resource.formats.gff import read_gff, write_gff
from pykotor.resource.formats.tpc import TPCTextureFormat
from pykotor.resource.formats.twoda import read_2da, write_2da
from pykotor.resource.generics.uti import construct_uti, dismantle_uti
from pykotor.resource.type import ResourceType

TEXTURE_PLACES = [SearchLocation.TEXTURES_TPA, SearchLocation.TEXTURES_TPB, SearchLocation.TEXTURES_TPC, SearchLocation.TEXTURES_GUI,
                  SearchLocation.CHITIN]
VANILLA_VARIANT = "005"            # the game's violet saber: its models name the texture w_lsabrepurp01
VANILLA_CODE = b"purp"

# label -> code (the 4 letters in the texture name), the model/template numbers (they follow the names the world already uses), crystal number,
# glow colours (core, halo, as RGB), and the icon tint: hue, the crystal's saturation and brightness scale, the hilt glow's saturation and brightness scale.
COLORS = {
    "Cyan":   dict(code="cyan", n=10, crystal=22, price=230, core=(215, 255, 255), halo=(0, 205, 200), hue=0.50, csat=0.60, cval=1.00, gsat=1.60, gval=1.00),
    "Orange": dict(code="orng", n=11, crystal=23, price=230, core=(255, 240, 200), halo=(255, 115, 20), hue=0.08, csat=0.85, cval=1.00, gsat=2.20, gval=1.00),
    "Bronze": dict(code="brnz", n=13, crystal=25, price=230, core=(255, 230, 195), halo=(190, 125, 55), hue=0.09, csat=0.50, cval=0.95, gsat=1.40, gval=0.85),
    "Silver": dict(code="silv", n=14, crystal=26, price=230, core=(255, 255, 255), halo=(205, 205, 215), hue=0.00, csat=0.00, cval=1.00, gsat=0.00, gval=1.00),
    "Black":  dict(code="blak", n=15, crystal=27, price=230, core=(0, 0, 0), halo=(255, 255, 255), hue=0.00, csat=0.00, cval=0.35, gsat=0.00, gval=0.20, dark=True),
    "Purple": dict(code=None, n=17, crystal=29, price=230, hue=0.78, csat=0.55, cval=1.00, gsat=1.70, gval=0.95),  # the game's own violet texture and models, unchanged
}


def _name(prefix, n, width=3):
    return f"{prefix}{n:0{width}d}"


def template_names(spec):
    n = spec["n"]
    return dict(long_uti=f"g_w_lghtsbr{n:02d}", short_uti=f"g_w_shortsbr{n:02d}", dbl_uti=f"g_w_dblsbr{n:03d}",
                crystal=f"g_w_sbrcrstl{spec['crystal']:02d}",
                long_mdl=_name("w_lghtsbr_", n), short_mdl=_name("w_shortsbr_", n), dbl_mdl=_name("w_dblsbr_", n),
                texture=f"w_lsabre{spec['code']}01" if spec["code"] else None,
                crystal_icon=_name("iw_sbrcrstl_", spec["crystal"]))


# ---------------------------------------------------------------------------------------------------- game access

def _model(game, stem, extension):
    res = game.installation.resource(stem, ResourceType.from_extension(extension), [SearchLocation.CHITIN, SearchLocation.MODULES])
    if res is None:
        raise FileNotFoundError(f"the game has no {stem}.{extension}")
    return bytes(res.data)


def _template(game, resref):
    res = game.installation.resource(resref, ResourceType.UTI, [SearchLocation.CHITIN, SearchLocation.MODULES])
    if res is None:
        raise FileNotFoundError(f"the game has no {resref}.uti")
    return construct_uti(read_gff(res.data))


def _texture(game, name):
    tpc = game.installation.texture(name, TEXTURE_PLACES)
    if tpc is None:
        raise FileNotFoundError(f"the game has no texture {name}")
    tpc = tpc.copy()
    tpc.convert(TPCTextureFormat.RGBA)
    width, height = tpc.dimensions()
    return width, height, bytearray(tpc.get(0, 0).data)


# ---------------------------------------------------------------------------------------------------- images

def write_tga(width, height, rgba):
    """Uncompressed 32-bit TGA. rgba is bottom row first, the order the game's own textures are stored in."""
    body = bytearray(len(rgba))
    for i in range(0, len(rgba), 4):
        body[i], body[i + 1], body[i + 2], body[i + 3] = rgba[i + 2], rgba[i + 1], rgba[i], rgba[i + 3]
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, width, height, 32, 8)
    return header + bytes(body)


def glow_texture(spec, size=128):
    """A radial glow: a solid core, then a halo that fades to nothing at the edge. Black draws a black core on a white halo."""
    cx = cy = (size - 1) / 2
    core_r, edge_r = size * 0.085, size * 0.5
    core, halo = spec["core"], spec["halo"]
    dark = spec.get("dark", False)
    out = bytearray()
    for y in range(size):
        for x in range(size):
            d = math.hypot(x - cx, y - cy)
            if d <= core_r:
                r, g, b, a = core[0], core[1], core[2], 255
            else:
                t = min(1.0, (d - core_r) / (edge_r - core_r))
                a = int(255 * (1 - t) ** 2.2) if not dark else int(255 * (1 - t) ** 1.2)
                # the halo is brightest next to the core and settles to the halo colour
                mix = max(0.0, 1.0 - t * 3.0)
                r = int(halo[0] + (core[0] - halo[0]) * mix * 0.6)
                g = int(halo[1] + (core[1] - halo[1]) * mix * 0.6)
                b = int(halo[2] + (core[2] - halo[2]) * mix * 0.6)
            out += bytes((r, g, b, a))
    return write_tga(size, size, out)


def txi_for_blade():
    """The same texture settings every blade glow in the game uses."""
    return b"blending 1\r\ndecal 1"


def retint(rgba, hue, sat_scale, val_scale, min_sat=0.2):
    """Re-tints the saturated glow of an icon to a new hue; the grey metal of a hilt is left alone."""
    out = bytearray(rgba)
    for i in range(0, len(out), 4):
        r, g, b, a = out[i], out[i + 1], out[i + 2], out[i + 3]
        if a == 0:
            continue
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if s <= min_sat:
            continue
        nr, ng, nb = colorsys.hsv_to_rgb(hue, min(1.0, s * sat_scale), min(1.0, v * val_scale))
        out[i], out[i + 1], out[i + 2] = round(nr * 255), round(ng * 255), round(nb * 255)
    return out


def colorize(rgba, hue, sat, val_scale):
    """Gives a whole icon one hue: every visible pixel keeps its brightness (so the facets and the dark outline survive) and takes the
    given saturation."""
    out = bytearray(rgba)
    for i in range(0, len(out), 4):
        r, g, b, a = out[i], out[i + 1], out[i + 2], out[i + 3]
        if a == 0:
            continue
        v = max(r, g, b) / 255
        nr, ng, nb = colorsys.hsv_to_rgb(hue, sat if v > 0.25 else sat * v * 4, min(1.0, v * val_scale))
        out[i], out[i + 1], out[i + 2] = round(nr * 255), round(ng * 255), round(nb * 255)
    return out


# ---------------------------------------------------------------------------------------------------- the pieces

def _uti_bytes(uti):
    data = bytearray()
    write_gff(dismantle_uti(uti), data)
    return bytes(data)


def _clone_template(game, base_resref, resref, variation):
    uti = _template(game, base_resref)
    old = str(uti.resref)
    uti.resref = type(uti.resref)(resref)
    tag = uti.tag
    uti.tag = tag.replace(old.upper(), resref.upper()) if tag == old.upper() else resref
    uti.model_variation = variation
    return uti


DESCRIPTION = "Special:\nUpgrade Item, Lightsaber\n\nBlade Color: {label}\n\nA lightsaber crystal that gives the blade a {lower} glow."


def build(game):
    """{file name: bytes} for every colour."""
    files = {}
    for label, spec in COLORS.items():
        names = template_names(spec)
        # models: the violet saber under a new name, with the texture code changed
        for stem_key, vanilla_prefix in (("long_mdl", "w_lghtsbr_"), ("short_mdl", "w_shortsbr_"), ("dbl_mdl", "w_dblsbr_")):
            base = vanilla_prefix + VANILLA_VARIANT
            mdl = _model(game, base, "mdl")
            if spec["code"]:
                new_texture = f"w_lsabre{spec['code']}01".encode()
                mdl = mdl.replace(b"w_lsabre" + VANILLA_CODE + b"01", new_texture)
            files[f"{names[stem_key]}.mdl"] = mdl
            files[f"{names[stem_key]}.mdx"] = _model(game, base, "mdx")
        # blade texture
        if spec["code"]:
            files[f"{names['texture']}.tga"] = glow_texture(spec)
            files[f"{names['texture']}.txi"] = txi_for_blade()
        # templates
        for key, base, variation in (("long_uti", "g_w_lghtsbr05", spec["n"]), ("short_uti", "g_w_shortsbr05", spec["n"]),
                                     ("dbl_uti", "g_w_dblsbr005", spec["n"])):
            files[f"{names[key]}.uti"] = _uti_bytes(_clone_template(game, base, names[key], variation))
        crystal = _clone_template(game, "g_w_sbrcrstl05", names["crystal"], spec["crystal"])
        crystal.name = LocalizedString.from_english(f"Crystal, {label}")
        crystal.description = LocalizedString.from_english(DESCRIPTION.format(label=label, lower=label.lower()))
        crystal.cost = spec["price"]
        files[f"{names['crystal']}.uti"] = _uti_bytes(crystal)
        # icons: the crystal, and the three hilts (an upgraded hilt looks up iw_<form>_<variation>)
        width, height, rgba = _texture(game, "iw_sbrcrstl_004")
        files[f"{names['crystal_icon']}.tga"] = write_tga(width, height, colorize(rgba, spec["hue"], spec["csat"], spec["cval"]))
        for prefix in ("iw_lghtsbr_", "iw_shortsbr_", "iw_dblsbr_"):
            width, height, rgba = _texture(game, f"{prefix}001")      # the game's blue hilt: its glow is the brightest to tint
            files[f"{prefix}{spec['n']:03d}.tga"] = write_tga(width, height, retint(rgba, spec["hue"], spec["gsat"], spec["gval"]))
    files["upcrystals.2da"] = _upcrystals(game)
    return files


def _upcrystals(game):
    res = game.installation.resource("upcrystals", ResourceType.TwoDA, [SearchLocation.CHITIN])
    table = read_2da(res.data)
    existing = {table.get_cell(i, "label") for i in range(table.get_height())}
    for label, spec in COLORS.items():
        if label.upper() in existing:
            continue
        names = template_names(spec)
        table.add_row(None, {"label": label.upper(), "template": names["crystal"], "shortmdlvar": names["short_uti"],
                             "longmdlvar": names["long_uti"], "doublemdlvar": names["dbl_uti"]})
    out = bytearray()
    write_2da(table, out)
    return bytes(out)
