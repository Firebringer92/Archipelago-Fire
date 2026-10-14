"""
Adds new lightsaber crystal colors to the game and the AP gear loot pool:
Cyan, Orange, Bronze, Silver, Black (assets from Crixler's New Saber
Crystals Pack I V2.1, https://deadlystream.com)
plus Purple (built here from scratch, reusing that pack's own unused
`w_lsabrepurp01` texture -- the pack ships the texture but never wires it
to a model/crystal/2da row).

Confirmed live this session (via MDLOps, not guessing) that KotOR's
lightsaber blade color is texture-driven, not geometry-driven: the 5
vanilla single-blade models (w_lghtsbr_001 through _005) are byte-for-
byte identical in size, differing only in which texture their blade mesh
points at (e.g. `w_lsabreblue01` vs `w_lsabrered01`). `upcrystals.2da`'s
`shortmdlvar`/`longmdlvar`/`doublemdlvar` columns are .uti TEMPLATE
resrefs (not direct model resrefs) -- inserting a crystal into a hilt
reads that template's own ModelVariation field and applies it to the
player's hilt, which is why a new color needs a real (if trivial, since
geometry is identical) new .uti + model pair per saber type, not just a
new texture file.

Each of the 5 ported colors already has a matching real model/uti/
texture/icon set in the pack for all 3 saber forms (long/short/double) --
deployed verbatim. Purple only has a texture in the pack; its long-form
model/uti/icon are built here (clone of an existing one via MDLOps ascii
text-splice, matching the exact `fix_malak_basic_attack_animations.py`
technique already proven safe this session), using ModelVariation 17
(confirmed free -- vanilla uses 1-5 plus 7/8 for its own 2 unique story
crystals, this pack uses 6/9-16). Purple's short/double forms are NOT
built (real 3D work, out of scope for this pass) -- its upcrystals.2da
row points its short/double columns at Viridian's (dark green) as a
safe, non-crashing fallback: a Purple crystal inserted into a short or
double-bladed hilt renders as dark green for that hilt type instead of
purple, cosmetic-only, never an invalid/missing model reference.

Usage: python add_saber_crystal_colors.py [--game-dir=<path>] [--icons-only]
  --icons-only deploys just the icons: the crystal icons (Cyan/Orange/Bronze
  with a softened outline) and the saber hilt icons (the item icon the upgrade
  screen swaps to when a crystal changes the hilt's ModelVariation).
  Writes extender/raw_override_files/*.{uti,mdl,mdx,tga,txi} (checked-in
  source), extender/raw_override_files/upcrystals.2da, deploys everything
  to <game-dir>/Override, and updates
  Archipelago/worlds/kotor/gear_items.json (adds each crystal, does not
  touch or reorder existing entries).
"""
import json
import os
import shutil
import sys

from pykotor.extract.installation import Installation, SearchLocation
from pykotor.resource.formats.gff import read_gff, write_gff
from pykotor.resource.formats.twoda import read_2da, write_2da
from pykotor.resource.generics.uti import construct_uti, dismantle_uti
from pykotor.resource.type import ResourceType

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
RAW_OVERRIDE_DIR = os.path.join(REPO_ROOT, "extender", "raw_override_files")
PACK_DIR = os.path.join(
    REPO_ROOT, "tools", "mod_inspect", "crixler_sabers",
    "Crixlers_new_saber_crystals_pack1_V2.1", "Crixlers_new_saber_crystals_pack1_V2.1", "tslpatchdata",
)
MDLOPS_EXE = os.path.join(REPO_ROOT, "tools", "mdlops", "mdlops.exe")
WORK_DIR = os.path.join(REPO_ROOT, "tools", "mdlops", "saber_work")
GEAR_JSON_PATH = os.path.join(REPO_ROOT, "Archipelago", "worlds", "kotor", "gear_items.json")

