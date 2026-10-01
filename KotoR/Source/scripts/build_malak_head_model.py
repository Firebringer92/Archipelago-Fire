"""
Builds p_malakh.mdl/.mdx -- Options.py's NewCompanion=malak head model --
by splicing Malak's real head geometry into Carth's own, proven-working
separable head model (p_CarthH), rather than reconstructing a new file
from Malak's original boss model (n_darthmalak_ap) via pykotor's own
writer end to end.

Why: two earlier attempts (a skinned-mesh graft, then a rigid-mesh
conversion of Malak's own head) both deployed without visible errors but
never actually rendered in-game ("head still not there"). A static audit
of the rigid-mesh attempt found nothing wrong -- correct 2DA wiring
(appearance.2da/heads.2da), correct node hierarchy shape (matches p_CarthH's
own torso_g -> ... -> head_g chain), real 690-vertex/750-face geometry,
a texture reference that genuinely resolves (N_DarthMalakh01, in the game's
own texture packs, same name the ORIGINAL n_darthmalak_ap.mdl already uses
for this exact mesh) -- yet it still didn't render. That points at
something pykotor's write_mdl gets subtly wrong in a way its own reader
doesn't catch on round-trip (this project has one other already-confirmed
write_mdl bug, corrupting bind-pose data for a modified skinned mesh --
plausibly not the only one).

This splice minimizes exposure to that risk: start from p_CarthH's own
MDL, ALREADY proven to render correctly as a companion's separable head
every time the player plays Carth, and change only ONE thing -- the
head_g node's mesh object, replaced wholesale with Malak's real head
geometry (vertex positions/normals/UVs/faces/texture, pulled directly
from his own original n_darthmalak_ap.mdl, the same source both earlier
attempts used). Every other node -- hierarchy, positions, controllers,
the whole face/jaw/eye rig -- stays exactly Carth's own, byte-for-byte
equivalent to what already works. Confirmed via round-trip: writing
Carth's own MDL back out with ZERO modifications preserves node count,
per-node controller count, and per-mesh vertex/face count exactly, so
this specific file's write path is not obviously lossy the way the
skinned-mesh bug is.

KNOWN LIMITATION, deliberately not addressed this pass: Carth's OWN
facial-detail child nodes (eyebrows, eyes, jaw, teeth, tongue, hair) are
left untouched, sized and positioned for Carth's own face -- they will
look wrong sitting on Malak's differently-shaped head. This script only
answers the question "does the swapped head_g mesh render at all" --
mapping every facial-detail sub-mesh onto Malak's own equivalents (a much
bigger, different-shaped job, and his own naming doesn't line up 1:1 with
Carth's) is follow-up work once the core technique is confirmed live.

Usage: python build_malak_head_model.py [--game-dir=<path>]
  Writes extender/raw_override_files/p_malakh.mdl/.mdx (checked-in source)
  and deploys them to <game-dir>/Override.
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


def _find_node(node, name):
    if node.name == name:
        return node
    for child in node.children:
        found = _find_node(child, name)
        if found is not None:
            return found
    return None


def build(game_dir: str) -> None:
    inst = Installation(game_dir)

    carth_mdl_res = inst.resource("p_CarthH", ResourceType.MDL)
    carth_mdx_res = inst.resource("p_CarthH", ResourceType.MDX)
    carth = read_mdl(carth_mdl_res.data, source_ext=carth_mdx_res.data)

    malak_mdl_res = inst.resource("n_darthmalak_ap", ResourceType.MDL, [])
    if malak_mdl_res is None:
        # n_darthmalak_ap isn't a stock resource -- it's this project's own
        # checked-in copy of Malak's real boss model (extender/raw_
        # override_files/), same source both earlier attempts pulled from.
        with open(os.path.join(RAW_OVERRIDE_DIR, "n_darthmalak_ap.mdl"), "rb") as f:
            malak_mdl_data = f.read()
        with open(os.path.join(RAW_OVERRIDE_DIR, "n_darthmalak_ap.mdx"), "rb") as f:
            malak_mdx_data = f.read()
    else:
        malak_mdl_data = malak_mdl_res.data
        malak_mdx_data = inst.resource("n_darthmalak_ap", ResourceType.MDX, []).data
    malak = read_mdl(malak_mdl_data, source_ext=malak_mdx_data)

    carth_head_g = _find_node(carth.root, "head_g")
    if carth_head_g is None:
        raise RuntimeError("p_CarthH has no 'head_g' node -- template shape changed?")
    malak_head = _find_node(malak.root, "head")
    if malak_head is None or malak_head.mesh is None:
        raise RuntimeError("n_darthmalak_ap has no 'head' mesh node -- source changed?")

    print(f"  splicing: head_g {len(carth_head_g.mesh.vertex_positions)} verts "
          f"-> {len(malak_head.mesh.vertex_positions)} verts "
          f"(texture {carth_head_g.mesh.texture_1} -> {malak_head.mesh.texture_1})")
    carth_head_g.mesh = malak_head.mesh

    carth.name = "p_malakh"

    out_mdl_path = os.path.join(RAW_OVERRIDE_DIR, "p_malakh.mdl")
    out_mdx_path = os.path.join(RAW_OVERRIDE_DIR, "p_malakh.mdx")
    with open(out_mdl_path, "wb") as f_mdl, open(out_mdx_path, "wb") as f_mdx:
        write_mdl(carth, f_mdl, ResourceType.MDL, f_mdx)
    print(f"  wrote {out_mdl_path} ({os.path.getsize(out_mdl_path)} bytes)")
    print(f"  wrote {out_mdx_path} ({os.path.getsize(out_mdx_path)} bytes)")

    override_dir = os.path.join(game_dir, "Override")
    for ext in ("mdl", "mdx"):
        shutil.copy2(os.path.join(RAW_OVERRIDE_DIR, f"p_malakh.{ext}"),
                     os.path.join(override_dir, f"p_malakh.{ext}"))
    print(f"  deployed -> {override_dir}\\p_malakh.mdl/.mdx")


if __name__ == "__main__":
    build(_arg_value("--game-dir", DEFAULT_GAME_DIR))
