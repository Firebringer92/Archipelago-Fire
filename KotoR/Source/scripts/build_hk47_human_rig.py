"""
Re-skins HK-47 onto a HUMAN skeleton so every human animation (all melee groups, two-handed, dual-wield, steps, ranged
stances, walk/run) plays natively, the way the community HK-47 melee mod was built (donor skeleton + target mesh), but done
by script because HK-47's body is rigid pieces, not a weighted skin.

Donor: N_DarkJediM, a full (type F) human model whose animations come from the standard human supermodel chain
(S_Female02 -> S_Female01 -> S_Male02 -> S_Male01). Steps:
  1. take the donor's bone nodes, drop its visible meshes (4 skin meshes + eyes);
  2. move each donor bone's JOINT to HK-47's matching joint (donor bone ORIENTATIONS are kept: the animation keys are written
     against them), with a vertical shift so his feet meet the ground at the donor's root height;
  3. attach every HK-47 piece to the matching donor bone, with its transform re-expressed so it sits exactly where it sat on
     HK-47 at rest (vertices untouched); HK-47's three skinned hose meshes get their bone names mapped to donor bones;
  4. align the donor's weapon/effect hooks (rhand, lhand, ...) to HK-47's;
  5. rename (ap_hk47v / ap_hk47v_01) and compile with MDLOps.
The result has NO animations of its own: they all come from the supermodel. appearance.2da row 1 (model ap_hk47v, type F) is
the same row build_hk47_variant.py patches, so use that script's --deploy / --restore for the game files.

Usage: python build_hk47_human_rig.py [--game-dir=PATH]      (builds into extender/raw_override_files, keeps the previous build
as ap_hk47v_retarget.mdl/.mdx)
"""
import glob
import math
import os
import re
import shutil
import subprocess
import sys

import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
RAW_OVERRIDE_DIR = os.environ.get("KOTOR_AP_MODEL_OUT") or os.path.join(REPO_ROOT, "extender", "raw_override_files")
MDLOPS_EXE = os.path.join(REPO_ROOT, "tools", "mdlops", "mdlops.exe")
WORK_ROOT = os.path.join(REPO_ROOT, "tools", "mdlops")

HK = "p_hk47"
DONOR = "n_darkjedim"
NEW = "ap_hk47v"
NEW_TEXTURE = "ap_hk47v_01"
HK_TEXTURE = "P_HK47_01"

# HK-47 node -> donor bone it rides on (HK bone names on the left; note his right hand bone is oddly named L_hand01).
HK_TO_DONOR = {
    "Pelvis": "pelvis_g", "InnerTorso": "torso_g", "Fore_body": "torsoUpr_g", "Neck": "neck_g",
    "head": "head_g",   # (HK-47's Hturn_g helper between them has no donor twin; it is carried over as a plain child)
    "R_upper_arm": "rbicep_g", "R_lower_arm": "rforearm_g", "L_hand01": "rhand_g",
    "L_upper_arm": "lbicep_g", "L_lower_arm": "lforearm_g", "L_hand": "lhand_g",
    "R_thigh": "rthigh_g", "R_calf": "rshin_g", "R_foot": "rfoot_g",
    "L_thigh": "lthigh_g", "L_calf": "lshin_g", "L_foot": "lfoot_g",
}
# HK-47's three skinned hose meshes become rigid pieces on one bone each (a skinned mesh's bone indices do not survive the skeleton
# swap: the compile bound them to the wrong bones and they stretched down to his feet).
SKIN_ANCHOR = {"L_hose": "Pelvis", "R_hose": "Pelvis", "TorsoHoses": "InnerTorso"}
# Dummies that exist on both: the donor's node is moved onto HK-47's, instead of adding a duplicate.
SHARED_HOOKS = ("rhand", "lhand", "handconjure", "headconjure", "Impact", "talkdummy", "camerahook", "headhook")
# HK-47 root/helper nodes that are not carried over.
SKIP_HK = ("P_HK47", "cutscenedummy", "rootdummy")