# label -> (crystal uti, long/short/double uti, long/short/double model,
# texture, icon). Straight ports from the pack -- verified via changes.ini
# and direct decompile that each model's own bitmap matches its color name.
PORTED_COLORS = {
    "Cyan": dict(crystal="g_w_sbrcrstl22", long_uti="g_w_lghtsbr10", short_uti="g_w_shortsbr10",
                 dbl_uti="g_w_dblsbr010", long_mdl="w_lghtsbr_010", short_mdl="w_shortsbr_010",
                 dbl_mdl="w_dblsbr_010", texture="w_lsabrecyan01", icon="iw_sbrcrstl_022", cost=500),
    "Orange": dict(crystal="g_w_sbrcrstl23", long_uti="g_w_lghtsbr11", short_uti="g_w_shortsbr11",
                   dbl_uti="g_w_dblsbr011", long_mdl="w_lghtsbr_011", short_mdl="w_shortsbr_011",
                   dbl_mdl="w_dblsbr_011", texture="w_lsabreorng01", icon="iw_SbrCrstl_023", cost=500),
    "Bronze": dict(crystal="g_w_sbrcrstl25", long_uti="g_w_lghtsbr13", short_uti="g_w_shortsbr13",
                   dbl_uti="g_w_dblsbr013", long_mdl="w_lghtsbr_013", short_mdl="w_shortsbr_013",
                   dbl_mdl="w_dblsbr_013", texture="w_lsabrebrnz01", icon="iw_sbrcrstl_025", cost=500),
    "Silver": dict(crystal="g_w_sbrcrstl26", long_uti="g_w_lghtsbr14", short_uti="g_w_shortsbr14",
                   dbl_uti="g_w_dblsbr014", long_mdl="w_lghtsbr_014", short_mdl="w_shortsbr_014",
                   dbl_mdl="w_dblsbr_014", texture="w_lsabresilv01", icon="iw_sbrcrstl_026", cost=500),
    "Black": dict(crystal="g_w_sbrcrstl27", long_uti="g_w_lghtsbr15", short_uti="g_w_shortsbr15",
                  dbl_uti="g_w_dblsbr015", long_mdl="w_lghtsbr_015", short_mdl="w_shortsbr_015",
                  dbl_mdl="w_dblsbr_015", texture="w_lsabreblak01", icon="iw_SbrCrstl_027", cost=500),
}

# Purple: built here. Long form is real (cloned from Viridian's own model/
# uti, texture swapped); short/double deliberately fall back to Viridian's
# real assets instead of a broken/missing reference.
PURPLE_VARIATION = 17
PURPLE_LONG_MDL = "w_lghtsbr_017"
PURPLE_LONG_UTI = "g_w_lghtsbr17"
PURPLE_CRYSTAL = "g_w_sbrcrstl29"
PURPLE_ICON = "iw_sbrcrstl_024"  # reuse Viridian's icon shape -- see build_purple()'s own note
PURPLE_TEXTURE = "w_lsabrepurp01"
VIRIDIAN_SHORT_UTI = "g_w_shortsbr12"
VIRIDIAN_DBL_UTI = "g_w_dblsbr012"


# Saber hilt icons. The item icon of a weapon is iw_<itemclass>_<ModelVariation>,
# so inserting a crystal (which swaps the hilt's ModelVariation through
# upcrystals.2da) makes the upgrade screen look up a NEW icon for the saber;
# a missing one is drawn as a blank white square. One icon per hilt form per
# variation. Value: (icon prefix, model-name prefix to read the variation from).
_HILT_ICON_FORMS = (
    ("iw_lghtsbr_", "long_mdl"),
    ("iw_shortsbr_", "short_mdl"),
    ("iw_dblsbr_", "dbl_mdl"),
)
# Purple's long hilt (variation 17) has no icon in the pack; it is built from
# Viridian's (variation 12) with the glow re-tinted. Its short/double hilts are
# Viridian's real ones (variation 12, already green to match their model).
PURPLE_LONG_HILT_ICON = "iw_lghtsbr_017"
PURPLE_ICON_SOURCE = "iw_lghtsbr_012"
VIRIDIAN_HILT_ICONS = ("iw_shortsbr_012", "iw_dblsbr_012")


