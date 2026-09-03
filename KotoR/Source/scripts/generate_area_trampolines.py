"""
For each area in AREA_LIST: extracts the real OnEnter script, saves its
bytecode under a new short resref (apo_NNNN) in Override so the original
behavior is fully preserved, and writes a tiny trampoline .nss that calls
the renamed original then ap_poll_shared. Trampolines still need
compiling afterward (via nwnnsscomp, done in a separate pass).

Some OnEnter resrefs are shared/generic across multiple different modules
(e.g. k_pkor_areaenter is used by both korr_m34aa and korr_m39aa) -- Override
is a flat namespace, so only ONE trampoline can occupy a given resref. For
those groups, a single trampoline is generated that checks
GetTag(GetArea(OBJECT_SELF)) at runtime to report the correct area index,
covering every module in the group with one shared preserved original.
"""
import json
import os
from collections import defaultdict
from pykotor.resource.formats.rim import read_rim
from pykotor.resource.formats.gff import read_gff
from pykotor.resource.type import ResourceType
from pykotor.extract.installation import Installation

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
OVERRIDE_DIR = GAME_DIR + r"\Override"
TRAMPOLINE_SRC_DIR = os.path.join(REPO_ROOT, "extender", "area_trampolines")

# All 78 real gameplay areas (modules with a populated OnEnter, excluding the
# 18 STUNT_* cutscene-only modules -- verified barren of triggers/stores/
# encounters, purely staged cinematic sets, not areas a player explores --
# and excluding M12ab, a dead duplicate of ebo_m12aa: identical OnEnter
# script AND identical area tag "Area001", non-standard capitalization vs.
# every other module's lowercase naming, same "unused leftover module"
# pattern found earlier with tar_m02af).
# end_m01aa/end_m01ab/tar_m02aa kept first so their indices (0/1/2) stay
# stable from the earlier proof-of-concept phase; the rest follow
# alphabetically.
AREA_LIST = [
    "end_m01aa", "end_m01ab", "tar_m02aa",
    "danm13", "danm14aa", "danm14ab", "danm14ac", "danm14ad",
    "danm15", "ebo_m12aa", "ebo_m41aa", "kas_m22aa", "kas_m23aa",
    "kas_m23ad", "kas_m24aa", "kas_m25aa", "korr_m33aa", "korr_m33ab",
    "korr_m34aa", "korr_m35aa", "korr_m36aa", "korr_m37aa", "korr_m38ab",
    "korr_m39aa", "lev_m40aa", "lev_m40ab", "lev_m40ac", "lev_m40ad",
    "liv_m99aa", "manm26aa", "manm26ab", "manm26ac", "manm26ad",
    "manm26ae", "manm27aa", "manm28aa", "manm28ab", "manm28ac",
    "manm28ad", "sta_m45aa", "sta_m45ac", "sta_m45ad", "tar_m02ab",
    "tar_m02ac", "tar_m02ad", "tar_m02ae", "tar_m02af", "tar_m03aa",
    "tar_m03ab", "tar_m03ad", "tar_m03ae", "tar_m03af", "tar_m04aa",
    "tar_m05aa", "tar_m05ab", "tar_m08aa", "tar_m09ab", "tar_m10aa",
    "tar_m10ab", "tar_m10ac", "tar_m11aa", "tar_m11ab", "tat_m17aa",
    "tat_m17ab", "tat_m17ad", "tat_m17ae", "tat_m18aa", "tat_m18ab",
    "tat_m18ac", "tat_m20aa", "unk_m41aa", "unk_m41ab", "unk_m41ac",
    "unk_m41ad", "unk_m42aa", "unk_m43aa", "unk_m44aa", "unk_m44ac",
]

os.makedirs(TRAMPOLINE_SRC_DIR, exist_ok=True)
installation = Installation(GAME_DIR)


def get_onenter_and_tag(base):
    r = read_rim(rf"{GAME_DIR}\modules\{base}.rim")
    are_data = None
    for res in r:
        if res.restype == ResourceType.ARE:
            are_data = res.data
    assert are_data is not None, f"no ARE for {base}"
    gff = read_gff(are_data)
    onenter = str(gff.root.get_resref("OnEnter"))
    tag = gff.root.get_string("Tag") if gff.root.exists("Tag") else base
    return onenter, tag


def get_orig_ncs(base, onenter):
    orig_ncs = None
    r_s = read_rim(rf"{GAME_DIR}\modules\{base}_s.rim")
    for res in r_s:
        if res.restype == ResourceType.NCS and res.resref.get() == onenter:
            orig_ncs = res.data
            break
    if orig_ncs is None:
        core_res = installation.resource(onenter, ResourceType.NCS)
        if core_res is not None:
            orig_ncs = core_res.data
    assert orig_ncs is not None, f"could not find {onenter}.ncs in {base}_s.rim or core data"
    return orig_ncs


