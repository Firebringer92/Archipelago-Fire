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

# Permanent-object spawns that must survive every regeneration of an
# area's OnEnter trampoline (this generator AND generate_trampoline_
# batch.py's live pending-arm-batch variant both rebuild these files from
# scratch, so a permanent addition has to live in the generator source,
# never hand-edited into a generated .nss). base -> list of NWScript
# statement strings, no leading indentation (added by the caller).
#
# Deliberately EMPTY here -- this generator runs once at packaging time,
# with no connected seed to read Options.py's GalacticShop from, so it
# can't know whether any given player wants the AP Vendor spawned at all.
# Defaults to matching GalacticShop's own `default = False` (no vendor)
# rather than guessing "always on." generate_trampoline_batch.py's own
# copy of this dict is the real, per-seed-correct source of truth once a
# player actually connects (gated on _connected_archipelago_vendor()) -- this
# packaging-time baseline only matters until the first real regeneration
# for ebo_m12aa happens for that player's own seed.
AREA_PERMANENT_SPAWNS = {}


def permanent_spawn_lines_for(base, indent):
    return [f"{indent}{stmt}" for stmt in AREA_PERMANENT_SPAWNS.get(base, [])]


def area_entry_diag_lines(idx, indent):
    """The area-entry report: the existing AP|CHECK|AREA|<idx> line, now also carrying seen=0/1.
    The mark is a LocalBoolean on the area object, which the game saves with the area's module
    state. A re-entry that reports seen=0 for an area the player has already been in, with no save
    load in between, means the game started the area from scratch instead of restoring its saved
    state -- the symptom behind "scripts refire and the game does not recognise I have been here"
    reports. Folded into the existing line (all readers match only the prefix) rather than a
    separate diagnostic line; nothing reads the mark.

    Also gives the player the plot item `ap_loc_<idx>` ("Location: <area>") if they do not have it. The
    item stays in the save, so the visited set survives a closed client or a missed report; the poll's
    CheckVisitedMarkers() reports it. Written here, in the always-on entry block, so it needs no client
    and no queued arm. Keep in sync with the copy in generate_trampoline_batch.py and with
    generate_location_items.py (the templates)."""
    marker = f"ap_loc_{idx:02d}"
    lines = [
        f"{indent}int nVisitMark = GetLocalBoolean(OBJECT_SELF, 62);",
        f"{indent}SetLocalBoolean(OBJECT_SELF, 62, TRUE);",
        f'{indent}KSE_Diag(20, "AP|CHECK|AREA|{idx}|seen=" + IntToString(nVisitMark));',
        f'{indent}if (!GetIsObjectValid(GetItemPossessedBy(GetFirstPC(), "{marker}")))',
        f"{indent}{{",
        f'{indent}    CreateItemOnObject("{marker}", GetFirstPC(), 1);',
        f"{indent}}}",
    ]
    if idx == 0:
        # The first Endar Spire area (end_m01aa): a brand-new level-1 character gets the Player ID item
        # (patch_player_id.py writes its per-seed template). Level 1 only, so a leveled character that
        # is warped or loaded in here is never stamped with the current seed. Runs after the original
        # OnEnter, so an entry-time inventory strip cannot remove it.
        lines += [
            f'{indent}if (GetHitDice(GetFirstPC()) <= 1 && !GetIsObjectValid(GetItemPossessedBy(GetFirstPC(), "ap_pid")))',
            f"{indent}{{",
            f'{indent}    CreateItemOnObject("ap_pid", GetFirstPC(), 1);',
            f"{indent}}}",
        ]
    return lines


# OnEnter scripts whose vanilla body makes a companion available on every
# real entry (AddAvailableNPCByTemplate behind only an IsAvailableCreature
# check), which hands Carth/Bastila back to a player whose AP item hasn't
# arrived: k_pdan_13_area (danm13, the Jedi Enclave) adds both,
# k_pdan_15_area (danm15) adds Bastila. The trampoline records who was
# available before the original runs and takes away whoever it added. A
# companion the AP grant already made available is left alone. Keep in sync
# with the copy in generate_trampoline_batch.py, which rebuilds these same
# trampolines.
ORIGINAL_ENTER_GUARDS = {
    "k_pdan_13_area": [("NPC_CARTH", "carth"), ("NPC_BASTILA", "bastila")],
    "k_pdan_15_area": [("NPC_BASTILA", "bastila")],
}


