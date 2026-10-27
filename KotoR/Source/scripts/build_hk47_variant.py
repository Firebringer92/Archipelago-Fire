"""
Builds the HK-47 VARIANT look: a copy of the HK-47 model under a new name (ap_hk47v) with a recolored skin
(ap_hk47v_01, see build_hk47_variant_texture.py) and melee animation groups added, plus the appearance.2da row that
points at it.

Why the animations come from his own clips and not from S_Male02 (the Malak recipe): HK-47's skeleton shares only 10
of S_Male02's 81 nodes and has no rhand_g/lhand_g, so human animation data would not move his body. He does have the
rhand/lhand hooks a blade attaches to. What he lacks are the melee weapon groups (1 stun baton, 2 one-handed blades and
sabers, 3 two-handed), so with a blade the engine finds no stance/attack clip and he glides. This duplicates his own
clips inside the same file under the missing names (same in-file trick as the Mark Two fix):
    g<N>a1, g<N>a2  <- g8a1, g8a2   (his 1.47 s attacks with a Hit event at 0.5 s)
    g<N>r1          <- pause1        (idle)
    g<N>w1          <- g5w1          (weapon draw, carries the draw_weapon event)
    g<N>d1          <- g5d1          (damage reaction)
    g<N>g1          <- g5g1          (guard)
for N in 1, 2, 3. MDLOps compiles it; pykotor's write_mdl is never used (it crashes the game when the animation count
changes).

Appearance row 1 ("Test", an unused duplicate that already pointed at P_HK47) becomes the variant: every cell is copied
from HK-47's own row 3 except `label` and `race`. The original cells are backed up for --restore.

Usage:
  python build_hk47_variant.py                  -- build the model into extender/raw_override_files
  python build_hk47_variant.py --deploy         -- also copy model + texture to <game>/Override and patch appearance row 1
  python build_hk47_variant.py --restore        -- remove the deployed files and put appearance row 1 back
  options: --game-dir=PATH
Run the game CLOSED for --deploy and --restore.
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
RAW_OVERRIDE_DIR = os.environ.get("KOTOR_AP_MODEL_OUT") or os.path.join(REPO_ROOT, "extender", "raw_override_files")
MDLOPS_EXE = os.path.join(REPO_ROOT, "tools", "mdlops", "mdlops.exe")
WORK_DIR = os.path.join(REPO_ROOT, "tools", "mdlops", "work_hk47_variant")

SOURCE = "p_hk47"
SOURCE_TEXTURE = "P_HK47_01"
NEW = "ap_hk47v"
NEW_TEXTURE = "ap_hk47v_01"
VARIANT_ROW = 1
HK47_ROW = 3
# Melee clips the engine can ask for, taken from the human body chain (S_Male02/S_Female02/S_Female01). The game picks a
# style variant (c = critical strike, f = flurry, m = master/power) by the character's feats, so every name has to exist or
# the swing silently plays nothing while the damage still lands. Each name is mapped onto one of HK-47's own clips.
# HK-47 has no sword swing in his file (his only melee clip, g8, is a kick): --swing=kick uses it, --swing=retarget (default)
# replays the human S_Male02 swing on his bones (see hk47_swing_retarget.py and its BONE_MAP knobs).
STANCE_SOURCES = {"r1": "pause1", "w1": "g5w1", "d1": "g5d1", "g1": "g5g1"}   # ready, draw, damage, guard
KICK_SOURCES = ("g8a1", "g8a2")   # his own melee clip (a kick, 1.47 s, Hit event at 0.5 s): the stable fallback
HUMAN_MODEL = "s_male02"
HUMAN_WORK_DIR = os.path.join(REPO_ROOT, "tools", "mdlops", "work_hk47_variant_human")


def alias_plan(swing):
    """[(new clip name, HK-47 clip to duplicate or None when it is retargeted from the human swing)] for melee groups 1-4."""
    names = []
    for g in (1, 2, 3, 4):
        names += [f"g{g}a1", f"g{g}a2"]
        names += [f"g{g}{suffix}" for suffix in STANCE_SOURCES]
        if g >= 2:
            names.append(f"g{g}f1")
            names += [f"c{g}a{i}" for i in range(1, 7)]
            names += [f"f{g}a{i}" for i in range(1, 5)]
            names += [f"m{g}a{i}" for i in (1, 2)]
            names += [f"c{g}n{i}" for i in (1, 2)]
    plan, flip = [], 0
    for name in dict.fromkeys(names):
        suffix = name[2:]
        if suffix in STANCE_SOURCES:
            retarget_stance = swing == "retarget" and suffix in ("r1", "g1")   # ready + guard: blade held in front
            plan.append((name, None if retarget_stance else STANCE_SOURCES[suffix]))
        elif swing == "kick":
            plan.append((name, KICK_SOURCES[flip % 2])); flip += 1
        else:
            plan.append((name, None))
    return plan


def human_source(name):
    """The S_Male02 clip that drives the HK-47 clip `name`.

    Ready/guard stances hold the first swing's pose (see READY_POSE_TIME). EVERY attack variant (basic, critical, flurry, master, the n-variants, any weapon
    group) is a copy of the two tuned basic swings, g2a1 and g2a2 (alternating by number), so one tuning pass in
    hk47_swing_retarget.BONE_MAP fixes them all; the engine only picks among the names by the character's feats."""
    letter, group, kind, idx = name[0], name[1], name[2], int(name[3])
    if kind in ("r", "g") and letter == "g":     # ready / guard stance: the swing frozen at READY_POSE_TIME
        return "g2a1"
    return "g2a1" if idx % 2 else "g2a2"


