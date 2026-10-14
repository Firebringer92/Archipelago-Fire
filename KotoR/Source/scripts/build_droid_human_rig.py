"""
Re-skins a humanoid droid onto the human Dark Jedi skeleton (N_DarkJediM) so every human animation plays natively.
Same technique as build_hk47_human_rig.py (read its docstring for the pipeline and the gotchas), driven by a per-droid CONFIG
so war / assassin / protocol droids share one implementation. HK-47's own script is left untouched.

Usage:
  python build_droid_human_rig.py war                 -- build extender/raw_override_files/ap_drdwar.mdl/.mdx
  python build_droid_human_rig.py war --deploy        -- also copy them to <game>/Override and point appearance row <row> at them
  python build_droid_human_rig.py war --restore       -- remove them and put the appearance row back
  options: --game-dir=PATH   --row=N (appearance.2da row that hosts the model; default per droid)
Run the game CLOSED for --deploy / --restore.
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys

import numpy as np

import build_hk47_human_rig as rig   # math, parsing and text helpers

REPO_ROOT = rig.REPO_ROOT
DEFAULT_GAME_DIR = rig.DEFAULT_GAME_DIR
RAW_OVERRIDE_DIR = rig.RAW_OVERRIDE_DIR
MDLOPS_EXE = rig.MDLOPS_EXE
WORK_ROOT = rig.WORK_ROOT
DONOR = "n_darkjedim"

CONFIGS = {
    "war": dict(
        resource="c_drdwar", new="ap_drdwar", source_row=66, default_row=58,
        # droid node -> donor bone
        map={"Groin": "pelvis_g", "Belly": "torso_g", "Chest": "torsoUpr_g", "Neck": "neck_g", "Head": "head_g",
             "L_UpperArm": "lbicep_g", "L_LowerArm": "lforearm_g", "R_UpperArm": "rbicep_g", "R_LowerArm": "rforearm_g",
             "R_Thigh": "rthigh_g", "R_Shin": "rshin_g", "R_Foot": "rfoot_g",
             "L_Thigh": "lthigh_g", "L_Shin": "lshin_g", "L_Foot": "lfoot_g",
             "RHandDrd": "rhand_g", "LHandDrd": "lhand_g"},
        skip={"C_DrdWar", "cutscenedummy", "rootdummy", "upperdummy"},       # root helpers, not carried over
        shared_hooks=("Impact", "camerahook", "headconjure"),                 # donor has these too: moved onto the droid's
        drop_kinds=("emitter", "light"),                                      # spark emitter + light are left out for now
        # real hands exist (RHandDrd/LHandDrd + finger pieces, children of the lower arms); the repeating blaster is a separate piece
        # (RptBlstr, texture w_RptnBlstr_001), left out so the open hand can hold whatever is equipped
        hands_from_forearm={},
        drop_nodes=("RptBlstr",),
        skin_anchor={},
    ),
    "assassin": dict(
        resource="c_drdassassin", new="ap_drdassn", source_row=56, default_row=82,
        map={"pelvis": "pelvis_g", "Box01": "torso_g", "torso": "torsoUpr_g", "head": "head_g",
             "r_shlder": "rcollar_g", "r_delt": "rbicep_g", "r_frarm": "rforearm_g", "r_hand": "rhand_g",
             "r_shlder01": "lcollar_g", "r_delt01": "lbicep_g", "r_frarm01": "lforearm_g", "r_hand01": "lhand_g",
             "r_thigh": "rthigh_g", "r_calf": "rshin_g", "r_foot": "rfoot_g", "r_toe": "rfootT_g",
             "l_thigh": "lthigh_g", "l_calf": "lshin_g", "l_foot": "lfoot_g", "l_toe": "lfootT_g"},
        skip={"C_DrdAssassin", "cutscenedummy", "rootdummy"},
        shared_hooks=("Impact", "camerahook", "headconjure"),
        drop_kinds=("emitter", "light"),
        hands_from_forearm={},
        # the held repeating blaster and its helpers are left out (they also take the rhdold helper under them)
        drop_nodes=("RptBlstr", "rhdold"),
        skin_anchor={},
        # the weapon hooks sit at the centre of each hand piece (the donor's own offset put the grip above this droid's hands),
        # then drop by hook_drop metres
        hook_hand_nodes={"rhand": "r_hand", "lhand": "r_hand01"},
        hook_drop=0.03,
        # both arms rest straight out sideways (a T-pose); the human animations assume arms hanging down, so each arm chain is
        # rotated about its shoulder joint to hang along the donor's arm direction before anything is attached
        repose=[dict(start="r_delt", end="r_hand", donor_start="rbicep_g", donor_end="rhand_g"),
                dict(start="r_delt01", end="r_hand01", donor_start="lbicep_g", donor_end="lhand_g")],
    ),
}


def _arg(flag, default=None):
    for a in sys.argv[1:]:
        if a.startswith(flag + "="):
            return a.split("=", 1)[1]
    return default


def stage(game_dir, out_dir, new):
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
    put(DONOR, new)
    for chain in ("S_Female02", "S_Female01", "S_Male02", "S_Male01"):
        put(chain, chain)


def mesh_points(node, g):
    m = re.search(r"(?m)^[ \t]*verts[ \t]+(\d+)\s*\n((?:[ \t]+\S+[ \t]+\S+[ \t]+\S+[ \t]*\n)+)", node.rest)
    if not m:
        return np.zeros((0, 3))
    v = np.array([[float(x) for x in ln.split()[:3]] for ln in m.group(2).strip().splitlines()[: int(m.group(1))]])
    return (g[:3, :3] @ v.T).T + g[:3, 3]


def build(key, game_dir):
    cfg = CONFIGS[key]
    new, resource = cfg["new"], cfg["resource"]
    d_text = rig.decompile(game_dir, resource, os.path.join(WORK_ROOT, f"work_{new}_src"))
    dn_text = rig.decompile(game_dir, DONOR, os.path.join(WORK_ROOT, f"work_{new}_donor"))
    d_head, _, d_geo, _ = rig.split_geometry(d_text)
    dn_head, _, dn_geo, dn_tail = rig.split_geometry(dn_text)
    d_nodes, d_order = rig.parse_nodes(d_geo)
    dn_nodes, dn_order = rig.parse_nodes(dn_geo)

    lc = {n.lower(): n for n in dn_nodes}
    to_donor = {h: lc[d.lower()] for h, d in cfg["map"].items()}
    hand_donor = {h: lc[d.lower()] for h, d in cfg["hands_from_forearm"].items()}
    hooks = {h: lc[h.lower()] for h in cfg["shared_hooks"] if h.lower() in lc and h in d_nodes}
    dng = rig.global_mats(dn_nodes)

    # scale the droid to the donor's proportions
    root_name = next(n for n in d_nodes if n.lower() == "rootdummy")
    d_root_z = rig.global_mats(d_nodes)[root_name][2, 3]
    f = dng["rootdummy"][2, 3] / d_root_z
    print(f"  scaling {resource} by {f:.4f} (root {d_root_z:.3f} -> {d_root_z * f:.3f}; donor {dng['rootdummy'][2, 3]:.3f})")
    for n in d_nodes.values():
        n.pos = n.pos * f
        if n.kind in ("trimesh", "skin"):
            n.rest = rig.scale_mesh_text(n.rest, f)
    dg = rig.global_mats(d_nodes)

    for chain in cfg.get("repose", ()):
        start, end = chain["start"], chain["end"]
        donor_vec = dng[lc[chain["donor_end"].lower()]][:3, 3] - dng[lc[chain["donor_start"].lower()]][:3, 3]
        src_vec = dg[end][:3, 3] - dg[start][:3, 3]
        a, b = src_vec / np.linalg.norm(src_vec), donor_vec / np.linalg.norm(donor_vec)
        axis = np.cross(a, b)
        angle = float(np.arccos(np.clip(np.dot(a, b), -1.0, 1.0)))
        R = rig.rot((*(axis / np.linalg.norm(axis)), angle)) if np.linalg.norm(axis) > 1e-9 else np.eye(3)
        pivot = dg[start][:3, 3].copy()
        spin = rig.mat4(pivot, R) @ rig.mat4(-pivot, np.eye(3))
        below, stack = [], [start]
        while stack:
            cur = stack.pop()
            below.append(cur)
            stack += [k for k, v in d_nodes.items() if v.parent == cur]
        for k in below:
            dg[k] = spin @ dg[k]
        print(f"  re-posed arm {start}..{end}: rotated {np.degrees(angle):.0f} degrees about its shoulder ({len(below)} nodes)")

    # donor meshes out
    drop = [n for n in dn_order if dn_nodes[n].kind == "skin" or re.search(r"(?m)^\s*bitmap\s+(?!NULL)\S+", dn_nodes[n].rest)]
    keep = [n for n in dn_order if n not in drop]
    kids = rig.children_of({n: dn_nodes[n] for n in keep})
    mapped_donor = {d: h for h, d in to_donor.items()}

    # hand targets: the tip of the forearm piece (mean of its farthest 3% of points from the elbow, scaled space)
    hand_target = {}
    for fore, hand in hand_donor.items():
        pts = mesh_points(d_nodes[fore], dg[fore])
        elbow = dg[fore][:3, 3]
        dist = np.linalg.norm(pts - elbow, axis=1)
        far = pts[dist >= np.percentile(dist, 97)]
        hand_target[hand] = far.mean(axis=0)
        print(f"  {hand}: forearm tip at {np.round(hand_target[hand], 3)} (elbow {np.round(elbow, 3)})")

    target_pos = {}

    def target(name):
        if name in target_pos:
            return target_pos[name]
        if name in mapped_donor:
            p = dg[mapped_donor[name]][:3, 3]
        elif name in hand_target:
            p = hand_target[name]
        elif name in hooks.values():
            p = dg[[h for h, dd in hooks.items() if dd == name][0]][:3, 3]
        elif name in ("rootdummy", "cutscenedummy") or dn_nodes[name].parent == "NULL":
            p = dng[name][:3, 3]
        else:
            desc, stack = None, list(kids.get(name, []))
            while stack and desc is None:
                c = stack.pop(0)
                if c in mapped_donor or c in hand_target:
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
        if n.parent == "NULL" or n.parent not in dn_nodes or n.parent in drop or name in ("cutscenedummy", "rootdummy"):
            continue
        if n.parent == "cutscenedummy":
            continue
        n.pos = dng[n.parent][:3, :3].T @ (target_pos[name] - target_pos[n.parent])
    dn_after = rig.global_mats({n: dn_nodes[n] for n in keep})

    for hook, hand_piece in cfg.get("hook_hand_nodes", {}).items():
        dd = dn_nodes[lc[hook.lower()]]
        pts = mesh_points(d_nodes[hand_piece], dg[hand_piece])
        centre = (pts.min(axis=0) + pts.max(axis=0)) / 2
        centre[2] -= cfg.get("hook_drop", 0.0)
        parent_g = dn_after[dd.parent]
        dd.pos = parent_g[:3, :3].T @ (centre - parent_g[:3, 3])
        dn_after = rig.global_mats({n: dn_nodes[n] for n in keep})
        print(f"  weapon hook {hook} placed at the centre of {hand_piece}: {np.round(centre, 3)}")

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
    print("  left out:", sorted(dropped))

    added = []
    for name in d_order:
        n = d_nodes[name]
        if name in cfg["skip"] or name in dropped:
            continue
        if name in hooks and hooks[name] not in drop:
            dd = dn_nodes[hooks[name]]
            a = anchor(name)
            parent_d = to_donor[a] if a else dd.parent
            rel = np.linalg.inv(dn_after[parent_d]) @ dg[name]
            dd.parent, dd.pos, dd.ori = parent_d, rel[:3, 3].copy(), rig.axis_angle(rel[:3, :3])
            continue
        if n.kind == "dummy" and name not in to_donor and anchor(name) is None:
            continue
        if n.kind == "skin":
            bone = to_donor[cfg["skin_anchor"][name]]
            rel = np.linalg.inv(dn_after[bone]) @ dg[name]
            n.kind, n.parent, n.pos, n.ori = "trimesh", bone, rel[:3, 3].copy(), rig.axis_angle(rel[:3, :3])
            n.rest = rig.strip_weights(n.rest)
            added.append(name)
            continue
        a = anchor(name)
        if name in to_donor or n.parent in cfg["skip"] or n.parent not in d_nodes:
            donor_parent = to_donor[a] if a else "rootdummy"
            rel = np.linalg.inv(dn_after[donor_parent]) @ dg[name]
            n.parent, n.pos, n.ori = donor_parent, rel[:3, 3].copy(), rig.axis_angle(rel[:3, :3])
        added.append(name)
    print(f"  {resource} nodes carried over: {len(added)} (of {len(d_order)})")

    geo_new = "".join(rig.fmt_node(dn_nodes[n]) for n in keep) + "".join(rig.fmt_node(d_nodes[n]) for n in added)
    head = dn_head
    head = re.sub(r"(?m)^# model .*", f"# model {new}", head)
    head = re.sub(r"(?m)^newmodel \S+", f"newmodel {new}", head)
    head = re.sub(r"(?m)^setsupermodel \S+ (\S+)", rf"setsupermodel {new} \1", head)
    head = re.sub(r"(?im)^filedependancy \S+ NULL\.mlk", f"filedependancy {new} NULL.mlk", head)
    text = head + f" {new}\n" + dn_geo.split("node ", 1)[0] + geo_new + dn_tail
    text = re.sub(r"(?i)\bN_DarkJediM\b", new, text)
    text = re.sub(rf"(?i)\b{re.escape(resource)}\b", new, text)

    out_dir = os.path.join(WORK_ROOT, f"work_{new}_out")
    os.makedirs(out_dir, exist_ok=True)
    for fn in os.listdir(out_dir):
        os.remove(os.path.join(out_dir, fn))
    ascii_path = os.path.join(out_dir, new + "-ascii.mdl")
    open(ascii_path, "w", encoding="latin-1").write(text)
    stage(game_dir, out_dir, new)
    res = subprocess.run([MDLOPS_EXE, "-k1", ascii_path], cwd=out_dir, capture_output=True, text=True)
    bins = glob.glob(os.path.join(out_dir, f"{new}-ascii-*bin.mdl"))
    if not bins:
        print(res.stdout[-1500:], res.stderr[-1500:])
        raise RuntimeError("MDLOps did not produce a compiled model")
    os.makedirs(RAW_OVERRIDE_DIR, exist_ok=True)
    for ext, src in (("mdl", bins[0]), ("mdx", bins[0][:-4] + ".mdx")):
        dest = os.path.join(RAW_OVERRIDE_DIR, f"{new}.{ext}")
        shutil.copy2(src, dest)
        print(f"  wrote {dest} ({os.path.getsize(dest)} bytes)")


def backup_path(game_dir, new):
    return os.path.join(game_dir, "Override", f"{new}_appearance_backup.json")


def deploy(key, game_dir, row):
    from pykotor.resource.formats.twoda import read_2da, write_2da
    from pykotor.resource.type import ResourceType
    cfg = CONFIGS[key]
    new = cfg["new"]
    override = os.path.join(game_dir, "Override")
    for ext in ("mdl", "mdx"):
        shutil.copy2(os.path.join(RAW_OVERRIDE_DIR, f"{new}.{ext}"), os.path.join(override, f"{new}.{ext}"))
    path = os.path.join(override, "appearance.2da")
    table = read_2da(path)
    bp = backup_path(game_dir, new)
    if os.path.exists(bp):
        print("  appearance row already patched; refreshed the model files only")
        return
    headers = table.get_headers()
    target, source = table.get_row(row), table.get_row(cfg["source_row"])
    json.dump({"row": row, "cells": {h: target.get_string(h) for h in headers}}, open(bp, "w"), indent=1)
    for h in headers:
        table.set_cell(row, h, source.get_string(h))
    table.set_cell(row, "label", f"AP_{new}")
    table.set_cell(row, "race", new)
    table.set_cell(row, "modeltype", "F")
    write_2da(table, path, ResourceType.TwoDA)
    print(f"  deployed {new} and pointed appearance row {row} at it")


def restore(key, game_dir):
    from pykotor.resource.formats.twoda import read_2da, write_2da
    from pykotor.resource.type import ResourceType
    new = CONFIGS[key]["new"]
    override = os.path.join(game_dir, "Override")
    bp = backup_path(game_dir, new)
    if os.path.exists(bp):
        saved = json.load(open(bp))
        path = os.path.join(override, "appearance.2da")
        table = read_2da(path)
        for h, v in saved["cells"].items():
            table.set_cell(saved["row"], h, v)
        write_2da(table, path, ResourceType.TwoDA)
        os.remove(bp)
        print(f"  appearance row {saved['row']} restored")
    for ext in ("mdl", "mdx"):
        p = os.path.join(override, f"{new}.{ext}")
        if os.path.exists(p):
            os.remove(p)
            print(f"  removed {new}.{ext}")


if __name__ == "__main__":
    key = sys.argv[1]
    game = _arg("--game-dir", DEFAULT_GAME_DIR)
    if "--restore" in sys.argv:
        restore(key, game)
    else:
        build(key, game)
        if "--deploy" in sys.argv:
            deploy(key, game, int(_arg("--row", CONFIGS[key]["default_row"])))