# Extra vertical shift (metres) applied after scaling: positive lifts him, negative sinks him.
EXTRA_HEIGHT = 0.0
# HK-47 is scaled uniformly to the donor's proportions (donor root height / HK root height, about 0.91). His legs are longer than
# the human's, so unscaled his feet sink whenever the human clips bend the knees; with the scale they plant like the human's.
# None = automatic; set a number to override (1.0 = his original size).
SCALE_OVERRIDE = None


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
    if a < 1e-9:
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
    nodes = {}
    order = []
    for m in NODE_RE.finditer(geo):
        n = Node(m.group(1), m.group(2), m.group(3))
        nodes[n.name] = n
        order.append(n.name)
    return nodes, order


def local(n):
    return mat4(n.pos, rot(n.ori))


def global_mats(nodes):
    cache = {}

    def g(name):
        if name in cache:
            return cache[name]
        n = nodes[name]
        base = np.eye(4) if n.parent == "NULL" or n.parent not in nodes else g(n.parent)
        cache[name] = base @ local(n)
        return cache[name]
    for name in nodes:
        g(name)
    return cache


def children_of(nodes):
    out = {}
    for n in nodes.values():
        out.setdefault(n.parent, []).append(n.name)
    return out


# ----------------------------------------------------------------------------------------------------------------- build
def decompile(game_dir, resource, work_dir):
    from pykotor.extract.installation import Installation, SearchLocation
    from pykotor.resource.type import ResourceType
    inst = Installation(game_dir)
    os.makedirs(work_dir, exist_ok=True)
    for f in os.listdir(work_dir):
        os.remove(os.path.join(work_dir, f))
    where = [SearchLocation.OVERRIDE, SearchLocation.CHITIN, SearchLocation.MODULES]
    mdl = inst.resource(resource, ResourceType.MDL, where)
    mdx = inst.resource(resource, ResourceType.MDX, where)
    p = os.path.join(work_dir, resource + ".mdl")
    open(p, "wb").write(mdl.data)
    open(os.path.join(work_dir, resource + ".mdx"), "wb").write(mdx.data)
    subprocess.run([MDLOPS_EXE, "-k1", p], cwd=work_dir, check=True, capture_output=True, text=True)
    return open(os.path.join(work_dir, resource + "-ascii.mdl"), "r", encoding="latin-1").read()


def fmt_node(n, kind=None):
    lines = [f"node {kind or n.kind} {n.name}", f"  parent {n.parent}",
             f"  position  {n.pos[0]:.7g} {n.pos[1]:.7g} {n.pos[2]:.7g}",
             f"  orientation  {n.ori[0]:.7g} {n.ori[1]:.7g} {n.ori[2]:.7g} {n.ori[3]:.7g}"]
    return "\n".join(lines) + "\n" + n.rest.rstrip("\n") + "\nendnode\n"


def scale_mesh_text(rest, f):
    """Scales the geometry in a node's non-transform text: verts, bmin, bmax, average, radius (UVs and faces untouched)."""
    out, in_verts = [], 0
    for line in rest.split(chr(10)):
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
    return chr(10).join(out)