# Held-weapon movement clips the engine asks for instead of plain walk/run (single saber, double-bladed, staff-type).
# The human body's versions are the same length and footstep timing as its plain walk/run, so his own walk/run stand in.
MOVE_ALIASES = {"walkss": "walk", "runss": "run", "walkds": "walk", "runds": "run", "walkst": "walk", "runst": "run"}
APPEARANCE_BACKUP = "hk47_variant_appearance_backup.json"


def _arg(flag, default=None):
    for a in sys.argv[1:]:
        if a.startswith(flag + "="):
            return a.split("=", 1)[1]
    return default


def _decompile(game_dir, resource=SOURCE, work_dir=WORK_DIR):
    from pykotor.extract.installation import Installation
    from pykotor.resource.type import ResourceType
    inst = Installation(game_dir)
    os.makedirs(work_dir, exist_ok=True)
    for f in os.listdir(work_dir):
        os.remove(os.path.join(work_dir, f))
    mdl = inst.resource(resource, ResourceType.MDL)
    mdx = inst.resource(resource, ResourceType.MDX)
    work_mdl = os.path.join(work_dir, resource + ".mdl")
    open(work_mdl, "wb").write(mdl.data)
    open(os.path.join(work_dir, resource + ".mdx"), "wb").write(mdx.data)
    subprocess.run([MDLOPS_EXE, "-k1", work_mdl], cwd=work_dir, check=True, capture_output=True, text=True)
    path = os.path.join(work_dir, resource + "-ascii.mdl")
    if not os.path.isfile(path):
        raise RuntimeError("MDLOps did not produce the ascii model")
    return path


def build(game_dir):
    ascii_path = _decompile(game_dir)
    text = open(ascii_path, "r", encoding="utf-8", errors="surrogateescape").read()
    model = re.search(r"^newmodel (\S+)", text, re.M).group(1)  # original casing, e.g. P_HK47

    def block(name):
        start = text.index(f"newanim {name} {model}")
        end_marker = f"doneanim {name} {model}"
        return text[start:text.index(end_marker, start) + len(end_marker)]

    swing = _arg("--swing", "retarget")
    if swing not in ("retarget", "kick"):
        raise RuntimeError("--swing must be retarget or kick")
    human_text = human_model = None
    if swing == "retarget":
        import hk47_swing_retarget as rt
        human_ascii = _decompile(game_dir, HUMAN_MODEL, HUMAN_WORK_DIR)
        human_text = open(human_ascii, "r", encoding="utf-8", errors="surrogateescape").read()
        human_model = re.search(r"^newmodel (\S+)", human_text, re.M).group(1)

    new_blocks = []
    for new_name, source in alias_plan(swing):
        if re.search(rf"^newanim {new_name} ", text, re.M):
            raise RuntimeError(f"{new_name} already exists in the source model")
        if source is None:
            stance = new_name[2:] in ("r1", "g1")
            new_blocks.append(rt.retarget_clip(text, human_text, model, human_model, human_source(new_name), new_name,
                                               freeze_at=rt.READY_POSE_TIME if stance else None))
            continue
        b = block(source)
        b = b.replace(f"newanim {source} {model}", f"newanim {new_name} {model}", 1)
        b = b.replace(f"doneanim {source} {model}", f"doneanim {new_name} {model}", 1)
        new_blocks.append(b)
    for new_name, source in MOVE_ALIASES.items():
        if re.search(rf"^newanim {new_name} ", text, re.M):
            raise RuntimeError(f"{new_name} already exists in the source model")
        b = block(source)
        b = b.replace(f"newanim {source} {model}", f"newanim {new_name} {model}", 1)
        b = b.replace(f"doneanim {source} {model}", f"doneanim {new_name} {model}", 1)
        new_blocks.append(b)
    anchor = f"doneanim g8a2 {model}"
    at = text.index(anchor) + len(anchor)
    text = text[:at] + "\n\n" + "\n\n".join(new_blocks) + text[at:]
    print(f"  swing mode: {swing}; added {len(new_blocks)} animation blocks ({len(alias_plan(swing))} melee + {len(MOVE_ALIASES)} movement)")

    # rename: texture first (it contains the model name), then the model name, then the dependency line
    text = re.sub(re.escape(SOURCE_TEXTURE), NEW_TEXTURE, text, flags=re.I)
    text = re.sub(rf"(?<![A-Za-z0-9_]){re.escape(model)}(?![A-Za-z0-9_])", NEW, text)
    text = re.sub(r"(?im)^filedependancy \S+ NULL\.mlk", f"filedependancy {NEW} NULL.mlk", text)
    leftover = re.findall(r"(?i)(?<![a-z])p_hk47", text)  # a leading letter means it is the new ap_hk47v name
    if leftover:
        raise RuntimeError(f"{len(leftover)} references to the old name remain after renaming")

    new_ascii = os.path.join(WORK_DIR, NEW + "-ascii.mdl")
    open(new_ascii, "w", encoding="utf-8", errors="surrogateescape").write(text)
    subprocess.run([MDLOPS_EXE, "-k1", new_ascii], cwd=WORK_DIR, check=True, capture_output=True, text=True)
    bins = glob.glob(os.path.join(WORK_DIR, f"{NEW}-ascii-*bin.mdl"))
    if not bins:
        raise RuntimeError("MDLOps did not produce a recompiled binary model")
    os.makedirs(RAW_OVERRIDE_DIR, exist_ok=True)
    for ext, src in (("mdl", bins[0]), ("mdx", bins[0][:-4] + ".mdx")):
        dest = os.path.join(RAW_OVERRIDE_DIR, f"{NEW}.{ext}")
        shutil.copy2(src, dest)
        print(f"  wrote {dest} ({os.path.getsize(dest)} bytes)")


