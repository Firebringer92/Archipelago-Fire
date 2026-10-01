"""
Fixes Darth Malak's missing basic-attack animation when played as a
companion (NewCompanion=malak, see k_hmal_spawn01.nss's
EffectDisguise(DISGUISE_TYPE_N_DARTHMALAK)).

Root cause: EffectDisguise renders the player's own vanilla appearance.2da
row 21 model, "N_DarthMalak" (models.bif). That model has supermodel=NULL
(confirmed via direct read) -- zero animation fallback. Its own 66 baked
animations cover walk/run/talk/idle, force-power cast (castout1-3/
castoutlp1-3 -- why power moves already animate correctly, no fallback
needed), his unique boss-AI moves, plus a partial one-handed-melee set
under group 2 (g2r1/g2w1 -- "ready"/"wound" reactions only, no attack
swing) and a nonstandard group-1 set (g1x1/g1y1/g1z1) that turned out to
be the wrong weapon group entirely -- see below.

FOUR earlier attempts, all superseded:
1-3. Cross-model node-tree copy from S_Male02, then two supermodel-field
   edits (S_Male02 direct, then S_Female02 mirroring P_CarthBB's own
   link) -- all via pykotor, all crashed live. Decoded the actual crash
   dumps (%LocalAppData%\\CrashDumps\\swkotor.exe.*.dmp, via the
   `minidump` python package): both supermodel edits crashed at the
   IDENTICAL address inside swkotor.exe regardless of which supermodel
   was chosen (an engine-side issue with a type-F unique appearance
   declaring any supermodel, not a wrong choice of supermodel); the
   node-tree-copy crash and a later plain in-file duplicate (attempt 4,
   also via pykotor) crashed at the identical address one function deep
   in the Intel GPU driver (igxelpicd32.dll) -- strong evidence pykotor's
   write_mdl mis-serializes something whenever this file's animation
   COUNT changes, independent of what data is added.
4. Switched to MDLOps (tools/mdlops/mdlops.exe -- ~20-year-old,
   independently-implemented Perl-based binary MDL compiler/decompiler,
   completely separate codebase from pykotor) to duplicate N_DarthMalak's
   OWN g1x1/g1y1 animations and rename the copies to g1a1/g1a2. This
   finally did NOT crash -- confirms the crashes above really were
   pykotor's writer, not an engine limitation -- but the animation still
   didn't play. Root cause: baseitems.2da's Lightsaber row has
   weaponwield=2, not 1 -- the game was never going to request "g1a1" for
   a lightsaber. Group 1 was simply the wrong style group.

This version targets the CORRECT group. It still uses MDLOps (proven
crash-free above), but now splices g2a1/g2a2 -- real one-handed-melee
swing keyframes, confirmed present in S_Male02 (events: "Swinglong" at
0.37s, "Hit" at 0.5s) -- across from S_Male02 into N_DarthMalak, as plain
ascii text. Each source block contains exactly 5 literal references to
its own model name ("S_Male02": the newanim/doneanim boundary, animroot,
the animation's own top dummy node, and that dummy's one child's parent
link) -- confirmed by direct inspection -- which get remapped to
"N_DarthMalak" so the spliced hierarchy attaches to the right target
model; every deeper node (cutscenedummy, rootdummy, pelvis_g, rhand_g,
etc) is generic shared-skeleton naming already confirmed present on
N_DarthMalak's own geometry, so nothing else needs renaming.

Usage: python fix_malak_basic_attack_animations.py [--game-dir=<path>]
  Writes extender/raw_override_files/N_DarthMalak.mdl/.mdx (checked-in
  source) and deploys them to <game-dir>/Override.
"""
import glob
import os
import shutil
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
RAW_OVERRIDE_DIR = os.path.join(REPO_ROOT, "extender", "raw_override_files")
MDLOPS_DIR = os.path.join(REPO_ROOT, "tools", "mdlops")
MDLOPS_EXE = os.path.join(MDLOPS_DIR, "mdlops.exe")
WORK_DIR = os.path.join(MDLOPS_DIR, "work")
SOURCE_WORK_DIR = os.path.join(MDLOPS_DIR, "work2")

TARGET_MODEL = "N_DarthMalak"
SOURCE_MODEL = "S_Male02"
# (new name, source name in S_Male02 to splice) -- weaponwield=2 for
# Lightsaber (baseitems.2da), confirmed via direct read -- group 2 is the
# correct one-handed-melee style, not group 1.
_ANIMS_TO_SPLICE = (("g2a1", "g2a1"), ("g2a2", "g2a2"))


def _arg_value(flag, default):
    for a in sys.argv[1:]:
        if a.startswith(flag + "="):
            return a.split("=", 1)[1]
    return default


def _clean_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)
    for f in os.listdir(path):
        os.remove(os.path.join(path, f))