def _pack_icon_filename(stem: str) -> str:
    """The pack's own spelling of <stem>.tga (it mixes iw_Lghtsbr_010 and
    iw_lghtsbr_011); the deployed file keeps that spelling."""
    for fn in os.listdir(PACK_DIR):
        if fn.lower() == f"{stem}.tga":
            return fn
    raise RuntimeError(f"expected hilt icon missing from pack: {stem}.tga")


def _hilt_icon_stems() -> list:
    """Pack hilt icons to deploy verbatim: every form of every ported color,
    plus Viridian's short/double (Purple's fallbacks) and long (Purple's
    tint source)."""
    stems = []
    for spec in PORTED_COLORS.values():
        for prefix, key in _HILT_ICON_FORMS:
            variation = int(spec[key].rsplit("_", 1)[1])
            stems.append(f"{prefix}{variation:03d}")
    stems += list(VIRIDIAN_HILT_ICONS) + [PURPLE_ICON_SOURCE]
    return stems


def deploy_hilt_icons(override_dir: str) -> None:
    """Deploys the hilt icons above, then builds Purple's long-hilt icon by
    re-tinting Viridian's green glow."""
    import colorsys
    from PIL import Image

    stems = _hilt_icon_stems()
    for stem in stems:
        _copy_pack_file(_pack_icon_filename(stem), override_dir)
    print(f"  deployed {len(stems)} hilt icons")

    src = Image.open(os.path.join(PACK_DIR, _pack_icon_filename(PURPLE_ICON_SOURCE))).convert("RGBA")
    px = src.load()
    for y in range(src.height):
        for x in range(src.width):
            r, g, b, a = px[x, y]
            h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            # Only the saturated glow is green; the grey hilt is untouched.
            if s > 0.2 and 0.2 < h < 0.5:
                h = 0.78
                nr, ng, nb = colorsys.hsv_to_rgb(h, s, v)
                px[x, y] = (round(nr * 255), round(ng * 255), round(nb * 255), a)
    out_raw = os.path.join(RAW_OVERRIDE_DIR, f"{PURPLE_LONG_HILT_ICON}.tga")
    src.save(out_raw, format="TGA", rle=True)
    shutil.copy2(out_raw, os.path.join(override_dir, f"{PURPLE_LONG_HILT_ICON}.tga"))
    print(f"  built+deployed {PURPLE_LONG_HILT_ICON}.tga (Viridian's hilt, purple glow)")


def list_deployed_filenames() -> list:
    """Every filename deploy_ported_colors()/build_purple() write to
    RAW_OVERRIDE_DIR, derived from PORTED_COLORS/PURPLE_* rather than
    hand-listed a second time -- package_dist.py's EXTRA_RAW_FILES imports
    this so the packaged release can't silently drift out of sync with
    what this script actually deploys."""
    files = []
    for spec in PORTED_COLORS.values():
        files += [
            f"{spec['crystal']}.uti", f"{spec['long_uti']}.uti", f"{spec['short_uti']}.uti", f"{spec['dbl_uti']}.uti",
            f"{spec['long_mdl']}.mdl", f"{spec['long_mdl']}.mdx",
            f"{spec['short_mdl']}.mdl", f"{spec['short_mdl']}.mdx",
            f"{spec['dbl_mdl']}.mdl", f"{spec['dbl_mdl']}.mdx",
            f"{spec['texture']}.tga", f"{spec['texture']}.txi",
            f"{spec['icon']}.tga",
        ]
    files += [
        f"{PURPLE_LONG_MDL}.mdl", f"{PURPLE_LONG_MDL}.mdx",
        f"{PURPLE_TEXTURE}.tga", f"{PURPLE_TEXTURE}.txi",
        f"{PURPLE_LONG_UTI}.uti", f"{PURPLE_CRYSTAL}.uti",
        f"{PURPLE_ICON}.tga",
        f"{PURPLE_LONG_HILT_ICON}.tga",
    ]
    files += [_pack_icon_filename(stem) for stem in _hilt_icon_stems()]
    return files


