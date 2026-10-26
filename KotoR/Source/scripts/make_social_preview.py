r"""
Draws the GitHub social preview image (1280 x 640, the size GitHub asks for) for the repository: an original space scene with
two lightsaber blades (blue for the first game, red for the second), a faint network of linked nodes for the
multiworld, and a title that names both games. Nothing from the games or from Archipelago's logo is used.

Usage: python make_social_preview.py [--out PATH]      (default: docs/social_preview_1280x640.png)
Upload it in the repository's Settings, General, Social preview.
"""
import math
import os
import random
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO_ROOT, "docs", "social_preview_1280x640.png")
for i, a in enumerate(sys.argv):
    if a == "--out" and i + 1 < len(sys.argv):
        OUT = sys.argv[i + 1]
    elif a.startswith("--out="):
        OUT = a.split("=", 1)[1]

W, H, S = 1280, 640, 2            # final size and supersampling factor
FONTS = r"C:\Windows\Fonts"
BLUE = (70, 170, 255)
RED = (255, 70, 60)
CYAN = (120, 220, 255)
AMBER = (255, 170, 80)
random.seed(1138)
np.random.seed(1138)


def font(name, size):
    return ImageFont.truetype(os.path.join(FONTS, name), int(size * S))


def blank():
    return Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))


def glow(layer, color, radius, strength=1.0):
    """The layer's shapes recoloured and blurred, for a light bloom under them."""
    alpha = layer.getchannel("A").filter(ImageFilter.GaussianBlur(radius * S))
    alpha = alpha.point(lambda v: min(255, int(v * strength)))
    out = Image.new("RGBA", layer.size, color + (0,))
    out.putalpha(alpha)
    return out


def radial(center, radius, color, power=2.0, strength=1.0):
    ys, xs = np.mgrid[0:H * S, 0:W * S]
    d = np.sqrt((xs - center[0] * S) ** 2 + (ys - center[1] * S) ** 2) / (radius * S)
    a = np.clip(1.0 - d, 0, 1) ** power * strength
    arr = np.zeros((H * S, W * S, 4), dtype=np.uint8)
    arr[..., 0], arr[..., 1], arr[..., 2] = color
    arr[..., 3] = (a * 255).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def tracked_width(text, fnt, tracking):
    return sum(fnt.getlength(c) for c in text) + tracking * S * (len(text) - 1)


def draw_tracked(draw, cx, y, text, fnt, fill, tracking=0):
    """Text centred on cx with extra letter spacing, top edge at y."""
    x = cx * S - tracked_width(text, fnt, tracking) / 2
    for ch in text:
        draw.text((x, y * S), ch, font=fnt, fill=fill)
        x += fnt.getlength(ch) + tracking * S


# ------------------------------------------------------------------ background
img = Image.new("RGBA", (W * S, H * S), (5, 8, 18, 255))
img = Image.alpha_composite(img, radial((640, 330), 760, (16, 46, 78), 1.6, 0.9))
img = Image.alpha_composite(img, radial((130, 640), 560, (20, 80, 150), 2.0, 0.55))
img = Image.alpha_composite(img, radial((1150, 640), 560, (150, 40, 30), 2.0, 0.55))

