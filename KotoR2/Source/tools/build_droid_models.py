"""Builds the four droid models that carry human animations in KotOR 2: the assassin droid (ap_drdassn), the Mining Droid Mk II (ap_drdmine), the war droid (ap_drdwar) and the
protocol droid (ap_drdprot).

Why: a creature droid model (modeltype L) has only its own few droid animations, so a droid made into a party member cannot swing a melee weapon or a lightsaber.
Every human animation is stored in the human supermodel chain (S_Female02 -> S_Female01 -> S_Male02 -> S_Male01) and plays on any model that names that chain as its
supermodel and has bones of the same names. So the droid's body is re-mounted on a human skeleton:
  1. the donor is N_DarkJediM, a full (type F) human model. Its bone nodes are kept, its visible meshes (4 skins, eyes) are dropped;
  2. the droid is scaled to the donor's root height, and the arms are rotated about the shoulders to hang along the donor's arm direction (the human clips are written
     against the donor's rest pose, so a droid whose arms rest differently would be moved wrongly by them);
  3. each donor bone's joint moves to the matching droid joint (donor bone orientations are kept, the animation keys are written against them), and every droid piece is
     attached to its donor bone with a transform that leaves it exactly where it sat on the droid at rest (vertices are not touched);
  4. a droid skin mesh becomes a rigid piece on one bone (a skin's bone indices do not survive the swap of the skeleton);
  5. the donor's weapon and effect hooks (rhand, lhand, impact, handconjure ...) move to the droid's own, or to the middle of its hand;
  6. the result is renamed and compiled with MDLOps. It has no animations of its own; they all come from the supermodel.
A droid whose arm ends in something other than a hand (the Mining Droid Mk II's left arm is a cannon) gets a mirrored copy of its other hand in place of it (mirror_hand).
The same technique and the same per-droid CONFIG layout as the KotOR 1 builder; the model files and the donor differ in K2 (see the notes by each CONFIG).

Depends on: pykotor and numpy; MDLOps (Perl-based, GPL) found through the folder K2_MDLOPS_DIR (default DEFAULT_MDLOPS_DIR), which must hold mdlops.exe; the game's own
files (the droid models, n_darkjedim and the four supermodels are read from the install, nothing is stored here). The result is two files per model, <name>.mdl and
<name>.mdx, plus the appearance.2da rows that host them (appearance_rows). Nothing is ever written to the game folder.

  python tools/build_droid_models.py [assassin|mining|war|protocol|all] [--game-dir PATH] [--out DIR]       (default out: client/models_out, never the game's Override)
  build(game_dir, out_dir, which, log=None) -> ({file name: bytes}, [problems])
  appearance_rows(game_dir) -> (appearance.2da bytes, {key: description of the row})
"""
import argparse
import glob
import logging
import math
import os
import re
import subprocess
import sys
import tempfile
import typing

try:
    import numpy as np
except ImportError:           # reported as a problem by build(), not an import error
    np = None

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
DEFAULT_GAME_DIR = os.environ.get("K2_GAME_DIR") or r"C:\Program Files (x86)\Steam\steamapps\common\Knights of the Old Republic II"
DEFAULT_OUT_DIR = os.path.join(ROOT, "client", "models_out")
# MDLOps is GPL and is not part of the repository: the release zip carries it unchanged in tools/mdlops (with its licence, readme, tutorials and Perl source). The
# environment variable K2_MDLOPS_DIR names another folder that holds mdlops.exe.
DEFAULT_MDLOPS_DIR = os.path.join(ROOT, "tools", "mdlops")
MDLOPS_TIMEOUT = 300           # seconds per run; MDLOps normally needs a second or two. It runs with no stdin so it cannot wait on an inherited one.

DONOR = "n_darkjedim"
SUPERMODEL_CHAIN = ("S_Female02", "S_Female01", "S_Male02", "S_Male01")     # what the donor's supermodel name leads to; compiling needs these binaries beside the ascii
SUFFIX = "_ap"                 # added to a droid node whose name is also a donor or animated node name