def _arg_value(flag, default):
    for a in sys.argv[1:]:
        if a.startswith(flag + "="):
            return a.split("=", 1)[1]
    return default


def _copy_pack_file(basename: str, override_dir: str) -> None:
    src = os.path.join(PACK_DIR, basename)
    if not os.path.isfile(src):
        raise RuntimeError(f"expected pack file missing: {src}")
    dst_raw = os.path.join(RAW_OVERRIDE_DIR, basename)
    shutil.copy2(src, dst_raw)
    shutil.copy2(src, os.path.join(override_dir, basename))


# Pack crystal icons drawn with a heavy near-black rim that looks harsh next to
# vanilla's thin dark-tinted one. Their rim pixels are recoloured as a darker
# shade of the crystal's own colour. Silver, Black and Purple are left as they
# are (no visible rim problem).
SOFT_OUTLINE_COLORS = ("Cyan", "Orange", "Bronze")


def _luma(p) -> float:
    return 0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2]


def soften_icon_outline(path: str, darken: float = 0.55, luma_max: float = 70, radius: int = 3) -> None:
    """Rewrites the TGA at `path`: every dark pixel touching the transparent
    background takes the average colour of the lit pixels within `radius`,
    scaled by `darken`. Alpha is unchanged."""
    from PIL import Image

    im = Image.open(path).convert("RGBA")
    px = im.load()
    w, h = im.size
    out = im.copy()
    op = out.load()
    for y in range(h):
        for x in range(w):
            p = px[x, y]
            if p[3] == 0 or _luma(p) >= luma_max:
                continue
            touches_background = any(
                0 <= x + dx < w and 0 <= y + dy < h and px[x + dx, y + dy][3] < 128
                for dy in (-1, 0, 1) for dx in (-1, 0, 1)
            )
            if not touches_background:
                continue
            lit = [
                px[x + dx, y + dy]
                for dy in range(-radius, radius + 1) for dx in range(-radius, radius + 1)
                if 0 <= x + dx < w and 0 <= y + dy < h
                and px[x + dx, y + dy][3] > 200 and _luma(px[x + dx, y + dy]) >= luma_max
            ]
            if not lit:
                continue
            n = len(lit)
            op[x, y] = (
                int(sum(c[0] for c in lit) / n * darken),
                int(sum(c[1] for c in lit) / n * darken),
                int(sum(c[2] for c in lit) / n * darken),
                p[3],
            )
    out.save(path, format="TGA", rle=True)


def deploy_crystal_icon(label: str, spec: dict, override_dir: str) -> None:
    """Copies the pack's crystal icon to the raw dir and Override, softening
    its outline first for the colours in SOFT_OUTLINE_COLORS."""
    fn = f"{spec['icon']}.tga"
    _copy_pack_file(fn, override_dir)
    if label in SOFT_OUTLINE_COLORS:
        soften_icon_outline(os.path.join(RAW_OVERRIDE_DIR, fn))
        shutil.copy2(os.path.join(RAW_OVERRIDE_DIR, fn), os.path.join(override_dir, fn))


def deploy_ported_colors(override_dir: str) -> None:
    for label, spec in PORTED_COLORS.items():
        files = [
            f"{spec['crystal']}.uti", f"{spec['long_uti']}.uti", f"{spec['short_uti']}.uti", f"{spec['dbl_uti']}.uti",
            f"{spec['long_mdl']}.mdl", f"{spec['long_mdl']}.mdx",
            f"{spec['short_mdl']}.mdl", f"{spec['short_mdl']}.mdx",
            f"{spec['dbl_mdl']}.mdl", f"{spec['dbl_mdl']}.mdx",
            f"{spec['texture']}.tga", f"{spec['texture']}.txi",
        ]
        for fn in files:
            _copy_pack_file(fn, override_dir)
        deploy_crystal_icon(label, spec, override_dir)
        print(f"  deployed {label} ({len(files) + 1} files)")


