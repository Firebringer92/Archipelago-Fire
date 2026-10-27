"""
Builds the recolored HK-47 skin (black armor, silver trim) used by the HK-47 variant look (see build_hk47_variant.py).

Takes the vanilla texture p_hk47_01 straight from the game's data, so nothing copyrighted is stored in the repo until
this runs on the user's own install, and writes extender/raw_override_files/ap_hk47v_01.tga (32-bit TGA, fully
opaque: the vanilla alpha is a gloss mask that the engine only treats as such through the original's TXI).

Recolor rules:
  * copper/orange plating (hue 0-65 degrees, any real saturation) -> near-black, keeping the plate detail
  * the brightest worn parts of those plates (edges, scratches)  -> silver, so the wear reads as polished trim
  * the saturated red glow panel                                  -> unchanged
  * everything else (the existing gray/black metal)               -> slightly cooled toward silver

Usage: python build_hk47_variant_texture.py [--game-dir=PATH] [--preview=PATH_TO_PNG]
"""
import colorsys
import os
import sys

import numpy as np
from PIL import Image

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
OUT_DIR = os.environ.get("KOTOR_AP_MODEL_OUT") or os.path.join(REPO_ROOT, "extender", "raw_override_files")
SOURCE_TEXTURE = "p_hk47_01"
OUT_TEXTURE = "ap_hk47v_01"

BLACK_FLOOR = 0.035       # darkest value of the recolored plating
BLACK_GAIN = 0.30         # how much of the original brightness variation survives
SILVER = np.array([0.80, 0.82, 0.85])
TRIM_START, TRIM_SPAN = 0.50, 0.30   # luminance where plating starts turning silver, and how fast


def _arg(flag, default=None):
    for a in sys.argv[1:]:
        if a.startswith(flag + "="):
            return a.split("=", 1)[1]
    return default


def load_source(game_dir):
    from pykotor.extract.installation import Installation, SearchLocation
    from pykotor.resource.formats.tpc import write_tpc
    from pykotor.resource.type import ResourceType
    inst = Installation(game_dir)
    tex = inst.texture(SOURCE_TEXTURE, [SearchLocation.OVERRIDE, SearchLocation.TEXTURES_TPA, SearchLocation.TEXTURES_TPB,
                                        SearchLocation.TEXTURES_TPC, SearchLocation.CHITIN])
    if tex is None:
        raise RuntimeError(f"{SOURCE_TEXTURE} not found in the game's data")
    tmp = os.path.join(OUT_DIR, "_hk47_source.tga")
    os.makedirs(OUT_DIR, exist_ok=True)
    write_tpc(tex, tmp, ResourceType.TGA)
    image = Image.open(tmp).convert("RGBA")
    os.remove(tmp)
    return image


def recolor(image):
    arr = np.asarray(image).astype(np.float32) / 255.0
    rgb, alpha = arr[..., :3], arr[..., 3:]
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx, mn = rgb.max(axis=-1), rgb.min(axis=-1)
    sat = np.where(mx > 1e-5, (mx - mn) / np.maximum(mx, 1e-5), 0.0)
    lum = 0.299 * r + 0.587 * g + 0.114 * b

    # hue in degrees (only meaningful where sat > 0)
    delta = np.maximum(mx - mn, 1e-5)
    hue = np.zeros_like(mx)
    hue = np.where(mx == r, (60 * ((g - b) / delta)) % 360, hue)
    hue = np.where(mx == g, 60 * ((b - r) / delta) + 120, hue)
    hue = np.where(mx == b, 60 * ((r - g) / delta) + 240, hue)

    plating = (sat > 0.14) & (hue >= 0) & (hue <= 65) & (lum > 0.04)
    glow = (r > 0.78) & (g < 0.45) & (b < 0.30) & (sat > 0.65)
    plating &= ~glow

    # near-black plating that keeps its surface detail
    lo, hi = np.percentile(lum[plating], [2, 98]) if plating.any() else (0.0, 1.0)
    norm = np.clip((lum - lo) / max(hi - lo, 1e-5), 0.0, 1.0)
    dark = BLACK_FLOOR + BLACK_GAIN * norm * 0.55
    dark_rgb = np.stack([dark * 0.98, dark, dark * 1.06], axis=-1)

    # worn highlights turn silver
    trim = np.clip((norm - TRIM_START) / TRIM_SPAN, 0.0, 1.0) ** 1.4
    plated = dark_rgb * (1 - trim[..., None]) + (SILVER[None, None, :] * (0.55 + 0.45 * norm[..., None])) * trim[..., None]

    # existing gray/black metal: cool it slightly toward silver, no other change
    cool = rgb * 0.92 + SILVER[None, None, :] * lum[..., None] * 0.08

    out = np.where(plating[..., None], plated, np.where(glow[..., None], rgb, cool))
    out = np.clip(out, 0.0, 1.0)
    # The vanilla alpha is the engine's gloss mask (its TXI says so); our copy has no TXI, so the engine would read it as
    # transparency and fade the model out. Fully opaque instead.
    opaque = np.ones_like(alpha)
    return Image.fromarray((np.concatenate([out, opaque], axis=-1) * 255.0 + 0.5).astype(np.uint8), "RGBA"), plating, glow


def main():
    image = load_source(_arg("--game-dir", DEFAULT_GAME_DIR))
    result, plating, glow = recolor(image)
    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, OUT_TEXTURE + ".tga")
    result.save(out_path, format="TGA")
    print(f"wrote {out_path} ({os.path.getsize(out_path)} bytes); recolored {plating.mean() * 100:.0f}% of pixels, "
          f"kept {glow.mean() * 100:.1f}% as the red glow")
    preview = _arg("--preview")
    if preview:
        side = Image.new("RGB", (image.width * 2, image.height))
        side.paste(image.convert("RGB"), (0, 0))
        side.paste(result.convert("RGB"), (image.width, 0))
        side.save(preview)
        print("preview ->", preview)


if __name__ == "__main__":
    main()