# Each CONFIG: the droid model (resource), the new model (new), the appearance.2da row that hosts it (host_row) and the row whose settings it takes over (source_row).
#   map            droid node -> donor bone it rides on
#   skip           the droid's root helpers, not carried over
#   shared_hooks   hooks both models have: the donor's node moves onto the droid's position and the droid's is not carried over
#   drop_kinds / drop_nodes   node kinds and nodes left out (with everything below them)
#   skin_anchor    droid skin mesh -> droid node (in map) whose donor bone carries it as a rigid piece
#   hook_hand_nodes  donor hook (rhand, lhand) -> droid nodes whose bounding box centre is where it is placed; hook_drop lowers it (metres)
#   repose         arm chains rotated about their first node so the chain points along the donor's (start..end) arm
#   mirror_hand    (optional) a hand built as the mirror image of the droid's other hand: source/target hand node, names of the copies (every node below the source hand and every
#                  listed skin gets one). The mirror plane's x is halfway between the two wrists; the target node's own mesh (a cannon) is replaced by the mirrored palm.
#   hook_follow    droid dummy -> donor hook name whose place (the middle of that hook's hand pieces) the dummy is moved to
# The host rows must be rows nothing else uses (the tests check this): 82 and 29 are blank rows, 58 is the cut "Droid_Nul" row, 380 is the cut "Twilek_Jedi_Male" row. Rows 91 and up
# are the PLAYER's body rows (portraits.2da hands them to the character generator) and row 27 is one of the looks of the generated companions (data/extra_companions.json): none of
# those may host a model.
CONFIGS = {
    # K2's c_drdassassin has the same 50 nodes with the same names as the K1 model the K1 CONFIG was written for, so the CONFIG is the same.
    "assassin": dict(
        resource="c_drdassassin", new="ap_drdassn", host_row=82, source_row=56, label="AP_ap_drdassn",
        map={"pelvis": "pelvis_g", "Box01": "torso_g", "torso": "torsoUpr_g", "head": "head_g",
             "r_shlder": "rcollar_g", "r_delt": "rbicep_g", "r_frarm": "rforearm_g", "r_hand": "rhand_g",
             "r_shlder01": "lcollar_g", "r_delt01": "lbicep_g", "r_frarm01": "lforearm_g", "r_hand01": "lhand_g",
             "r_thigh": "rthigh_g", "r_calf": "rshin_g", "r_foot": "rfoot_g", "r_toe": "rfootT_g",
             "l_thigh": "lthigh_g", "l_calf": "lshin_g", "l_foot": "lfoot_g", "l_toe": "lfootT_g"},
        skip={"C_DrdAssassin", "cutscenedummy", "rootdummy"},
        shared_hooks=("Impact", "camerahook", "headconjure"),
        drop_kinds=("emitter", "light"),
        # the held repeating blaster and its helpers are left out (they also take the rhdold helper under them)
        drop_nodes=("RptBlstr", "rhdold"),
        skin_anchor={},
        # the weapon hooks sit at the centre of each hand piece (the donor's own offset puts the grip above this droid's hands), then drop by hook_drop metres
        hook_hand_nodes={"rhand": ("r_hand",), "lhand": ("r_hand01",)},
        hook_drop=0.03,
        # both arms rest straight out sideways (a T-pose)
        repose=[dict(start="r_delt", end="r_hand", donor_start="rbicep_g", donor_end="rhand_g"),
                dict(start="r_delt01", end="r_hand01", donor_start="lbicep_g", donor_end="lhand_g")],
    ),
    # The Mining Droid Mk II is a tall humanoid (pelvis_g, torso_g, head_g, arms with a forearm and a hand each, legs with a toe piece) whose visible waist, neck and
    # right-hand finger geometry are skin meshes (the finger, waist and collision pieces under them are render-off). Its torso piece is the whole upper body, so it
    # rides on the donor's upper torso and the waist piece on the donor's lower torso. Its node names equal donor bone names (pelvis_g, torso_g, head_g, lhand_g,
    # RafngrB_g ...): those droid nodes are renamed with SUFFIX so the output holds one node of each name. Its left arm is a cannon (lhand_g, no fingers, the muzzle dummies
    # handconjure and rbullet at its tip): the cannon is replaced by a mirrored copy of the right hand (palm, the six finger pieces and the visible finger skin), the muzzle
    # dummy rbullet is left out and handconjure moves to the middle of the new hand.
    "mining": dict(
        resource="c_mk2_drd", new="ap_drdmine", host_row=58, source_row=461, label="AP_ap_drdmine",
        map={"pelvis_g": "pelvis_g", "waist01": "torso_g", "torso_g": "torsoUpr_g", "head_g": "head_g",
             "leftUprarm": "lbicep_g", "lforearm_g": "lforearm_g", "lhand_g": "lhand_g",
             "ruprarm": "rbicep_g", "rforearm_g": "rforearm_g", "rhand_g": "rhand_g",
             "lthigh": "lthigh_g", "lshin": "lshin_g", "lfoot": "lfoot_g", "lfoor_T": "lfootT_g",
             "rthigh": "rthigh_g", "rshin": "rshin_g", "rfoot": "rfoot_g", "rfoot_T": "rfootT_g"},
        skip={"C_MK2_DRD", "cutscenedummy", "rootdummy"},
        shared_hooks=("impact", "camerahook", "headconjure", "talkdummy", "handconjure"),
        drop_kinds=(),
        drop_nodes=("rbullet",),
        # the visible neck sleeve follows the head, the visible waist sleeve the lower torso, the visible fingers of each hand that hand
        skin_anchor={"waist": "waist01", "fingers": "rhand_g", "neck": "head_g", "lfingers": "lhand_g"},
        mirror_hand=dict(source="rhand_g", target="lhand_g", skins={"fingers": "lfingers"},
                         names={"RafngrB_g": "LafngrB_g", "RafngrT_g": "LafngrT_g", "RbfngrB_g": "LbfngrB_g", "RbfngrT_g": "LbfngrT_g",
                                "RcfngrB_g": "LcfngrB_g", "RcfngrT_g": "LcfngrT_g"}),
        # each hand holds weapons: the middle of the palm and the three finger bases
        hook_hand_nodes={"rhand": ("rhand_g", "RafngrB_g", "RbfngrB_g", "RcfngrB_g"), "lhand": ("lhand_g", "LafngrB_g", "LbfngrB_g", "LcfngrB_g")},
        hook_drop=0.0,
        hook_follow={"handconjure": "lhand"},
        # the arms hang almost straight down, the donor's rest arms point outward: rotated to the donor's direction
        repose=[dict(start="ruprarm", end="rhand_g", donor_start="rbicep_g", donor_end="rhand_g"),
                dict(start="leftUprarm", end="lhand_g", donor_start="lbicep_g", donor_end="lhand_g")],
    ),
    # The war droid (K2 row 66): belly, chest, neck, head, two arms (upper, lower, a hand with two fingers and a thumb) and legs without toes. Its right hand holds a baked-in
    # repeating blaster (RptBlstr, with the helpers Dummy01, Dummy02, rbullet and handconjure under it) that is left out. Its arms already hang outward and down along nearly the
    # donor's arm line, so the re-pose only turns them a few degrees.
    "war": dict(
        resource="c_drdwar", new="ap_drdwar", host_row=29, source_row=66, label="AP_ap_drdwar",
        map={"Groin": "pelvis_g", "Belly": "torso_g", "Chest": "torsoUpr_g", "Neck": "neck_g", "Head": "head_g",
             "R_UpperArm": "rbicep_g", "R_LowerArm": "rforearm_g", "RHandDrd": "rhand_g",
             "L_UpperArm": "lbicep_g", "L_LowerArm": "lforearm_g", "LHandDrd": "lhand_g",
             "R_Thigh": "rthigh_g", "R_Shin": "rshin_g", "R_Foot": "rfoot_g",
             "L_Thigh": "lthigh_g", "L_Shin": "lshin_g", "L_Foot": "lfoot_g"},
        skip={"C_DrdWar", "cutscenedummy", "rootdummy"},
        shared_hooks=("Impact", "camerahook", "headconjure", "talkdummy"),
        drop_kinds=("emitter", "light"),
        drop_nodes=("RptBlstr",),
        skin_anchor={},
        # the weapon hooks sit in the middle of the palm and the two finger bases of each hand
        hook_hand_nodes={"rhand": ("RHandDrd", "RFngr01", "RFngr02"), "lhand": ("LHandDrd", "LFngr1", "LFngr02")},
        hook_drop=0.0,
        repose=[dict(start="R_UpperArm", end="RHandDrd", donor_start="rbicep_g", donor_end="rhand_g"),
                dict(start="L_UpperArm", end="LHandDrd", donor_start="lbicep_g", donor_end="lhand_g")],
    ),
    # The protocol droid (K2 row 63): torso, head with two eyes, shoulder cylinders, arms (shoulder piece, forearm, a hand with two fingers and a thumb) held straight out sideways
    # (a T-pose, like the assassin) and legs with pistons. Nothing is held in the hands. The model has two pairs of same-named nodes (Rwr_box and Lwr_box: the second of each is
    # renamed) and a copy of the left hand's shape (ShadowGeo, riding on the forearm, so it would stay behind when the hand moves: it is left out).
    "protocol": dict(
        resource="c_drdprot", new="ap_drdprot", host_row=380, source_row=63, label="AP_ap_drdprot",
        map={"Hip": "pelvis_g", "Torso": "torsoUpr_g", "Head": "head_g",
             "R_Shldr": "rbicep_g", "R4rm": "rforearm_g", "RHnd": "rhand_g",
             "L_Shldr": "lbicep_g", "L4rm": "lforearm_g", "LHand": "lhand_g",
             "RThigh": "rthigh_g", "RLeg": "rshin_g", "RFoot": "rfoot_g",
             "LThigh": "lthigh_g", "LLeg": "lshin_g", "LFoot": "lfoot_g"},
        skip={"C_DrdProt", "cutscenedummy", "RootDummy"},
        shared_hooks=("Impact", "camerahook", "headconjure", "talkdummy"),
        drop_kinds=("emitter", "light"),
        drop_nodes=("ShadowGeo",),
        skin_anchor={},
        hook_hand_nodes={"rhand": ("RHnd", "RFngr1", "RFngr2"), "lhand": ("LHand", "LFngr1", "LFngr2")},
        hook_drop=0.0,
        # The protocol droid's own row is a slow shuffler (walk 0.6, run 0.7, moverate SLOW): the human clips are written for a body that covers 1.75 and 3.75 metres a cycle, so on
        # that row every movement clip played at the wrong pace. The host row takes the war droid's movement values, which belong to the same human-rig body plan.
        row_cells=dict(walkdist="1.75", rundist="3.75", moverate="NORM", hitradius="0.2", deathvfx="4034", deathvfxnode="impact"),
        repose=[dict(start="R_Shldr", end="RHnd", donor_start="rbicep_g", donor_end="rhand_g"),
                dict(start="L_Shldr", end="LHand", donor_start="lbicep_g", donor_end="lhand_g")],
    ),
}
ORDER = ("assassin", "mining", "war", "protocol")