def build_purple(game_dir: str, override_dir: str) -> None:
    """Clones Viridian's real long-form model+uti (same technique as
    fix_malak_basic_attack_animations.py: MDLOps ascii text-splice, not
    pykotor's write_mdl) and repoints the blade texture at the pack's own
    unused w_lsabrepurp01."""
    os.makedirs(WORK_DIR, exist_ok=True)
    for f in os.listdir(WORK_DIR):
        os.remove(os.path.join(WORK_DIR, f))

    src_mdl = os.path.join(PACK_DIR, "w_lghtsbr_012.mdl")
    src_mdx = os.path.join(PACK_DIR, "w_lghtsbr_012.mdx")
    work_mdl = os.path.join(WORK_DIR, "w_lghtsbr_012.mdl")
    shutil.copy2(src_mdl, work_mdl)
    shutil.copy2(src_mdx, os.path.join(WORK_DIR, "w_lghtsbr_012.mdx"))

    import subprocess
    subprocess.run([MDLOPS_EXE, "-k1", work_mdl], cwd=WORK_DIR, check=True, capture_output=True, text=True)
    ascii_path = os.path.join(WORK_DIR, "w_lghtsbr_012-ascii.mdl")
    with open(ascii_path, "r", encoding="utf-8", errors="surrogateescape") as f:
        text = f.read()

    occurrences_name = text.count("w_lghtsbr_012")
    occurrences_tex = text.count("w_lsabredgrn01")
    if occurrences_tex == 0:
        raise RuntimeError("found no 'w_lsabredgrn01' bitmap reference -- source model changed?")
    # Confirmed via direct inspection: 4 occurrences, all plain
    # "bitmap w_lsabredgrn01" lines -- a multi-layer glow effect (core +
    # glow planes), every one of which needs the same swap.
    print(f"  cloning w_lghtsbr_012 -> {PURPLE_LONG_MDL}: renaming {occurrences_name} model-name "
          f"reference(s), retexturing {occurrences_tex} bitmap reference(s) to {PURPLE_TEXTURE}")
    text = text.replace("w_lghtsbr_012", PURPLE_LONG_MDL)
    text = text.replace("w_lsabredgrn01", PURPLE_TEXTURE)
    with open(ascii_path, "w", encoding="utf-8", errors="surrogateescape") as f:
        f.write(text)

    result = subprocess.run([MDLOPS_EXE, "-k1", ascii_path], cwd=WORK_DIR, check=True,
                             capture_output=True, text=True)
    print(result.stdout)

    import glob
    # MDLOps names its output after the ASCII file it read (the original
    # "w_lghtsbr_012-ascii.mdl"), not the model's own internal name field
    # we just renamed -- confirmed by checking the actual work dir output.
    bin_candidates = glob.glob(os.path.join(WORK_DIR, "w_lghtsbr_012-ascii-*bin.mdl"))
    if not bin_candidates:
        raise RuntimeError("MDLOps did not produce a recompiled binary model -- compile failed?")
    bin_mdl = bin_candidates[0]
    bin_mdx = bin_mdl[:-4] + ".mdx"

    out_mdl = os.path.join(RAW_OVERRIDE_DIR, f"{PURPLE_LONG_MDL}.mdl")
    out_mdx = os.path.join(RAW_OVERRIDE_DIR, f"{PURPLE_LONG_MDL}.mdx")
    shutil.copy2(bin_mdl, out_mdl)
    shutil.copy2(bin_mdx, out_mdx)
    shutil.copy2(out_mdl, os.path.join(override_dir, f"{PURPLE_LONG_MDL}.mdl"))
    shutil.copy2(out_mdx, os.path.join(override_dir, f"{PURPLE_LONG_MDL}.mdx"))
    print(f"  wrote+deployed {PURPLE_LONG_MDL}.mdl/.mdx ({os.path.getsize(out_mdl)} bytes)")

    # Purple's own texture (already in the pack, just never wired up).
    _copy_pack_file(f"{PURPLE_TEXTURE}.tga", override_dir)
    _copy_pack_file(f"{PURPLE_TEXTURE}.txi", override_dir)

    # Clone the long-form .uti from Viridian's (g_w_lghtsbr12), same
    # ModelVariation-bump pattern as everywhere else in this pack.
    inst = Installation(game_dir)
    src_uti_path = os.path.join(PACK_DIR, "g_w_lghtsbr12.uti")
    with open(src_uti_path, "rb") as f:
        uti = construct_uti(read_gff(f.read()))
    uti.resref = uti.resref.__class__(PURPLE_LONG_UTI)
    uti.model_variation = PURPLE_VARIATION
    uti.tag = PURPLE_LONG_UTI
    with open(os.path.join(RAW_OVERRIDE_DIR, f"{PURPLE_LONG_UTI}.uti"), "wb") as f:
        write_gff(dismantle_uti(uti), f, ResourceType.UTI)
    shutil.copy2(os.path.join(RAW_OVERRIDE_DIR, f"{PURPLE_LONG_UTI}.uti"),
                 os.path.join(override_dir, f"{PURPLE_LONG_UTI}.uti"))
    print(f"  wrote+deployed {PURPLE_LONG_UTI}.uti (ModelVariation={PURPLE_VARIATION})")

    # Crystal item itself -- clone Viridian's crystal (g_w_sbrcrstl24),
    # rename + retitle + repoint ModelVariation to match.
    src_crystal_path = os.path.join(PACK_DIR, "g_w_sbrcrstl24.uti")
    with open(src_crystal_path, "rb") as f:
        crystal = construct_uti(read_gff(f.read()))
    crystal.resref = crystal.resref.__class__(PURPLE_CRYSTAL)
    crystal.tag = PURPLE_CRYSTAL
    crystal.model_variation = PURPLE_VARIATION
    from pykotor.common.language import LocalizedString
    crystal.name = LocalizedString.from_english("Crystal, Purple")
    crystal.description = LocalizedString.from_english(
        "Special: Upgrade Item, Lightsaber  Blade Color: Purple  A facetted crystal used in the "
        "constructing of a lightsaber. It glows faintly with an inner purple light."
    )
    with open(os.path.join(RAW_OVERRIDE_DIR, f"{PURPLE_CRYSTAL}.uti"), "wb") as f:
        write_gff(dismantle_uti(crystal), f, ResourceType.UTI)
    shutil.copy2(os.path.join(RAW_OVERRIDE_DIR, f"{PURPLE_CRYSTAL}.uti"),
                 os.path.join(override_dir, f"{PURPLE_CRYSTAL}.uti"))
    print(f"  wrote+deployed {PURPLE_CRYSTAL}.uti (crystal item)")

    # Icon -- reuse Viridian's crystal icon shape (a generic faceted-
    # crystal silhouette, not color-specific art) rather than author a
    # new one; every vanilla crystal icon is the same silhouette anyway,
    # only tinted, so this is a visually reasonable placeholder.
    _copy_pack_file("iw_sbrcrstl_024.tga", override_dir)