def _appearance_path(game_dir):
    return os.path.join(game_dir, "Override", "appearance.2da")


def deploy(game_dir):
    from pykotor.resource.formats.twoda import read_2da, write_2da
    from pykotor.resource.type import ResourceType
    texture = os.path.join(RAW_OVERRIDE_DIR, NEW_TEXTURE + ".tga")
    if not os.path.isfile(texture):
        raise RuntimeError("build_hk47_variant_texture.py has not been run (no ap_hk47v_01.tga)")
    override = os.path.join(game_dir, "Override")
    for name in (NEW + ".mdl", NEW + ".mdx", NEW_TEXTURE + ".tga"):
        src = os.path.join(texture if name.endswith(".tga") else os.path.join(RAW_OVERRIDE_DIR, name)) if False else \
            os.path.join(RAW_OVERRIDE_DIR, name)
        shutil.copy2(src, os.path.join(override, name))
    path = _appearance_path(game_dir)
    table = read_2da(path)
    backup_path = os.path.join(override, APPEARANCE_BACKUP)
    if os.path.exists(backup_path):
        print("  appearance row 1 already patched; refreshed the model and texture files only")
        return
    row1, row3 = table.get_row(VARIANT_ROW), table.get_row(HK47_ROW)
    headers = table.get_headers()
    json.dump({h: row1.get_string(h) for h in headers}, open(backup_path, "w"), indent=1)
    for h in headers:
        table.set_cell(VARIANT_ROW, h, row3.get_string(h))
    table.set_cell(VARIANT_ROW, "label", "AP_HK47_Variant")
    table.set_cell(VARIANT_ROW, "race", NEW)
    write_2da(table, path, ResourceType.TwoDA)
    print(f"  deployed model/texture to {override} and patched appearance row {VARIANT_ROW} -> {NEW}")


def restore(game_dir):
    from pykotor.resource.formats.twoda import read_2da, write_2da
    from pykotor.resource.type import ResourceType
    override = os.path.join(game_dir, "Override")
    backup_path = os.path.join(override, APPEARANCE_BACKUP)
    if os.path.exists(backup_path):
        saved = json.load(open(backup_path))
        path = _appearance_path(game_dir)
        table = read_2da(path)
        for h, v in saved.items():
            table.set_cell(VARIANT_ROW, h, v)
        write_2da(table, path, ResourceType.TwoDA)
        os.remove(backup_path)
        print(f"  appearance row {VARIANT_ROW} restored")
    for name in (NEW + ".mdl", NEW + ".mdx", NEW_TEXTURE + ".tga"):
        path = os.path.join(override, name)
        if os.path.exists(path):
            os.remove(path)
            print(f"  removed {name}")


if __name__ == "__main__":
    game = _arg("--game-dir", DEFAULT_GAME_DIR)
    if "--restore" in sys.argv:
        restore(game)
    else:
        build(game)
        if "--deploy" in sys.argv:
            deploy(game)