# ---------------------------------------------------------------------------------------------------------------- maths
def rot(axis_angle):
    x, y, z, a = axis_angle
    n = math.sqrt(x * x + y * y + z * z)
    if n < 1e-9 or abs(a) < 1e-9:
        return np.eye(3)
    x, y, z = x / n, y / n, z / n
    c, s, t = math.cos(a), math.sin(a), 1 - math.cos(a)
    return np.array([[t * x * x + c, t * x * y - s * z, t * x * z + s * y],
                     [t * x * y + s * z, t * y * y + c, t * y * z - s * x],
                     [t * x * z - s * y, t * y * z + s * x, t * z * z + c]])


def axis_angle(m):
    """3x3 rotation -> (x, y, z, angle)"""
    cos_a = max(-1.0, min(1.0, (np.trace(m) - 1) / 2))
    a = math.acos(cos_a)
    if a < 1e-4:            # an identity with numeric noise: its axis is meaningless, and MDLOps writes such an orientation as a half turn
        return (0.0, 0.0, 1.0, 0.0)
    if abs(a - math.pi) < 1e-6:
        w, v = np.linalg.eigh((m + np.eye(3)) / 2)
        ax = v[:, np.argmax(w)]
        return (float(ax[0]), float(ax[1]), float(ax[2]), math.pi)
    ax = np.array([m[2, 1] - m[1, 2], m[0, 2] - m[2, 0], m[1, 0] - m[0, 1]]) / (2 * math.sin(a))
    ax /= np.linalg.norm(ax)
    return (float(ax[0]), float(ax[1]), float(ax[2]), a)


def mat4(pos, rot3):
    m = np.eye(4)
    m[:3, :3] = rot3
    m[:3, 3] = pos
    return m


# ------------------------------------------------------------------------------------------------------------ ascii parse
NODE_RE = re.compile(r"(?ms)^[ \t]*node (\w+) (\S+)[ \t]*\n(.*?)^[ \t]*endnode[ \t]*\n")


def split_geometry(text):
    head, rest = text.split("beginmodelgeom", 1)
    geo, tail = rest.split("endmodelgeom", 1)
    first_line, geo = geo.split("\n", 1)   # " <model name>" remainder of the beginmodelgeom line
    return head + "beginmodelgeom", first_line, geo, "endmodelgeom" + tail


class Node:
    def __init__(self, kind, name, body):
        self.kind, self.name = kind, name
        self.parent = re.search(r"(?m)^[ \t]*parent (\S+)", body).group(1)
        p = re.search(r"(?m)^[ \t]*position[ \t]+(\S+)[ \t]+(\S+)[ \t]+(\S+)", body)
        o = re.search(r"(?m)^[ \t]*orientation[ \t]+(\S+)[ \t]+(\S+)[ \t]+(\S+)[ \t]+(\S+)", body)
        self.pos = np.array([float(v) for v in p.groups()]) if p else np.zeros(3)
        self.ori = tuple(float(v) for v in o.groups()) if o else (0.0, 0.0, 1.0, 0.0)
        self.rest = re.sub(r"(?m)^[ \t]*(parent|position|orientation)[ \t].*\n", "", body)   # everything else


def parse_nodes(geo):
    nodes, order = {}, []
    for m in NODE_RE.finditer(geo):
        n = Node(m.group(1), m.group(2), m.group(3))
        nodes[n.name] = n
        order.append(n.name)
    return nodes, order


def global_mats(nodes):
    cache = {}

    def g(name):
        if name in cache:
            return cache[name]
        n = nodes[name]
        base = np.eye(4) if n.parent == "NULL" or n.parent not in nodes else g(n.parent)
        cache[name] = base @ mat4(n.pos, rot(n.ori))
        return cache[name]
    for name in nodes:
        g(name)
    return cache


def children_of(nodes):
    out = {}
    for n in nodes.values():
        out.setdefault(n.parent, []).append(n.name)
    return out


def fmt_node(n):
    lines = [f"node {n.kind} {n.name}", f"  parent {n.parent}",
             f"  position  {n.pos[0]:.7g} {n.pos[1]:.7g} {n.pos[2]:.7g}",
             f"  orientation  {n.ori[0]:.7g} {n.ori[1]:.7g} {n.ori[2]:.7g} {n.ori[3]:.7g}"]
    return "\n".join(lines) + "\n" + n.rest.rstrip("\n") + "\nendnode\n"