def patch_upcrystals(game_dir: str, override_dir: str) -> None:
    inst = Installation(game_dir)
    res = inst.resource("upcrystals", ResourceType.TwoDA, [SearchLocation.OVERRIDE, SearchLocation.CHITIN])
    twoda = read_2da(res.data)
    print(f"  source: {res.filepath} ({twoda.get_height()} existing rows)")

    existing_labels = {twoda.get_cell(i, "label") for i in range(twoda.get_height())}
    for label, spec in PORTED_COLORS.items():
        if label.upper() in existing_labels:
            print(f"  {label} row already present, skipping")
            continue
        twoda.add_row(None, {
            "label": label.upper(), "template": spec["crystal"],
            "shortmdlvar": spec["short_uti"], "longmdlvar": spec["long_uti"], "doublemdlvar": spec["dbl_uti"],
        })
        print(f"  added row: {label.upper()}")

    if "PURPLE" not in existing_labels:
        twoda.add_row(None, {
            "label": "PURPLE", "template": PURPLE_CRYSTAL,
            "shortmdlvar": VIRIDIAN_SHORT_UTI, "longmdlvar": PURPLE_LONG_UTI, "doublemdlvar": VIRIDIAN_DBL_UTI,
        })
        print("  added row: PURPLE (short/double fall back to Viridian's real assets)")

    out_path = os.path.join(RAW_OVERRIDE_DIR, "upcrystals.2da")
    with open(out_path, "wb") as f:
        write_2da(twoda, f)
    shutil.copy2(out_path, os.path.join(override_dir, "upcrystals.2da"))
    print(f"  wrote+deployed upcrystals.2da ({twoda.get_height()} total rows)")