def original_enter_guard(onenter):
    """(lines before, lines after) the ExecuteScript of the preserved
    original, as ready-to-embed text. Both empty for an unguarded OnEnter so
    its generated trampoline is unchanged."""
    guards = ORIGINAL_ENTER_GUARDS.get(onenter)
    if not guards:
        return "", ""
    pre = ""
    post = ""
    for npc_const, key in guards:
        pre += f"    int bWas_{key} = IsAvailableCreature({npc_const});\n"
        post += (
            f"    if (!bWas_{key} && IsAvailableCreature({npc_const}))\n"
            "    {\n"
            f"        RemovePartyMember({npc_const});\n"
            f"        RemoveAvailableNPC({npc_const});\n"
            f'        KSE_Diag(28, "AP|SUPPRESSED|companion_{key}|area_enter");\n'
            "    }\n"
        )
    return pre, post


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
    # Areas can share an OnEnter RESREF while each module's copy of that
    # script is a different script (korr_m34aa/korr_m39aa and the three
    # sta_m45* areas do). Preserve one original per distinct script, under
    # apo_NNNN, apo_NNNNb, apo_NNNNc..., keyed by the exact bytes.
    variant_name_for_bytes = {}
    renamed_for_base = {}
    for base in bases:
        data = bytes(get_orig_ncs(base, onenter))
        if data not in variant_name_for_bytes:
            suffix = "" if not variant_name_for_bytes else chr(ord("a") + len(variant_name_for_bytes))
            name = f"{renamed_resref}{suffix}"
            variant_name_for_bytes[data] = name
            with open(os.path.join(OVERRIDE_DIR, f"{name}.ncs"), "wb") as f:
                f.write(data)
        renamed_for_base[base] = variant_name_for_bytes[data]
    if len(variant_name_for_bytes) == 1:
        original_block = f'    ExecuteScript("{renamed_resref}", OBJECT_SELF);\n'
    else:
        original_block = '    string sEnterTag = GetTag(GetArea(OBJECT_SELF));\n'
        for i, base in enumerate(bases):
            kw = "if" if i == 0 else "else if"
            original_block += f'    {kw} (sEnterTag == "{area_info[base]["tag"]}") ExecuteScript("{renamed_for_base[base]}", OBJECT_SELF);\n'
        original_block += f'    else ExecuteScript("{renamed_for_base[bases[0]]}", OBJECT_SELF);\n'

    if len(bases) == 1:
        base = bases[0]
        idx = area_info[base]["idx"]
        lines = list(area_entry_diag_lines(idx, "        "))
        lines.extend(permanent_spawn_lines_for(base, "        "))
        report_block = "\n".join(lines)
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
            lines.extend(area_entry_diag_lines(idx, "            "))
            lines.extend(permanent_spawn_lines_for(base, "            "))
            lines.append('        }')
        report_block = "\n".join(lines)

    base_list_comment = ", ".join(bases)
    guard_pre, guard_post = original_enter_guard(onenter)
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
{guard_pre}{original_block}{guard_post}
    object oEnterer = GetEnteringObject();
    if (GetIsPC(oEnterer))
    {{
{report_block}
        // Restart the heartbeat on every area entry. An area change ends the heartbeat's timer chain, and the
        // staleness check inside the poll only notices that when the game clock steps back by a whole second;
        // a smaller step left the heartbeat dead (no polls at all) until the next transition. Starting it
        // bumps its generation, so any older chain ends itself at its next tick and exactly one chain
        // survives, attached to this area.
        ExecuteScript("ap_heartbeat", OBJECT_SELF);
        ExecuteScript("ap_poll_shared", OBJECT_SELF);
    }}
}}
"""
    nss_path = os.path.join(TRAMPOLINE_SRC_DIR, f"{onenter}.nss")
    with open(nss_path, "w") as f:
        f.write(trampoline_src)

    for base in bases:
        mapping[base] = {"idx": area_info[base]["idx"], "onenter": onenter,
                         "renamed": renamed_for_base[base], "tag": area_info[base]["tag"]}
    tag_note = "" if len(bases) == 1 else f" (shared, {len(bases)} areas via runtime tag check)"
    print(f"{onenter}: covers {base_list_comment} -> preserved as {renamed_resref}, trampoline at {nss_path}{tag_note}")

with open(os.path.join(TRAMPOLINE_SRC_DIR, "_mapping.json"), "w") as f:
    json.dump(mapping, f, indent=2)

idx_to_name = {v["idx"]: k for k, v in mapping.items()}
with open(os.path.join(TRAMPOLINE_SRC_DIR, "_idx_to_name.json"), "w") as f:
    json.dump(idx_to_name, f, indent=2)

print(f"\n{len(mapping)} areas covered by {trampoline_counter} trampolines. Compile them next.")