def scale_mesh_text(rest, f):
    """Scales the geometry in a node's non-transform text: verts, bmin, bmax, average, radius (UVs and faces untouched)."""
    out, in_verts = [], 0
    for line in rest.split("\n"):
        t = line.strip()
        m = re.match(r"(bmin|bmax|average)\s+(\S+)\s+(\S+)\s+(\S+)$", t)
        if in_verts:
            v = [float(x) * f for x in t.split()[:3]]
            out.append(f"    {v[0]:.7g} {v[1]:.7g} {v[2]:.7g}")
            in_verts -= 1
        elif m:
            v = [float(x) * f for x in m.groups()[1:]]
            out.append(f"  {m.group(1)} {v[0]:.7g} {v[1]:.7g} {v[2]:.7g}")
        elif re.match(r"radius\s+\S+$", t):
            out.append(f"  radius {float(t.split()[1]) * f:.7g}")
        elif re.match(r"verts\s+\d+$", t):
            in_verts = int(t.split()[1])
            out.append(line)
        else:
            out.append(line)
    return "\n".join(out)


def strip_weights(rest):
    """Removes a skin mesh's 'weights N' block (the header line and its N per-vertex lines)."""
    out, skip = [], 0
    for line in rest.split("\n"):
        t = line.strip()
        if skip:
            skip -= 1
            continue
        if re.match(r"weights\s+\d+$", t):
            skip = int(t.split()[1])
            continue
        out.append(line)
    return "\n".join(out)


def mesh_points(node, g):
    """The mesh's vertices in model space (g = the node's global matrix)."""
    m = re.search(r"(?m)^[ \t]*verts[ \t]+(\d+)\s*\n((?:[ \t]+\S+[ \t]+\S+[ \t]+\S+[ \t]*\n)+)", node.rest)
    if not m:
        return np.zeros((0, 3))
    v = np.array([[float(x) for x in ln.split()[:3]] for ln in m.group(2).strip().splitlines()[: int(m.group(1))]])
    return (g[:3, :3] @ v.T).T + g[:3, 3]


def unique_node_names(geo):
    """The geometry text with every repeated node name made unique. A model can hold two nodes of one name under different parents (the protocol droid's Rwr_box); the first keeps
    the name, each later one is renamed NAME_2, NAME_3 ..., and a child that names the repeated name as its parent follows the most recent node of that name (the nodes are listed
    depth first, so that is the one it hangs under). Returns (text, [(old name, new name)])."""
    count, latest, used, renamed, out, last = {}, {}, set(), [], [], 0
    all_names = {m.group(2).lower() for m in NODE_RE.finditer(geo)}
    for m in NODE_RE.finditer(geo):
        out.append(geo[last:m.start()])
        last = m.end()
        name, text = m.group(2), m.group(0)
        pm = re.search(r"(?m)^[ \t]*parent (\S+)", text)
        if pm and pm.group(1) in latest and latest[pm.group(1)] != pm.group(1):
            text = text[:pm.start(1)] + latest[pm.group(1)] + text[pm.end(1):]
        key = name.lower()
        count[key] = count.get(key, 0) + 1
        unique = name
        if count[key] > 1:
            n = count[key]
            unique = f"{name}_{n}"
            while unique.lower() in used or unique.lower() in all_names:
                n += 1
                unique = f"{name}_{n}"
            renamed.append((name, unique))
            hm = re.search(r"(?m)^[ \t]*node \w+ (\S+)", text)
            text = text[:hm.start(1)] + unique + text[hm.end(1):]
        used.add(unique.lower())
        latest[name] = unique
        out.append(text)
    out.append(geo[last:])
    return "".join(out), renamed


def mirror_mesh_text(rest, T):
    """A mesh node's non-transform text with its geometry carried through the 4x4 matrix T, which must be a reflection (determinant below zero): the vertices are moved, bmin,
    bmax and average follow, and every face's winding is reversed (vertices 2 and 3 swap, and their UV indices with them), because a reflection turns a triangle inside out.
    Normals and tangents are not stored in the ascii (MDLOps derives them from the faces), so there is nothing else to carry. Everything else is copied."""
    lines = rest.split("\n")
    vi = next((i for i, ln in enumerate(lines) if re.match(r"\s*verts\s+\d+\s*$", ln)), None)
    if vi is None:
        raise RuntimeError("a mesh without vertices cannot be mirrored")
    if np.linalg.det(T[:3, :3]) >= 0:
        raise RuntimeError("mirror_mesh_text needs a reflection")
    nv = int(lines[vi].split()[1])
    pts = np.array([[float(x) for x in lines[vi + 1 + k].split()[:3]] for k in range(nv)])
    moved = (T[:3, :3] @ pts.T).T + T[:3, 3]
    out, k = [], 0
    while k < len(lines):
        ln, t = lines[k], lines[k].strip()
        m = re.match(r"(bmin|bmax|average)\s+(\S+)\s+(\S+)\s+(\S+)$", t)
        if k == vi:
            out.append(ln)
            for row in moved:
                out.append(f"    {row[0]:.7g} {row[1]:.7g} {row[2]:.7g}")
            k += 1 + nv
            continue
        if m:
            if m.group(1) == "bmin":
                v = moved.min(axis=0)
            elif m.group(1) == "bmax":
                v = moved.max(axis=0)
            else:
                v = (T[:3, :3] @ np.array([float(x) for x in m.groups()[1:]])) + T[:3, 3]
            out.append(f"  {m.group(1)} {v[0]:.7g} {v[1]:.7g} {v[2]:.7g}")
        elif re.match(r"faces\s+\d+$", t):
            nf = int(t.split()[1])
            out.append(ln)
            for j in range(nf):
                f = lines[k + 1 + j].split()
                f[1], f[2] = f[2], f[1]            # vertex 2 <-> vertex 3
                f[5], f[6] = f[6], f[5]            # and their UV indices
                out.append("    " + " ".join(f))
            k += 1 + nf
            continue
        else:
            out.append(ln)
        k += 1
    return "\n".join(out)


