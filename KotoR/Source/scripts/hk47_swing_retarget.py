"""
Trial-and-error retarget of the human melee swing clips (S_Male02) onto HK-47's skeleton, used by build_hk47_variant.py.

No rotation math: each HK-47 bone that has a human counterpart simply replays the human bone's orientation keys, optionally
adjusted by the four knobs in BONE_MAP (flip the sign of an axis component, or of the angle). Everything not listed (legs,
root, hooks) stays in HK-47's own rest stance, taken from his idle clip. Adjust BONE_MAP by looking at the result in game.

Orientation keys in the ascii format are `time x y z angle` (axis + angle in radians).
"""
import re

# HK-47 bone -> (human bone, sign of axis x, sign of axis y, sign of axis z, sign of angle).
# START: straight copy (all +1). Tune from what the swing looks like: for example, if the right arm swings the wrong way,
# try (-1, -1, -1, ...) or flip just one axis; if an arm twists instead of swinging, flip the angle sign.
BONE_MAP = {
    # Torso: full strength (halving it removed the forward drive of the swing).
    "InnerTorso":  ("torso_g",    1, 1, 1, 1),
    "Fore_body":   ("torsoUpr_g", 1, 1, 1, 1),
    # Right (blade) arm: straight copy.
    "R_upper_arm": ("rbicep_g",   1, 1, 1, 1),
    "R_lower_arm": ("rforearm_g", 1, 1, 1, 1),
    # Left (off) arm: mirrored, its rest tilt is opposite to the human's.
    "L_upper_arm": ("lbicep_g",   1, -1, -1, 1),
    "L_lower_arm": ("lforearm_g", 1, -1, -1, 1),
    # Legs are NOT driven. Tried: flipping the human thigh/calf keys about Y (his legs are built upside down) lifted his whole body
    # into the air, so the leg frames need a different conversion than a simple axis flip.
    # Not driven, so they keep HK-47's own rest pose: Pelvis, Neck, head (they tilted the whole body), the legs and both hands (his right
    # hand bone, L_hand01, has a 180 degree flip in its rest pose that reversed the blade grip when the human keys were replayed).
}

# The human root moves forward (+y) about 0.4 m through the strike. Replayed on HK-47's root as an offset from his own rest
# position, scaled per axis (x sideways, y forward, z up/down). Set to (0, 0, 0) to turn the lunge off.
ROOT_LUNGE_SCALE = (0.5, 1.0, 0.0)

# The shared ready pose: the swing's own pose at this time (seconds into the human clip; the Hit event is at 0.5). The idle
# stances hold it and the swing starts and ends on it. Earlier = blade closer to the wind-up, later = further through the strike.
READY_POSE_CLIP = "g2a1"   # the human clip the shared ready pose is read from
READY_POSE_TIME = 0.9   # the follow-through just after the strike: blade swept out to his left, angled down

NUM = r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?"
ROW = rf"[ \t]+{NUM}(?:[ \t]+{NUM})+"


def _blocks(text, model):
    """{clip name: block text} for every animation in an ascii model."""
    out = {}
    for m in re.finditer(rf"(?m)^newanim (\S+) {re.escape(model)}", text):
        name = m.group(1)
        end_marker = f"doneanim {name} {model}"
        end = text.index(end_marker, m.start()) + len(end_marker)
        out[name] = text[m.start():end]
    return out


def _nodes(block):
    """Splits a block into (header text, [node chunks]); each chunk starts with 'dummy NAME'."""
    parts = re.split(r"(?m)^  node ", block)
    footer_at = parts[-1].rfind("doneanim")
    return parts[0], parts[1:], footer_at


def _keys(chunk, kind):
    m = re.search(rf"(?m)^[ \t]*{kind}\n((?:{ROW}\n)+)[ \t]*endlist", chunk)
    if not m:
        return None
    return [list(map(float, row.split())) for row in m.group(1).strip().splitlines()]


def _fmt(rows):
    return "\n".join("       " + "  ".join(f"{v:g}" if i else f"{v:g}" for i, v in enumerate(r)) for r in rows)