# ------------------------------------------------------------------ stars
stars = blank()
sd = ImageDraw.Draw(stars)
for _ in range(520):
    x, y = random.uniform(0, W), random.uniform(0, H)
    b = random.choice([90, 120, 160, 200, 255])
    r = random.choice([0.6, 0.6, 0.8, 1.0, 1.3])
    tint = random.choice([(255, 255, 255), (200, 225, 255), (255, 235, 210)])
    sd.ellipse([(x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S], fill=tint + (b,))
img = Image.alpha_composite(img, stars)
big = blank()
bd = ImageDraw.Draw(big)
for _ in range(18):
    x, y = random.uniform(20, W - 20), random.uniform(15, H - 15)
    bd.ellipse([(x - 1.8) * S, (y - 1.8) * S, (x + 1.8) * S, (y + 1.8) * S], fill=(255, 255, 255, 230))
img = Image.alpha_composite(img, glow(big, (180, 210, 255), 5, 1.4))
img = Image.alpha_composite(img, big)

# ------------------------------------------------------------------ the multiworld: linked nodes
nodes = []
while len(nodes) < 20:
    x, y = random.uniform(30, W - 30), random.uniform(30, H - 30)
    if abs(x - 640) < 470 and 150 < y < 520:     # keep the middle clear for the title
        continue
    if all(math.hypot(x - a, y - b) > 110 for a, b in nodes):
        nodes.append((x, y))
net = blank()
nd = ImageDraw.Draw(net)
for i, (x1, y1) in enumerate(nodes):
    for x2, y2 in nodes[i + 1:]:
        if math.hypot(x1 - x2, y1 - y2) < 300:
            nd.line([x1 * S, y1 * S, x2 * S, y2 * S], fill=CYAN + (55,), width=int(1.4 * S))
for x, y in nodes:
    nd.ellipse([(x - 4) * S, (y - 4) * S, (x + 4) * S, (y + 4) * S], fill=CYAN + (220,))
img = Image.alpha_composite(img, glow(net, CYAN, 6, 1.2))
img = Image.alpha_composite(img, net)

# ------------------------------------------------------------------ two sabers, one for each game
def saber(x_hilt, y_hilt, x_tip, y_tip, color):
    global img
    blade = blank()
    bdr = ImageDraw.Draw(blade)
    bdr.line([x_hilt * S, y_hilt * S, x_tip * S, y_tip * S], fill=color + (255,), width=int(15 * S))
    img = Image.alpha_composite(img, glow(blade, color, 34, 1.7))
    img = Image.alpha_composite(img, glow(blade, color, 12, 2.2))
    img = Image.alpha_composite(img, blade)
    core = blank()
    cdr = ImageDraw.Draw(core)
    cdr.line([x_hilt * S, y_hilt * S, x_tip * S, y_tip * S], fill=(255, 255, 255, 255), width=int(6 * S))
    img = Image.alpha_composite(img, core)
    # a plain emitter and grip, drawn along the same line past the hilt end
    dx, dy = x_hilt - x_tip, y_hilt - y_tip
    n = math.hypot(dx, dy)
    ux, uy = dx / n, dy / n
    hilt = blank()
    hd = ImageDraw.Draw(hilt)
    for t0, t1, col, wd in ((0, 22, (190, 196, 206, 255), 17), (22, 118, (60, 66, 78, 255), 15), (118, 128, (190, 196, 206, 255), 18)):
        a = (x_hilt + ux * t0, y_hilt + uy * t0)
        b = (x_hilt + ux * t1, y_hilt + uy * t1)
        hd.line([a[0] * S, a[1] * S, b[0] * S, b[1] * S], fill=col, width=int(wd * S))
    img = Image.alpha_composite(img, hilt)


saber(78, 520, 190, 24, BLUE)
saber(1202, 520, 1090, 24, RED)

# ------------------------------------------------------------------ text
text = blank()
td = ImageDraw.Draw(text)
f_tag = font("AGENCYR.TTF", 34)
f_title = font("AGENCYB.TTF", 215)
f_sub = font("AGENCYR.TTF", 40)
f_small = font("AGENCYR.TTF", 30)

draw_tracked(td, 640, 66, "ARCHIPELAGO  MULTIWORLD  RANDOMIZER", f_tag, CYAN + (255,), 9)

# KOTOR  I  &  II on one line, the numerals tinted per game
parts = [("KOTOR", (240, 244, 250, 255)), ("  I ", BLUE + (255,)), ("&", (200, 205, 215, 255)), (" II", RED + (255,))]
gap = 6
total = sum(f_title.getlength(p) for p, _ in parts) + gap * S * (len(parts) - 1)
x = 640 * S - total / 2
y_title = 118 * S
layers = {}
for p, col in parts:
    td.text((x, y_title), p, font=f_title, fill=col)
    x += f_title.getlength(p) + gap * S

draw_tracked(td, 640, 372, "KNIGHTS OF THE OLD REPUBLIC", f_sub, (230, 236, 246, 255), 10)
draw_tracked(td, 640, 420, "THE  SITH  LORDS", f_sub, (230, 236, 246, 255), 10)
draw_tracked(td, 640, 540, "Play KOTOR alongside other games in a shared multiworld", f_small, (170, 190, 215, 255), 2)

shadow = glow(text, (0, 0, 0), 10, 1.2)
img = Image.alpha_composite(img, shadow)
img = Image.alpha_composite(img, glow(text, (140, 180, 255), 16, 0.35))
img = Image.alpha_composite(img, text)

# ------------------------------------------------------------------ frame, scan lines and save
frame = blank()
fd = ImageDraw.Draw(frame)
fd.rectangle([6 * S, 6 * S, (W - 6) * S, (H - 6) * S], outline=CYAN + (70,), width=int(2 * S))
img = Image.alpha_composite(img, frame)

final = img.convert("RGB").resize((W, H), Image.LANCZOS)
os.makedirs(os.path.dirname(OUT), exist_ok=True)
final.save(OUT, optimize=True)
print(f"Wrote {OUT} ({os.path.getsize(OUT) / 1024:.0f} KB, {W}x{H})")