def mirror_hand(mh, d_nodes, d_order, dg):
    """Builds a hand as the mirror image of the droid's other hand. mh: source (the model's good hand node), target (the other hand node, whose own mesh is replaced), names
    (new name of every node below the source) and skins (source skin mesh -> new name). The mirror plane is x = halfway between the two wrists, then moved so the mirrored wrist lands
    exactly on the target's wrist. The target node keeps its place; the new nodes hang under it (a copy of a node below the source hangs under the copy of its parent). Each new
    node's frame is the mirrored frame with its x axis flipped (so it stays a proper rotation), which makes its vertices the source's with x negated. dg (the global matrices) is
    not changed. Changes d_nodes and d_order in place; returns a note."""
    src, dst = mh["source"], mh["target"]
    names, skins = mh["names"], mh.get("skins", {})
    below, stack = [], [src]
    while stack:
        cur = stack.pop(0)
        below.append(cur)
        stack += [o for o in d_order if d_nodes[o].parent == cur]
    missing = [n for n in below[1:] if n not in names]
    if missing or [n for n in names if n not in below]:
        raise RuntimeError(f"mirror_hand: the names must cover exactly the nodes below {src} (missing {missing})")
    if any(s not in d_nodes for s in skins):
        raise RuntimeError("mirror_hand: a skin to mirror is not in the model")
    cx = (dg[src][0, 3] + dg[dst][0, 3]) / 2
    M = np.eye(4)
    M[0, 0], M[0, 3] = -1.0, 2 * cx
    shift = dg[dst][:3, 3] - (M @ dg[src])[:3, 3]
    M[:3, 3] += shift
    flip = np.diag([-1.0, 1.0, 1.0, 1.0])               # the local x axis of a mirrored node
    d_nodes[dst].rest = mirror_mesh_text(d_nodes[src].rest, np.linalg.inv(dg[dst]) @ M @ dg[src])      # the palm: the source's, mirrored, in the target's own frame
    new_glob, new_name = {src: dg[dst]}, {src: dst}
    order = [n for n in d_order if n in below[1:] or n in skins]
    for s in order:
        node = d_nodes[s]
        g = M @ dg[s] @ flip
        if s in skins:
            parent, parent_g, nn = node.parent, dg[node.parent], skins[s]
        else:
            parent, parent_g, nn = new_name[node.parent], new_glob[node.parent], names[s]
        rel = np.linalg.inv(parent_g) @ g
        copy = Node.__new__(Node)
        copy.kind, copy.name, copy.parent = node.kind, nn, parent
        copy.pos, copy.ori = rel[:3, 3].copy(), axis_angle(rel[:3, :3])
        copy.rest = mirror_mesh_text(node.rest, flip)
        d_nodes[nn] = copy
        d_order.append(nn)
        new_glob[s], new_name[s] = g, nn
    return f"mirrored {src} onto {dst}: plane x={cx:.3f}, wrist moved by {np.round(shift, 4).tolist()}, {len(order)} new nodes"