# Assign each area a stable index (by AREA_LIST position), then group by
# OnEnter resref so shared ones can be handled specially.
area_info = {}  # base -> {idx, onenter, tag}
by_onenter = defaultdict(list)  # onenter -> [base, ...]
for idx, base in enumerate(AREA_LIST):
    onenter, tag = get_onenter_and_tag(base)
    assert onenter, f"SKIP {base}: no OnEnter set"
    area_info[base] = {"idx": idx, "onenter": onenter, "tag": tag}
    by_onenter[onenter].append(base)

mapping = {}
trampoline_counter = 0
for onenter, bases in by_onenter.items():
    trampoline_counter += 1
    renamed_resref = f"apo_{trampoline_counter:04d}"
    orig_ncs = get_orig_ncs(bases[0], onenter)
    renamed_path = os.path.join(OVERRIDE_DIR, f"{renamed_resref}.ncs")
    with open(renamed_path, "wb") as f:
        f.write(orig_ncs)

    if len(bases) == 1:
        base = bases[0]
        idx = area_info[base]["idx"]
        report_block = f'        KSE_Diag(20, "AP|CHECK|AREA|{idx}");'
    else:
        # Shared OnEnter across multiple modules -- disambiguate at runtime
        # via the area's own tag, which IS distinct even when the OnEnter
        # resref isn't.
        lines = ['        string sAreaTag = GetTag(GetArea(OBJECT_SELF));']
        for i, base in enumerate(bases):
            idx = area_info[base]["idx"]
            tag = area_info[base]["tag"]
            kw = "if" if i == 0 else "else if"
            lines.append(f'        {kw} (sAreaTag == "{tag}")')
            lines.append('        {')
            lines.append(f'            KSE_Diag(20, "AP|CHECK|AREA|{idx}");')
            lines.append('        }')
        report_block = "\n".join(lines)

    base_list_comment = ", ".join(bases)
    trampoline_src = f"""// AUTO-GENERATED trampoline for OnEnter={onenter}.
// Covers: {base_list_comment}
// Preserves the real game's OnEnter logic via ExecuteScript, then runs the
// shared AP polling brain. See generate_area_trampolines.py.
//
// The area-visited check is done INLINE here, not in ap_poll_shared --
// confirmed by testing that a global set immediately before ExecuteScript
// is NOT visible to the called script in this engine build (true for both
// string and number globals, so it's not a type issue -- a genuine
// ExecuteScript/global-visibility limitation).
//
// NOTE: no seen-flag guard here -- custom (non-globalcat.2da) global
// variable names were confirmed this session to NOT persist in this engine
// build, so we report UNCONDITIONALLY on every real player entry instead.
// Deduplication lives on the extender/AP-client side now, not in-game.
//
// OnEnter fires once per OBJECT crossing into the area -- with a full
// party, that means once for the player AND once for each companion
// following, all in the same instant (confirmed: 15 duplicate fires on one
// real transition). ExecuteScript(renamed original) always runs, for every
// entering object, matching real game behavior. Our OWN AP reporting is
// gated to the player specifically via GetEnteringObject()+GetIsPC(), so
// it only ever runs once per area PER ENTRY regardless of party size (it
// will still fire again on a later, separate entry into the same area).
#include "kse"

void main()
{{
    ExecuteScript("{renamed_resref}", OBJECT_SELF);

    object oEnterer = GetEnteringObject();
    if (GetIsPC(oEnterer))
    {{
{report_block}
        ExecuteScript("ap_poll_shared", OBJECT_SELF);
    }}
}}
"""
    nss_path = os.path.join(TRAMPOLINE_SRC_DIR, f"{onenter}.nss")
    with open(nss_path, "w") as f:
        f.write(trampoline_src)

    for base in bases:
        mapping[base] = {"idx": area_info[base]["idx"], "onenter": onenter, "renamed": renamed_resref}
    tag_note = "" if len(bases) == 1 else f" (shared, {len(bases)} areas via runtime tag check)"
    print(f"{onenter}: covers {base_list_comment} -> preserved as {renamed_resref}, trampoline at {nss_path}{tag_note}")

with open(os.path.join(TRAMPOLINE_SRC_DIR, "_mapping.json"), "w") as f:
    json.dump(mapping, f, indent=2)

idx_to_name = {v["idx"]: k for k, v in mapping.items()}
with open(os.path.join(TRAMPOLINE_SRC_DIR, "_idx_to_name.json"), "w") as f:
    json.dump(idx_to_name, f, indent=2)

print(f"\n{len(mapping)} areas covered by {trampoline_counter} trampolines. Compile them next.")