def update_gear_items_json() -> None:
    with open(GEAR_JSON_PATH, encoding="utf-8") as f:
        gear = json.load(f)

    def _entry(resref, name, cost, desc):
        gear[resref] = {
            "name": name, "base_item_type": "Lightsaber_Crystals", "cost": cost,
            "first_seen_in": "CORE", "stack_limit": 99, "quest_dependent": False,
            "progression_dependent": False, "stat_modifiers": "", "description": desc,
            "included_as_item": True, "shop_randomize": True, "equipment_slot": "",
            "progression_suppression": "0",
        }

    added = []
    for label, spec in PORTED_COLORS.items():
        if spec["crystal"] in gear:
            continue
        desc = (f"Special: Upgrade Item, Lightsaber  Blade Color: {label}  A facetted crystal used "
                f"in the constructing of a lightsaber. It glows faintly with an inner {label.lower()} light.")
        _entry(spec["crystal"], f"Crystal, {label}", spec["cost"], desc)
        added.append(spec["crystal"])

    if PURPLE_CRYSTAL not in gear:
        _entry(PURPLE_CRYSTAL, "Crystal, Purple", 500,
               "Special: Upgrade Item, Lightsaber  Blade Color: Purple  A facetted crystal used in "
               "the constructing of a lightsaber. It glows faintly with an inner purple light.")
        added.append(PURPLE_CRYSTAL)

    with open(GEAR_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(gear, f, indent=4, sort_keys=True)
        f.write("\n")
    print(f"  gear_items.json: added {len(added)} new entries: {added}")


def main():
    game_dir = _arg_value("--game-dir", DEFAULT_GAME_DIR)
    override_dir = os.path.join(game_dir, "Override")

    if "--icons-only" in sys.argv[1:]:
        print("Deploying crystal icons...")
        for label, spec in PORTED_COLORS.items():
            deploy_crystal_icon(label, spec, override_dir)
        print("Deploying saber hilt icons...")
        deploy_hilt_icons(override_dir)
        print("Done.")
        return

    print("Deploying ported colors (Cyan/Orange/Bronze/Silver/Black)...")
    deploy_ported_colors(override_dir)

    print("Building Purple...")
    build_purple(game_dir, override_dir)

    print("Deploying saber hilt icons...")
    deploy_hilt_icons(override_dir)

    print("Patching upcrystals.2da...")
    patch_upcrystals(game_dir, override_dir)

    print("Updating gear_items.json...")
    update_gear_items_json()

    print("Done.")


if __name__ == "__main__":
    main()