# ------------------------------------------------------------------------------------------------------------- the rebuild
def assemble(cfg: dict, droid_text: str, donor_text: str, reserved: typing.Iterable[str] = ()) -> typing.Tuple[str, typing.List[str]]:
    """The ascii of the new model from the decompiled droid and donor. reserved: more node names (lower case) the carried droid nodes must not use, besides the donor's
    (the names animated by the supermodel chain). Returns (ascii text, notes). Raises RuntimeError when the CONFIG does not fit the models."""
    new, resource = cfg["new"], cfg["resource"]
    notes: typing.List[str] = []
    _, _, d_geo, _ = split_geometry(droid_text)
    d_geo, repeated = unique_node_names(d_geo)
    if repeated:
        notes.append("repeated node names made unique: " + ", ".join(f"{a}->{b}" for a, b in repeated))
    dn_head, _, dn_geo, dn_tail = split_geometry(donor_text)
    d_nodes, d_order = parse_nodes(d_geo)
    dn_nodes, dn_order = parse_nodes(dn_geo)

    lc = {n.lower(): n for n in dn_nodes}
    d_lc = {n.lower(): n for n in d_nodes}
    missing = [h for h in cfg["map"] if h not in d_nodes] + [d for d in cfg["map"].values() if d.lower() not in lc]
    if missing:
        raise RuntimeError(f"{resource}: the CONFIG names nodes that are not in the models: {missing}")
    if len({d.lower() for d in cfg["map"].values()}) != len(cfg["map"]):
        raise RuntimeError(f"{resource}: two droid nodes map to the same donor bone")
    to_donor = {h: lc[d.lower()] for h, d in cfg["map"].items()}
    hooks = {d_lc[h.lower()]: lc[h.lower()] for h in cfg["shared_hooks"] if h.lower() in d_lc and h.lower() in lc}
    dng = global_mats(dn_nodes)
    donor_root = next(n for n, v in dn_nodes.items() if v.parent == "NULL")

    # the droid is scaled to the donor's root height, so that its feet meet the ground where the human clips put the human's
    root_name = d_lc["rootdummy"]
    d_root_z = global_mats(d_nodes)[root_name][2, 3]
    f = dng["rootdummy"][2, 3] / d_root_z
    notes.append(f"scaled {resource} by {f:.4f} (root {d_root_z:.3f} -> {d_root_z * f:.3f}; donor {dng['rootdummy'][2, 3]:.3f})")
    for n in d_nodes.values():
        n.pos = n.pos * f
        if n.kind in ("trimesh", "skin"):
            n.rest = scale_mesh_text(n.rest, f)
    dg = global_mats(d_nodes)

    if cfg.get("mirror_hand"):           # before the re-pose, so that the new hand turns with its arm
        notes.append(mirror_hand(cfg["mirror_hand"], d_nodes, d_order, dg))
        dg = global_mats(d_nodes)

    for chain in cfg.get("repose", ()):
        start, end = chain["start"], chain["end"]
        donor_vec = dng[lc[chain["donor_end"].lower()]][:3, 3] - dng[lc[chain["donor_start"].lower()]][:3, 3]
        src_vec = dg[end][:3, 3] - dg[start][:3, 3]
        a, b = src_vec / np.linalg.norm(src_vec), donor_vec / np.linalg.norm(donor_vec)
        axis = np.cross(a, b)
        angle = float(np.arccos(np.clip(np.dot(a, b), -1.0, 1.0)))
        R = rot((*(axis / np.linalg.norm(axis)), angle)) if np.linalg.norm(axis) > 1e-9 else np.eye(3)
        pivot = dg[start][:3, 3].copy()
        spin = mat4(pivot, R) @ mat4(-pivot, np.eye(3))
        below, stack = [], [start]
        while stack:
            cur = stack.pop()
            below.append(cur)
            stack += [k for k, v in d_nodes.items() if v.parent == cur]
        for k in below:
            dg[k] = spin @ dg[k]
        for skin, anchored in cfg["skin_anchor"].items():
            if anchored in below:                  # a skin mesh that rides on a bone of the chain turns with it
                dg[skin] = spin @ dg[skin]
        notes.append(f"re-posed {start}..{end}: rotated {np.degrees(angle):.0f} degrees about its shoulder ({len(below)} nodes)")

    # donor meshes out: the skins and everything with a texture (the eyes)
    drop = [n for n in dn_order if dn_nodes[n].kind == "skin" or re.search(r"(?m)^\s*bitmap\s+(?!NULL)\S+", dn_nodes[n].rest)]
    keep = [n for n in dn_order if n not in drop]
    for n in drop:
        if [c for c in dn_nodes.values() if c.parent == n and c.name not in drop]:
            raise RuntimeError(f"the donor node {n} has children that would be orphaned")
    kids = children_of({n: dn_nodes[n] for n in keep})
    mapped_donor = {d: h for h, d in to_donor.items()}
    hook_target = {dd: h for h, dd in hooks.items()}

    target_pos: typing.Dict[str, "np.ndarray"] = {}

    def target(name):
        """Where a kept donor bone's joint goes: the matching droid joint; an unmapped bone sits on its first mapped descendant (collars, twist bones) or else on its parent."""
        if name in target_pos:
            return target_pos[name]
        if name in mapped_donor:
            p = dg[mapped_donor[name]][:3, 3]
        elif name in hook_target:
            p = dg[hook_target[name]][:3, 3]
        elif name in ("rootdummy", "cutscenedummy") or dn_nodes[name].parent == "NULL":
            p = dng[name][:3, 3]
        else:
            desc, stack = None, list(kids.get(name, []))
            while stack and desc is None:
                c = stack.pop(0)
                if c in mapped_donor:
                    desc = c
                else:
                    stack = kids.get(c, []) + stack
            p = target(desc) if desc else target(dn_nodes[name].parent)
        target_pos[name] = p
        return p

    for name in keep:
        target(name)
    for name in keep:
        n = dn_nodes[name]
        if n.parent == "NULL" or n.parent not in dn_nodes or n.parent in drop or name in ("cutscenedummy", "rootdummy") or n.parent == "cutscenedummy":
            continue
        if n.parent == donor_root and n.kind == "dummy" and name not in hook_target:
            continue          # the donor's own free hooks (LightsaberHook, DeflectHook ...) keep their place
        n.pos = dng[n.parent][:3, :3].T @ (target_pos[name] - target_pos[n.parent])
    dn_after = global_mats({n: dn_nodes[n] for n in keep})

    hand_centre = {}
    for hook, pieces in cfg.get("hook_hand_nodes", {}).items():
        dd = dn_nodes[lc[hook.lower()]]
        pts = np.vstack([mesh_points(d_nodes[p], dg[p]) for p in pieces])
        centre = (pts.min(axis=0) + pts.max(axis=0)) / 2
        centre[2] -= cfg.get("hook_drop", 0.0)
        hand_centre[hook] = centre
        parent_g = dn_after[dd.parent]
        dd.pos = parent_g[:3, :3].T @ (centre - parent_g[:3, 3])
        dn_after = global_mats({n: dn_nodes[n] for n in keep})
        notes.append(f"weapon hook {hook} placed at the centre of {'+'.join(pieces)}: {np.round(centre, 3).tolist()}")

    for node, hook in cfg.get("hook_follow", {}).items():       # a droid dummy that rides with a hand hook's place (it keeps its own orientation)
        dg[node] = mat4(hand_centre[hook], dg[node][:3, :3])

    def anchor(name):
        cur = name
        while cur and cur in d_nodes:
            if cur in to_donor:
                return cur
            cur = d_nodes[cur].parent
        return None

    # nodes left out, plus everything below them (a child of a dropped node would point at a parent that no longer exists)
    dropped = set(cfg.get("drop_nodes", ())) | {k for k, v in d_nodes.items() if v.kind in cfg["drop_kinds"]}
    grew = True
    while grew:
        grew = False
        for k, v in d_nodes.items():
            if v.parent in dropped and k not in dropped:
                dropped.add(k)
                grew = True
    notes.append("left out: " + (", ".join(sorted(dropped)) or "nothing"))

    added = []
    on_donor = set()          # carried nodes whose parent is a donor bone (their parent name is never renamed)
    for name in d_order:
        n = d_nodes[name]
        if name in cfg["skip"] or name in dropped:
            continue
        if name in hooks and hooks[name] not in drop:
            dd = dn_nodes[hooks[name]]
            a = anchor(name)
            parent_d = to_donor[a] if a else dd.parent
            rel = np.linalg.inv(dn_after[parent_d]) @ dg[name]
            dd.parent, dd.pos, dd.ori = parent_d, rel[:3, 3].copy(), axis_angle(rel[:3, :3])
            continue
        if n.kind == "dummy" and name not in to_donor and anchor(name) is None:
            continue
        if n.kind == "skin":
            if name not in cfg["skin_anchor"]:
                raise RuntimeError(f"{resource}: skin mesh {name} has no skin_anchor")
            bone = to_donor[cfg["skin_anchor"][name]]
            rel = np.linalg.inv(dn_after[bone]) @ dg[name]
            n.kind, n.parent, n.pos, n.ori = "trimesh", bone, rel[:3, 3].copy(), axis_angle(rel[:3, :3])
            n.rest = strip_weights(n.rest)
            added.append(name)
            on_donor.add(name)
            continue
        a = anchor(name)
        if name in to_donor or n.parent in cfg["skip"] or n.parent not in d_nodes:
            donor_parent = to_donor[a] if a else "rootdummy"
            rel = np.linalg.inv(dn_after[donor_parent]) @ dg[name]
            n.parent, n.pos, n.ori = donor_parent, rel[:3, 3].copy(), axis_angle(rel[:3, :3])
            on_donor.add(name)
        added.append(name)
    notes.append(f"{resource} nodes carried over: {len(added)} of {len(d_order)}")

    # one node of each name: a droid node named like a donor bone (or like a node the human clips animate) is renamed, and the droid's own children follow it
    taken = {n.lower() for n in keep} | {r.lower() for r in reserved}
    rename = {}
    for name in added:
        if name.lower() in taken:
            candidate = name + SUFFIX
            while candidate.lower() in taken or candidate in d_nodes:
                candidate += SUFFIX
            rename[name] = candidate
            taken.add(candidate.lower())
        else:
            taken.add(name.lower())
    for name in added:
        n = d_nodes[name]
        n.name = rename.get(name, name)
        if name not in on_donor:
            n.parent = rename.get(n.parent, n.parent)
    if rename:
        notes.append("renamed: " + ", ".join(f"{a}->{b}" for a, b in rename.items()))

    geo_new = "".join(fmt_node(dn_nodes[n]) for n in keep) + "".join(fmt_node(d_nodes[n]) for n in added)
    head = dn_head
    head = re.sub(r"(?m)^# model .*", f"# model {new}", head)
    head = re.sub(r"(?m)^newmodel \S+", f"newmodel {new}", head)
    head = re.sub(r"(?m)^setsupermodel \S+ (\S+)", rf"setsupermodel {new} \1", head)
    head = re.sub(r"(?im)^filedependancy \S+ NULL\.mlk", f"filedependancy {new} NULL.mlk", head)
    text = head + f" {new}\n" + dn_geo.split("node ", 1)[0] + geo_new + dn_tail
    text = re.sub(r"(?i)\bN_DarkJediM\b", new, text)       # the donor's root node and the tail; a texture name such as N_DarkJediM01 is not touched
    return text, notes


