"""
Diagnostic only -- not a fix. Writes N_DarthMalak.mdl/.mdx back out via
the exact same read_mdl/write_mdl path fix_malak_basic_attack_
animations.py uses, with ZERO changes (no supermodel edit, no animation
edit), and deploys that as an Override.

Why: the last two live attempts (direct S_Male02 supermodel, then
S_Female02 mirroring Carth's own exact link) both crashed despite
passing every pykotor-object-level check available (node counts, anim
counts, bone names). That pattern points away from "wrong supermodel
choice" and toward either (a) write_mdl not round-tripping this specific
file safely at all, independent of what's being changed, or (b) the
engine refusing a supermodel on a type-F unique appearance regardless of
value. This isolates which: if an UNCHANGED round trip also crashes,
it's (a), a pykotor writer bug -- not a modeling decision to revisit.
If it doesn't crash, it's (b), and no amount of picking a different
supermodel will fix this path.

Usage: python test_malak_roundtrip_nochange.py [--game-dir=<path>]
"""
import os
import shutil
import sys

from pykotor.extract.installation import Installation
from pykotor.resource.formats.mdl import read_mdl, write_mdl
from pykotor.resource.type import ResourceType

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
RAW_OVERRIDE_DIR = os.path.join(REPO_ROOT, "extender", "raw_override_files")


def _arg_value(flag, default):
    for a in sys.argv[1:]:
        if a.startswith(flag + "="):
            return a.split("=", 1)[1]
    return default


def build(game_dir: str) -> None:
    inst = Installation(game_dir)
    mdl_res = inst.resource("N_DarthMalak", ResourceType.MDL)
    mdx_res = inst.resource("N_DarthMalak", ResourceType.MDX)
    print(f"  source: {mdl_res.filepath}")
    mdl = read_mdl(mdl_res.data, source_ext=mdx_res.data)
    print(f"  read OK: supermodel={mdl.supermodel!r} anims={len(mdl.animations)} -- NOT modifying anything")

    out_mdl_path = os.path.join(RAW_OVERRIDE_DIR, "N_DarthMalak.mdl")
    out_mdx_path = os.path.join(RAW_OVERRIDE_DIR, "N_DarthMalak.mdx")
    with open(out_mdl_path, "wb") as f_mdl, open(out_mdx_path, "wb") as f_mdx:
        write_mdl(mdl, f_mdl, ResourceType.MDL, f_mdx)
    print(f"  wrote {out_mdl_path} ({os.path.getsize(out_mdl_path)} bytes, "
          f"original was {len(mdl_res.data)} bytes)")

    override_dir = os.path.join(game_dir, "Override")
    for ext in ("mdl", "mdx"):
        shutil.copy2(os.path.join(RAW_OVERRIDE_DIR, f"N_DarthMalak.{ext}"),
                     os.path.join(override_dir, f"N_DarthMalak.{ext}"))
    print(f"  deployed unchanged round-trip -> {override_dir}\\N_DarthMalak.mdl/.mdx")


if __name__ == "__main__":
    build(_arg_value("--game-dir", DEFAULT_GAME_DIR))