def build(game_dir):
    hk_text = decompile(game_dir, HK, os.path.join(WORK_ROOT, "work_hk47_rig_hk"))
    dn_text = decompile(game_dir, DONOR, os.path.join(WORK_ROOT, "work_hk47_rig_donor"))
    hk_head, hk_first, hk_geo, hk_tail = split_geometry(hk_text)
    dn_head, dn_first, dn_geo, dn_tail = split_geometry(dn_text)
    hk_nodes, hk_order = parse_nodes(hk_geo)
    dn_nodes, dn_order = parse_nodes(dn_geo)
    # the donor's bone names are mixed case (Rforearm_g, Lhand_g ...): resolve every name against what is really there
    lc = {n.lower(): n for n in dn_nodes}
    global HK_TO_DONOR
    missing = [d for d in HK_TO_DONOR.values() if d.lower() not in lc]
    if missing:
        raise RuntimeError(f"donor has no bone named {missing}")
    HK_TO_DONOR = {h: lc[d.lower()] for h, d in HK_TO_DONOR.items()}
    hook_donor = {h: lc[h.lower()] for h in SHARED_HOOKS if h.lower() in lc and h in hk_nodes}
    dng = global_mats(dn_nodes)
    hk_root_z0 = global_mats(hk_nodes)["rootdummy"][2, 3]
    f = SCALE_OVERRIDE if SCALE_OVERRIDE is not None else dng["rootdummy"][2, 3] / hk_root_z0
    print(f"  scaling HK-47 by {f:.4f} (root {hk_root_z0:.3f} -> {hk_root_z0 * f:.3f}; donor root {dng['rootdummy'][2, 3]:.3f})")
    for n in hk_nodes.values():
        n.pos = n.pos * f
        n.rest = scale_mesh_text(n.rest, f)
    hkg = global_mats(hk_nodes)

    # 1. drop the donor's visible meshes (its 4 skin meshes and the eye/lid meshes that use its own texture)
    drop = [n for n in dn_order if dn_nodes[n].kind == "skin" or re.search(r"(?m)^\s*bitmap\s+(?!NULL)\S+", dn_nodes[n].rest)]
    print("  donor meshes dropped:", drop)
    for n in drop:
        # children of a dropped node (none expected) would be orphaned
        assert not [c for c in dn_nodes.values() if c.parent == n and c.name not in drop], f"dropped node {n} has children"
    keep = [n for n in dn_order if n not in drop]

    # 2. target joint positions: vertical shift so his feet land on the ground when the donor's root sits at its own height
    hk_root_z = hkg["rootdummy"][2, 3]
    dn_root_z = dng["rootdummy"][2, 3]
    shift = np.array([0.0, 0.0, dn_root_z - hk_root_z + EXTRA_HEIGHT])
    print(f"  root height HK {hk_root_z:.3f} vs donor {dn_root_z:.3f} -> vertical shift {shift[2]:+.3f}")
    kids = children_of({n: dn_nodes[n] for n in keep})
    target_pos = {}
    mapped_donor = {d: h for h, d in HK_TO_DONOR.items()}

    def target(name):
        if name in target_pos:
            return target_pos[name]
        if name in mapped_donor:
            p = hkg[mapped_donor[name]][:3, 3] + shift
        elif name in hook_donor.values():
            p = hkg[[h for h, d in hook_donor.items() if d == name][0]][:3, 3] + shift
        elif name in ("rootdummy",) or dn_nodes[name].parent == "NULL" or dn_nodes[name].parent in ("cutscenedummy",):
            p = dng[name][:3, 3]
        else:
            # unmapped bone: sit on the first mapped descendant (collars, twist bones) or else on its parent (fingers, face)
            desc = None
            stack = list(kids.get(name, []))
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

    # donor rest rotations stay as they are; recompute each kept bone's local position from the target joint positions
    for name in keep:
        n = dn_nodes[name]
        if n.parent == "NULL" or n.parent not in dn_nodes or n.parent in drop:
            continue
        if n.parent in ("cutscenedummy",) or name in ("cutscenedummy", "rootdummy"):
            continue
        parent_rot = dng[n.parent][:3, :3]
        n.pos = parent_rot.T @ (target_pos[name] - target_pos[n.parent])

    # donor global frames AFTER repositioning (rotations unchanged)
    dn_after = global_mats({n: dn_nodes[n] for n in keep})

    # 3 + 4. HK-47 nodes ------------------------------------------------------------------------------------------------
    hk_children = children_of(hk_nodes)

    def anchor(name):
        cur = name
        while cur and cur in hk_nodes:
            if cur in HK_TO_DONOR:
                return cur
            cur = hk_nodes[cur].parent
        return None

    shift_m = mat4(shift, np.eye(3))
    added = []
    for name in hk_order:
        n = hk_nodes[name]
        if name in SKIP_HK:
            continue
        if name in hook_donor and hook_donor[name] not in drop:
            d = dn_nodes[hook_donor[name]]
            a = anchor(name)
            parent_d = HK_TO_DONOR[a] if a else d.parent
            rel = np.linalg.inv(dn_after[parent_d]) @ shift_m @ hkg[name]
            d.parent, d.pos, d.ori = parent_d, rel[:3, 3].copy(), axis_angle(rel[:3, :3])
            continue
        if n.kind == "skin":
            bone = HK_TO_DONOR[SKIN_ANCHOR[name]]
            rel = np.linalg.inv(dn_after[bone]) @ shift_m @ hkg[name]
            n.kind, n.parent, n.pos, n.ori = "trimesh", bone, rel[:3, 3].copy(), axis_angle(rel[:3, :3])
            n.rest = strip_weights(n.rest)
            added.append(name)
            continue
        if n.kind == "dummy" and name not in HK_TO_DONOR and anchor(name) is None:
            continue
        a = anchor(name)
        if name in HK_TO_DONOR or (n.parent in SKIP_HK or n.parent not in hk_nodes):
            donor_parent = HK_TO_DONOR[a] if a else "rootdummy"
            new_parent_global = dn_after[donor_parent] if donor_parent in dn_after else dng[donor_parent]
            rel = np.linalg.inv(new_parent_global) @ shift_m @ hkg[name]
            n.parent, n.pos, n.ori = donor_parent, rel[:3, 3].copy(), axis_angle(rel[:3, :3])
        # else: its HK parent is itself carried over, so the local transform stays as it was
        added.append(name)
    print(f"  HK-47 nodes carried over: {len(added)} (of {len(hk_order)})")

    # 5. assemble ---------------------------------------------------------------------------------------------------------
    pieces = [fmt_node(dn_nodes[n]) for n in keep] + [fmt_node(hk_nodes[n]) for n in added]
    geo_new = "".join(pieces)
    head = dn_head
    head = re.sub(r"(?m)^# model .*", f"# model {NEW}", head)
    head = re.sub(r"(?m)^newmodel \S+", f"newmodel {NEW}", head)
    head = re.sub(r"(?m)^setsupermodel \S+ (\S+)", rf"setsupermodel {NEW} \1", head)
    head = re.sub(r"(?im)^filedependancy \S+ NULL\.mlk", f"filedependancy {NEW} NULL.mlk", head)
    # bounding box / radius of the new model: take HK-47's (shifted)
    for key in ("bmin", "bmax", "radius"):
        m = re.search(rf"(?m)^[ \t]*{key}[ \t].*$", hk_geo.split("node ", 1)[0] if False else hk_text.split("beginmodelgeom", 1)[1].split("node ", 1)[0])
        if m:
            head = head  # donor values kept (the engine recomputes culling from the nodes)
    text = head + f" {NEW}\n" + dn_geo.split("node ", 1)[0] + geo_new + dn_tail
    text = re.sub(rf"(?i){re.escape(HK_TEXTURE)}", NEW_TEXTURE, text)
    text = re.sub(r"(?i)\bP_HK47\b", NEW, text)
    text = re.sub(r"(?i)\bN_DarkJediM\b", NEW, text)
    out_dir = os.path.join(WORK_ROOT, "work_hk47_rig_out")
    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(out_dir):
        os.remove(os.path.join(out_dir, f))
    ascii_path = os.path.join(out_dir, NEW + "-ascii.mdl")
    open(ascii_path, "w", encoding="latin-1").write(text)
    stage_binaries(game_dir, out_dir)
    res = subprocess.run([MDLOPS_EXE, "-k1", ascii_path], cwd=out_dir, capture_output=True, text=True)
    bins = glob.glob(os.path.join(out_dir, f"{NEW}-ascii-*bin.mdl"))
    if not bins:
        print(res.stdout[-1500:], res.stderr[-1500:])
        raise RuntimeError("MDLOps did not produce a compiled model")
    os.makedirs(RAW_OVERRIDE_DIR, exist_ok=True)
    for ext in ("mdl", "mdx"):   # keep the previous (retarget) build as a fallback, once
        prev = os.path.join(RAW_OVERRIDE_DIR, f"{NEW}.{ext}")
        keep_copy = os.path.join(RAW_OVERRIDE_DIR, f"{NEW}_retarget.{ext}")
        if os.path.exists(prev) and not os.path.exists(keep_copy):
            shutil.copy2(prev, keep_copy)
    for ext, src in (("mdl", bins[0]), ("mdx", bins[0][:-4] + ".mdx")):
        dest = os.path.join(RAW_OVERRIDE_DIR, f"{NEW}.{ext}")
        shutil.copy2(src, dest)
        print(f"  wrote {dest} ({os.path.getsize(dest)} bytes)")