def check_ascii(text: str, new: str) -> typing.List[str]:
    """Problems in an assembled ascii model: a duplicate node name, a missing parent, a node listed before its parent, a vertex value that is not finite."""
    problems = []
    _, _, geo, _ = split_geometry(text)
    nodes, order = parse_nodes(geo)
    seen = set()
    for n in order:
        low = n.lower()
        if low in seen:
            problems.append(f"{new}: node name {n} appears twice")
        seen.add(low)
        par = nodes[n].parent
        if par != "NULL" and par not in nodes:
            problems.append(f"{new}: node {n} has the missing parent {par}")
        elif par != "NULL" and order.index(par) >= order.index(n):
            problems.append(f"{new}: node {n} is listed before its parent {par}")
    for m in re.finditer(r"(?im)\b(nan|[-+]?inf(?:inity)?)\b", geo):
        problems.append(f"{new}: a non-finite value ({m.group(1)}) in the geometry")
        break
    return problems


# ----------------------------------------------------------------------------------------------------------------- MDLOps
def mdlops_exe() -> typing.Optional[str]:
    path = os.path.join(os.environ.get("K2_MDLOPS_DIR") or DEFAULT_MDLOPS_DIR, "mdlops.exe")
    return path if os.path.isfile(path) else None


def _resource(inst, name: str, restype, where=None):
    """The game's own bytes of a resource: chitin first (the unmodified model the CONFIG is written for), then Override."""
    from pykotor.extract.installation import SearchLocation
    for loc in where or (SearchLocation.CHITIN, SearchLocation.OVERRIDE):
        res = inst.resource(name, restype, [loc])
        if res is not None:
            return res.data
    return None


def _write_model(inst, resource: str, as_name: str, folder: str):
    from pykotor.resource.type import ResourceType
    for ext, rt in (("mdl", ResourceType.MDL), ("mdx", ResourceType.MDX)):
        data = _resource(inst, resource, rt)
        if data is None:
            raise RuntimeError(f"{resource}.{ext} was not found in the game files")
        with open(os.path.join(folder, f"{as_name}.{ext}"), "wb") as fh:
            fh.write(data)


def _run_mdlops(exe: str, path: str, folder: str):
    return subprocess.run([exe, "-k2", path], cwd=folder, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=MDLOPS_TIMEOUT)


def decompile(inst, exe: str, resource: str, folder: str) -> str:
    os.makedirs(folder, exist_ok=True)
    _write_model(inst, resource, resource, folder)
    _run_mdlops(exe, os.path.join(folder, resource + ".mdl"), folder)
    path = os.path.join(folder, resource + "-ascii.mdl")
    if not os.path.isfile(path):
        raise RuntimeError(f"MDLOps could not decompile {resource}")
    with open(path, "r", encoding="latin-1") as fh:
        return fh.read()


def compile_model(inst, exe: str, text: str, cfg: dict, folder: str) -> typing.Tuple[bytes, bytes]:
    """MDLOps' compile of a model with a supermodel needs the donor's original binary beside the ascii under the NEW name, and the supermodel chain's binaries too."""
    new = cfg["new"]
    os.makedirs(folder, exist_ok=True)
    ascii_path = os.path.join(folder, new + "-ascii.mdl")
    with open(ascii_path, "w", encoding="latin-1") as fh:
        fh.write(text)
    _write_model(inst, DONOR, new, folder)
    for chain in SUPERMODEL_CHAIN:
        _write_model(inst, chain, chain, folder)
    res = _run_mdlops(exe, ascii_path, folder)
    bins = glob.glob(os.path.join(folder, f"{new}-ascii-*bin.mdl"))
    if not bins:
        raise RuntimeError("MDLOps did not produce a compiled model: " + (res.stdout + res.stderr).strip()[-300:])
    with open(bins[0], "rb") as fh:
        mdl = fh.read()
    with open(bins[0][:-4] + ".mdx", "rb") as fh:
        mdx = fh.read()
    return mdl, mdx


def _animated_names(inst) -> typing.Set[str]:
    """Every node name the supermodel chain's animations key (lower case)."""
    from pykotor.resource.formats.mdl import read_mdl
    from pykotor.resource.type import ResourceType
    names: typing.Set[str] = set()

    def walk(node):
        names.add(node.name.lower())
        for c in node.children:
            walk(c)
    for chain in SUPERMODEL_CHAIN:
        mdl_bytes, mdx_bytes = _resource(inst, chain, ResourceType.MDL), _resource(inst, chain, ResourceType.MDX)
        if mdl_bytes is None or mdx_bytes is None:
            raise RuntimeError(f"{chain} was not found in the game files")
        for anim in read_mdl(mdl_bytes, source_ext=mdx_bytes).anims:
            walk(anim.root)
    return names


def read_compiled(mdl: bytes, mdx: bytes):
    """pykotor's read_mdl of a compiled model. Its first pass over the node tree (_get_node_order, whose result nothing uses) adds the 12-byte file header to the offsets twice
    and so reads past the end of a file whose child arrays lie late in it, as MDLOps' output does; the pass is switched off for this call."""
    from pykotor.resource.formats.mdl import read_mdl
    try:
        from pykotor.resource.formats.mdl import io_mdl
        reader = io_mdl.MDLBinaryReader
        saved = reader._get_node_order
    except (ImportError, AttributeError):
        return read_mdl(mdl, source_ext=mdx)
    reader._get_node_order = lambda self, startnode: None
    try:
        return read_mdl(mdl, source_ext=mdx)
    finally:
        reader._get_node_order = saved


