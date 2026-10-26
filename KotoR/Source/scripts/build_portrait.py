"""
Turns a screenshot into a 64x64 party portrait texture (the size and format of the game's own portraits).

  python build_portrait.py <image> <resref> [--crop=left,top,right,bottom] [--out-dir=DIR]

The crop is made square (centered on the given box, or on the whole image) and scaled down with a high-quality filter. Writes
<out-dir>/<resref>.tpc (default extender/raw_override_files) and <resref>_preview.png (a 256x256 enlargement, not shipped).
"""
import os
import sys

from PIL import Image
from pykotor.resource.formats.tpc import TPC, TPCTextureFormat, write_tpc, read_tpc

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = os.path.join(REPO_ROOT, "extender", "raw_override_files")
SIZE = 64


def _arg(name, default=None):
    for a in sys.argv[3:]:
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return default


def square_crop(img, box=None):
    left, top, right, bottom = box if box else (0, 0, img.width, img.height)
    side = min(right - left, bottom - top)
    cx, cy = (left + right) / 2, (top + bottom) / 2
    left = int(round(cx - side / 2))
    top = int(round(cy - side / 2))
    left = max(0, min(left, img.width - side))
    top = max(0, min(top, img.height - side))
    return img.crop((left, top, left + side, top + side))


def to_tpc(img):
    """RGB bytes of a SIZE x SIZE image as an uncompressed TPC (bottom row first, as TPC stores it; the game's own portraits are RGB)."""
    flipped = img.convert("RGB").transpose(Image.FLIP_TOP_BOTTOM)
    tpc = TPC()
    tpc.set_single(bytearray(flipped.tobytes()), TPCTextureFormat.RGB, SIZE, SIZE)
    return tpc


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    path, resref = sys.argv[1], sys.argv[2]
    box = _arg("--crop")
    box = tuple(int(v) for v in box.split(",")) if box else None
    out_dir = _arg("--out-dir", DEFAULT_OUT)
    os.makedirs(out_dir, exist_ok=True)
    img = Image.open(path).convert("RGBA")
    small = square_crop(img, box).resize((SIZE, SIZE), Image.LANCZOS)
    out = os.path.join(out_dir, f"{resref}.tpc")
    write_tpc(to_tpc(small), out)
    check = read_tpc(open(out, "rb").read())
    assert check.dimensions() == (SIZE, SIZE)
    small.resize((256, 256), Image.NEAREST).save(os.path.join(out_dir, f"{resref}_preview.png"))
    print(f"wrote {out} ({os.path.getsize(out)} bytes, {check.dimensions()}, {check.format()})")


if __name__ == "__main__":
    main()