def _decompile(work_dir: str, resource_name: str, game_dir: str) -> str:
    from pykotor.extract.installation import Installation
    from pykotor.resource.type import ResourceType
    inst = Installation(game_dir)
    mdl_res = inst.resource(resource_name, ResourceType.MDL)
    mdx_res = inst.resource(resource_name, ResourceType.MDX)
    print(f"  source: {resource_name} <- {mdl_res.filepath}")
    work_mdl = os.path.join(work_dir, f"{resource_name}.mdl")
    with open(work_mdl, "wb") as f:
        f.write(mdl_res.data)
    with open(os.path.join(work_dir, f"{resource_name}.mdx"), "wb") as f:
        f.write(mdx_res.data)

    subprocess.run([MDLOPS_EXE, "-k1", work_mdl], cwd=work_dir, check=True,
                    capture_output=True, text=True)
    ascii_path = os.path.join(work_dir, f"{resource_name}-ascii.mdl")
    if not os.path.isfile(ascii_path):
        raise RuntimeError(f"MDLOps did not produce {ascii_path} -- decompile failed?")
    return ascii_path


def _extract_anim_block(text: str, anim_name: str, model_name: str) -> str:
    start_marker = f"newanim {anim_name} {model_name}"
    end_marker = f"doneanim {anim_name} {model_name}"
    start = text.index(start_marker)
    end = text.index(end_marker, start) + len(end_marker)
    return text[start:end]


def build(game_dir: str) -> None:
    _clean_dir(WORK_DIR)
    _clean_dir(SOURCE_WORK_DIR)

    target_ascii_path = _decompile(WORK_DIR, TARGET_MODEL, game_dir)
    source_ascii_path = _decompile(SOURCE_WORK_DIR, SOURCE_MODEL, game_dir)

    with open(source_ascii_path, "r", encoding="utf-8", errors="surrogateescape") as f:
        source_text = f.read()

    new_blocks = []
    for new_name, source_name in _ANIMS_TO_SPLICE:
        block = _extract_anim_block(source_text, source_name, SOURCE_MODEL)
        occurrences = block.count(SOURCE_MODEL)
        if occurrences != 5:
            raise RuntimeError(f"expected exactly 5 references to '{SOURCE_MODEL}' in its own "
                                f"'{source_name}' block, found {occurrences} -- ascii format changed?")
        remapped = block.replace(SOURCE_MODEL, TARGET_MODEL)
        if new_name != source_name:
            remapped = remapped.replace(f"newanim {source_name} {TARGET_MODEL}",
                                         f"newanim {new_name} {TARGET_MODEL}", 1)
            remapped = remapped.replace(f"doneanim {source_name} {TARGET_MODEL}",
                                         f"doneanim {new_name} {TARGET_MODEL}", 1)
        new_blocks.append(remapped)
        print(f"  spliced {SOURCE_MODEL}:{source_name} -> {TARGET_MODEL}:{new_name} ({len(remapped)} chars)")

    with open(target_ascii_path, "r", encoding="utf-8", errors="surrogateescape") as f:
        text = f.read()
    insertion_point = text.index(f"doneanim g2w1 {TARGET_MODEL}") + len(f"doneanim g2w1 {TARGET_MODEL}")
    text = text[:insertion_point] + "\n\n" + "\n\n".join(new_blocks) + text[insertion_point:]
    with open(target_ascii_path, "w", encoding="utf-8", errors="surrogateescape") as f:
        f.write(text)

    result = subprocess.run([MDLOPS_EXE, "-k1", target_ascii_path], cwd=WORK_DIR, check=True,
                             capture_output=True, text=True)
    print(result.stdout)

    bin_candidates = glob.glob(os.path.join(WORK_DIR, f"{TARGET_MODEL}-ascii-*bin.mdl"))
    if not bin_candidates:
        raise RuntimeError("MDLOps did not produce a recompiled binary model -- compile failed?")
    bin_mdl = bin_candidates[0]
    bin_mdx = bin_mdl[:-4] + ".mdx"

    out_mdl_path = os.path.join(RAW_OVERRIDE_DIR, f"{TARGET_MODEL}.mdl")
    out_mdx_path = os.path.join(RAW_OVERRIDE_DIR, f"{TARGET_MODEL}.mdx")
    shutil.copy2(bin_mdl, out_mdl_path)
    shutil.copy2(bin_mdx, out_mdx_path)
    print(f"  wrote {out_mdl_path} ({os.path.getsize(out_mdl_path)} bytes)")
    print(f"  wrote {out_mdx_path} ({os.path.getsize(out_mdx_path)} bytes)")

    override_dir = os.path.join(game_dir, "Override")
    for ext in ("mdl", "mdx"):
        shutil.copy2(os.path.join(RAW_OVERRIDE_DIR, f"{TARGET_MODEL}.{ext}"),
                     os.path.join(override_dir, f"{TARGET_MODEL}.{ext}"))
    print(f"  deployed -> {override_dir}\\{TARGET_MODEL}.mdl/.mdx")


if __name__ == "__main__":
    build(_arg_value("--game-dir", DEFAULT_GAME_DIR))