def check_model(mdl: bytes, mdx: bytes, cfg: dict, text: typing.Optional[str] = None) -> typing.List[str]:
    """Problems found by reading a compiled model back: it must parse, name the human supermodel, hold no animations of its own, hold the expected nodes, and have finite
    vertex data."""
    new = cfg["new"]
    problems = []
    try:
        model = read_compiled(mdl, mdx)
    except Exception as e:
        return [f"{new}: the compiled model does not read back ({e})"]
    if model.supermodel.lower() != SUPERMODEL_CHAIN[0].lower():
        problems.append(f"{new}: the supermodel is {model.supermodel}, expected {SUPERMODEL_CHAIN[0]}")
    if model.anims:
        problems.append(f"{new}: the model holds {len(model.anims)} animations of its own (they should all come from the supermodel)")
    nodes = model.all_nodes()
    if text is not None:
        _, _, geo, _ = split_geometry(text)
        expected = parse_nodes(geo)[1]
        got = {n.name.lower() for n in nodes}
        absent = [n for n in expected if n.lower() not in got]
        if len(nodes) != len(expected) or absent:
            problems.append(f"{new}: the compiled model has {len(nodes)} nodes, the ascii {len(expected)}; missing: {absent[:6]}")
    bad = 0
    for node in nodes:
        mesh = getattr(node, "mesh", None)
        if mesh is None:
            continue
        for vec in (mesh.vertex_positions or []):
            if not all(math.isfinite(c) for c in (vec.x, vec.y, vec.z)):
                bad += 1
    if bad:
        problems.append(f"{new}: {bad} vertices are not finite numbers")
    return problems


# ----------------------------------------------------------------------------------------------------------------- the entry points
def build(game_dir: str, out_dir: typing.Optional[str], which: str = "all", log: typing.Optional[typing.Callable[[str], None]] = None) -> typing.Tuple[typing.Dict[str, bytes], typing.List[str]]:
    """({file name: bytes}, problems) for one of ORDER ("assassin", "mining", "war", "protocol") or "all". The files are also written to out_dir when it is given (never to the game folder). A failure of one
    model is a problem in the list, not an exception, and does not stop the other. log: called with one line per step of the rebuild (what was scaled, moved, left out)."""
    files: typing.Dict[str, bytes] = {}
    problems: typing.List[str] = []
    keys = ORDER if which == "all" else (which,)
    for key in keys:
        if key not in CONFIGS:
            problems.append(f"unknown model {key!r} (expected {', '.join(ORDER)} or all)")
    keys = [k for k in keys if k in CONFIGS]
    if np is None:
        return files, problems + ["numpy is not installed (needed to build the droid models)"]
    exe = mdlops_exe()
    if exe is None:
        return files, problems + [f"MDLOps was not found: put mdlops.exe in {os.environ.get('K2_MDLOPS_DIR') or DEFAULT_MDLOPS_DIR} or point K2_MDLOPS_DIR at its folder"]
    if not os.path.isfile(os.path.join(game_dir, "swkotor2.exe")):
        return files, problems + [f"the game was not found in {game_dir}"]
    previous = logging.root.manager.disable
    logging.disable(logging.CRITICAL)        # pykotor logs every resource it loads
    try:
        from pykotor.extract.installation import Installation
        inst = Installation(game_dir)
        reserved = _animated_names(inst)
        for key in keys:
            cfg = CONFIGS[key]
            try:
                with tempfile.TemporaryDirectory(prefix="k2droid_") as work:
                    droid_text = decompile(inst, exe, cfg["resource"], os.path.join(work, "droid"))
                    donor_text = decompile(inst, exe, DONOR, os.path.join(work, "donor"))
                    text, notes = assemble(cfg, droid_text, donor_text, reserved)
                    found = check_ascii(text, cfg["new"])
                    if found:
                        problems.extend(found)
                        continue
                    mdl, mdx = compile_model(inst, exe, text, cfg, os.path.join(work, "out"))
                problems.extend(check_model(mdl, mdx, cfg, text))
                files[cfg["new"] + ".mdl"] = mdl
                files[cfg["new"] + ".mdx"] = mdx
                for line in notes:
                    if log:
                        log(f"  [{key}] {line}")
            except Exception as e:
                problems.append(f"{cfg['new']}: {type(e).__name__}: {e}")
    finally:
        logging.disable(previous)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        for name, data in files.items():
            with open(os.path.join(out_dir, name), "wb") as fh:
                fh.write(data)
    return files, problems


def appearance_rows(game_dir: str, base: typing.Optional[bytes] = None) -> typing.Tuple[bytes, typing.Dict[str, dict]]:
    """(appearance.2da bytes, {"assassin": row description, "mining": ..., one per ORDER entry}). Each model is hosted in an appearance row nothing in the game uses: the row takes every
    setting of the droid's own row (source_row), then its label, its model (the race column) and the model type F (a full-body model, which is what plays the human
    clips). base: the bytes to start from instead of the game's own appearance.2da (when something else has already changed it). The row's old cells are in the
    description ("previous") so a caller can put them back."""
    from pykotor.extract.installation import Installation, SearchLocation
    from pykotor.resource.formats.twoda import bytes_2da, read_2da
    from pykotor.resource.type import ResourceType
    if base is None:
        previous = logging.root.manager.disable
        logging.disable(logging.CRITICAL)
        try:
            base = _resource(Installation(game_dir), "appearance", ResourceType.TwoDA, (SearchLocation.OVERRIDE, SearchLocation.CHITIN))
        finally:
            logging.disable(previous)
    if base is None:
        raise RuntimeError("appearance.2da was not found in the game files")
    table = read_2da(base)
    headers = table.get_headers()
    described: typing.Dict[str, dict] = {}
    for key in ORDER:
        cfg = CONFIGS[key]
        row, source = cfg["host_row"], cfg["source_row"]
        target, origin = table.get_row(row), table.get_row(source)
        old = {h: target.get_string(h) for h in headers}
        for h in headers:
            table.set_cell(row, h, origin.get_string(h))
        table.set_cell(row, "label", cfg["label"])
        table.set_cell(row, "race", cfg["new"])
        table.set_cell(row, "modeltype", "F")
        for h, value in cfg.get("row_cells", {}).items():
            table.set_cell(row, h, value)
        described[key] = {"row": row, "model": cfg["new"], "source_row": source, "label": cfg["label"], "modeltype": "F", "previous": old}
    return bytes_2da(table), described


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Builds the assassin, Mining Droid Mk II, war and protocol droid models that play human animations.")
    ap.add_argument("which", nargs="?", default="all", choices=ORDER + ("all",))
    ap.add_argument("--game-dir", default=DEFAULT_GAME_DIR)
    ap.add_argument("--out", default=DEFAULT_OUT_DIR)
    args = ap.parse_args(argv)
    files, problems = build(args.game_dir, args.out, args.which, log=print)
    for name, data in sorted(files.items()):
        print(f"wrote {os.path.join(args.out, name)} ({len(data)} bytes)")
    for p in problems:
        print("PROBLEM:", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