def retarget_clip(hk_text, human_text, hk_model, human_model, human_clip, new_name, template_clip="pause1", freeze_at=None):
    """Returns a block text for `new_name` on the HK-47 model, driven by the human clip.

    freeze_at: hold the pose the human clip has at that time (seconds) for the whole clip, no events, no lunge. Used for the
    ready/guard stances so the blade rests where the swing strikes."""
    human = _blocks(human_text, human_model)[human_clip]
    template = _blocks(hk_text, hk_model)[template_clip]

    length = float(re.search(r"(?m)^\s*length\s+(\S+)", human).group(1))
    events = re.findall(r"(?m)^\s*event\s+(\S+)\s+(\S+)", human)
    h_parts = re.split(r"(?m)^  node ", human)[1:]
    # the ready pose comes from ONE reference clip, so every swing and stance starts/ends on exactly the same pose
    ref_block = _blocks(human_text, human_model)[READY_POSE_CLIP]
    ref_keys = {}
    for chunk in re.split(r"(?m)^  node ", ref_block)[1:]:
        rk = _keys(chunk, "orientationkey")
        if rk:
            ref_keys[chunk.split()[1]] = min(rk, key=lambda r: abs(r[0] - READY_POSE_TIME))
    h_keys, h_root_pos = {}, None
    for chunk in h_parts:
        name = chunk.split()[1]
        h_keys[name] = _keys(chunk, "orientationkey")
        if name == "rootdummy":
            h_root_pos = _keys(chunk, "positionkey")

    head, chunks, _ = _nodes(template)
    out = [f"newanim {new_name} {hk_model}", f"  length {length:g}", "  transtime 0.25", f"  animroot {hk_model}"]
    if freeze_at is None:
        out += [f"  event  {t} {n}" for t, n in events if n.lower() != "snd_footstep"]
    for chunk in chunks:
        lines = chunk.splitlines()
        kind, name = lines[0].split()[:2]
        parent = next((l.split()[1] for l in lines if l.strip().startswith("parent ")), "NULL")
        pos = _keys(chunk, "positionkey")
        ori = _keys(chunk, "orientationkey")
        out.append(f"  node {kind} {name}")
        out.append(f"    parent {parent}")
        if name == "rootdummy" and pos and h_root_pos and any(ROOT_LUNGE_SCALE) and freeze_at is None:
            base = pos[0][1:]
            h0 = h_root_pos[0][1:]
            rows = [[r[0]] + [base[i] + ROOT_LUNGE_SCALE[i] * (r[1 + i] - h0[i]) for i in range(3)] for r in h_root_pos]
            out.append("    positionkey")
            out.append(_fmt(rows))
            out.append("    endlist")
        elif pos:
            first = pos[0][1:]
            out.append("    positionkey")
            out.append(_fmt([[0.0] + first, [length] + first]))
            out.append("    endlist")
        if name in BONE_MAP and h_keys.get(BONE_MAP[name][0]):
            _, sx, sy, sz, sa = BONE_MAP[name]
            rows = [[r[0], r[1] * sx, r[2] * sy, r[3] * sz, r[4] * sa] for r in h_keys[BONE_MAP[name][0]]]
            # One shared ready pose (the swing's own pose at READY_POSE_TIME): the idle stances hold it, and the swing starts and
            # ends on it, so the idle, the wind-up and the recovery all agree. (The human clip starts and ends on its own ready
            # pose, which on this body puts the blade up behind the head.)
            ref = ref_keys[BONE_MAP[name][0]]
            held = [ref[1] * sx, ref[2] * sy, ref[3] * sz, ref[4] * sa]   # same pose for EVERY clip (taken from the reference swing)
            if freeze_at is not None:
                rows = [[0.0] + held, [length] + held]
            else:
                rows[0] = [rows[0][0]] + held
                rows[-1] = [rows[-1][0]] + held
            out.append("    orientationkey")
            out.append(_fmt(rows))
            out.append("    endlist")
        elif ori:
            first = ori[0][1:]
            out.append("    orientationkey")
            out.append(_fmt([[0.0] + first, [length] + first]))
            out.append("    endlist")
        out.append("  endnode")
    out.append(f"doneanim {new_name} {hk_model}")
    return "\n".join(out) + "\n"