def stage_binaries(game_dir, out_dir):
    """MDLOps' read-and-write compile of a model that has a supermodel needs (a) the donor's original binary sitting next to
    the ascii under the NEW name and (b) the supermodel chain's binaries in the same folder."""
    from pykotor.extract.installation import Installation, SearchLocation
    from pykotor.resource.type import ResourceType
    inst = Installation(game_dir)
    where = [SearchLocation.OVERRIDE, SearchLocation.CHITIN, SearchLocation.MODULES]

    def put(resource, as_name):
        for ext, rt in (("mdl", ResourceType.MDL), ("mdx", ResourceType.MDX)):
            r = inst.resource(resource, rt, where)
            if r is None:
                raise RuntimeError(f"{resource}.{ext} not found")
            open(os.path.join(out_dir, f"{as_name}.{ext}"), "wb").write(r.data)
    put(DONOR, NEW)
    for chain in ("S_Female02", "S_Female01", "S_Male02", "S_Male01"):
        put(chain, chain)


def strip_weights(rest):
    """Removes a skin mesh's 'weights N' block (the header line and its N per-vertex lines)."""
    out, skip = [], 0
    for line in rest.split(chr(10)):
        t = line.strip()
        if skip:
            skip -= 1
            continue
        if re.match(r"weights\s+\d+$", t):
            skip = int(t.split()[1])
            continue
        out.append(line)
    return chr(10).join(out)


def remap_weights(rest, shift):
    """Skinned hose meshes: bone names -> donor bone names, vertices shifted with the model."""
    def bone(m):
        return HK_TO_DONOR.get(m.group(1), m.group(1))
    out = []
    in_weights = False
    in_verts = 0
    for line in rest.split("\n"):
        s = line.strip()
        if re.match(r"verts \d+", s):
            in_verts = int(s.split()[1]); out.append(line); continue
        if in_verts:
            xyz = [float(v) for v in s.split()[:3]]
            out.append(f"    {xyz[0] + shift[0]:.7g} {xyz[1] + shift[1]:.7g} {xyz[2] + shift[2]:.7g}")
            in_verts -= 1; continue
        if re.match(r"weights \d+", s):
            in_weights = True; out.append(line); continue
        if in_weights and s and re.match(r"^[A-Za-z_]", s):
            toks = s.split()
            toks = [HK_TO_DONOR.get(t, t) if i % 2 == 0 else t for i, t in enumerate(toks)]
            out.append("    " + " ".join(toks)); continue
        if in_weights and s and not re.match(r"^[A-Za-z_]", s):
            in_weights = False
        out.append(line)
    return "\n".join(out)


if __name__ == "__main__":
    game = DEFAULT_GAME_DIR
    for a in sys.argv[1:]:
        if a.startswith("--game-dir="):
            game = a.split("=", 1)[1]
    build(game)
