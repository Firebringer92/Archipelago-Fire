"""
Generates ap_poll_shared.nss -- the single "brain" script that all 97 area
trampolines call via ExecuteScript. Contains:
  - area-visited detection (compares current area tag to last-known)
  - quest-completion detection (all 185 *_DONE booleans from globalcat.2da)
  - companion-unlock detection (all 9 NPC_* slots, via IsAvailableCreature)

Each detected event is reported via KSE_Diag with an "AP|CHECK|<type>|<id>"
marker, picked up by the extender's existing kse.log tailer -- the same
pipeline already proven in phase 03.

This is the ONE file that needs editing/recompiling for future feature
additions (e.g. a credits-given check) -- the 97 area trampolines never
need to change again once generated.
"""
import argparse
import json
import os
import subprocess
import sys

from pykotor.extract.installation import Installation
from pykotor.resource.type import ResourceType
from pykotor.resource.formats.twoda import read_2da
from pykotor.resource.formats.gff import read_gff


def _arg_value(flag, default):
    for i, a in enumerate(sys.argv):
        if a == flag and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
        if a.startswith(flag + "="):
            return a.split("=", 1)[1]
    return default


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
from nwnnsscomp_path import resolve_nwnnsscomp  # noqa: E402 -- see that module's docstring
# The recruit markers' quest tags and companion order (position == Locations.py's
# companion_idx) are defined once, next to the global.jrl builder that declares them.
from build_ap_tracker_quest import RECRUITS, RECRUIT_QUEST_PREFIX  # noqa: E402
NWNNSSCOMP = resolve_nwnnsscomp()
SRC_DIR = os.path.join(REPO_ROOT, "extender", "scripts_src")
# Written by KotorClient.py on every successful Connect -- see its own
# SLOT_DATA_PATH/write_slot_data_for_patch_scripts() for why. Only read
# here when --area-randomizer isn't passed (KotorClient.py's automatic
# on-connect call always passes it explicitly, so this only affects
# someone running this script by hand without it -- a real, documented
# use case per this file's own Usage below, not hypothetical).
SLOT_DATA_PATH = os.path.join(REPO_ROOT, "extender", "area_trampolines", "_slot_data.json")

# This file must not be dev-only: a hardcoded GAME_DIR constant, or
# guessing area_randomizer from whichever AP_*.zip happened to be newest
# in Archipelago/output/, is fine on a single dev machine generating one
# seed at a time, but wrong the moment another machine/seed
# differs from that -- and broken entirely for a player joining someone
# ELSE's multiworld, who never has that zip at all. An earlier version
# of the script also only ever wrote the .nss source -- compiling
# and deploying to a live Override was always a separate manual step.
# Real fix: KotorClient.py now calls this script directly, every
# Connected, passing the ACTUAL connected slot_data's area_randomizer
# explicitly via --area-randomizer -- no guessing involved for that path.
# The fallback (now only used when the override flag isn't passed, i.e.
# someone running this by hand from the terminal) reads the same
# SLOT_DATA_PATH file KotorClient.py already writes, rather than
# re-deriving it from a seed zip that may not even exist.
#
# loot_mode used to also flow through here (bonus mode's grant logic
# lived in this file as CheckPickupCount()) -- moved entirely into
# patch_item_suppression.py's HandleAcquiredItem() instead (see that
# file's build_handler_body() docstring), since it already runs
# per real Mod_OnAcquirItem event rather than on a fixed timer regardless
# of activity. Nothing in this file depends on loot_mode any more.
parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--game-dir", default=DEFAULT_GAME_DIR,
                     help=r"Your KOTOR install folder, the one with swkotor.exe (default: the standard Steam location).")
parser.add_argument("--area-randomizer", type=int, default=None, choices=[0, 1],
                     help="1 if the seed has area_randomizer=True, 0 otherwise, to use directly instead of "
                          "reading it from _slot_data.json (see SLOT_DATA_PATH above).")
parser.add_argument("--additional-enemies", type=int, default=None, choices=[0, 1],
                     help="1 if the seed has additional_enemies_mode != 0, 0 otherwise, to use directly "
                          "instead of reading it from _slot_data.json (see SLOT_DATA_PATH above).")
parser.add_argument("--no-deploy", action="store_true",
                     help="Only write the .nss source -- skip compiling and deploying to --game-dir's Override "
                          "(matches this script's old dev-only behavior).")
parser.add_argument("--dispatch-test", action="store_true", help="Kept so older callers still work; the dispatcher is always in the poll now.")
parser.add_argument("--no-dispatcher", action="store_true",
                     help="Leaves the job dispatcher out of the poll (only for comparing against a build without it).")
cli_args = parser.parse_args()
# Every delivery goes through the job dispatcher (generate_trampoline_batch.py's old staged path is retired), so it is part of the poll.
cli_args.dispatch_test = not cli_args.no_dispatcher
GAME_DIR = cli_args.game_dir


def _connected_wants_additional_enemies() -> bool:
    """True if _slot_data.json has additional_enemies_mode != 0. Gates
    CheckBountyCount() the same way _connected_wants_area_randomizer()
    gates CheckPlanetAvailability() -- see that function's docstring for
    why this file reads slot_data directly rather than assuming every
    seed wants every check. Returns False (the safe default) if the file
    is missing/unparseable."""
    if not os.path.isfile(SLOT_DATA_PATH):
        return False
    try:
        with open(SLOT_DATA_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return bool(data.get("additional_enemies_mode", 0))
    except Exception as e:
        print(f"  (couldn't read {SLOT_DATA_PATH}: {e})")
        return False


def _connected_wants_droid_look() -> bool:
    """True if _slot_data.json has starting_class == 4 (droid). Gates CheckDroidLook(), the same way
    _connected_wants_additional_enemies() gates CheckBountyCount(). False (the safe default) when the file is missing."""
    if not os.path.isfile(SLOT_DATA_PATH):
        return False
    try:
        with open(SLOT_DATA_PATH, encoding="utf-8") as f:
            return int(json.load(f).get("starting_class", 0)) == 4
    except Exception as e:
        print(f"  (couldn't read {SLOT_DATA_PATH}: {e})")
        return False


def _connected_wants_area_randomizer() -> bool:
    """True if _slot_data.json (written by KotorClient.py on the last
    successful Connect) has area_randomizer=True. This file is normally
    seed-independent (every CheckX() function above fires unconditionally
    regardless of options), but planet-availability forcing is the one
    exception: it's only correct when doors are actually shuffled (see
    the CheckGoal-adjacent block below for why), so it needs to know the
    real option value rather than always firing. Returns False (the safe
    default) if that file doesn't exist yet or doesn't parse -- connect
    once with KotorClient.py first if you want this to reflect a real
    seed instead."""
    if not os.path.isfile(SLOT_DATA_PATH):
        return False
    try:
        with open(SLOT_DATA_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return bool(data.get("area_randomizer", False))
    except Exception as e:
        print(f"  (couldn't read {SLOT_DATA_PATH}: {e})")
        return False

installation = Installation(GAME_DIR)
res = installation.resource("globalcat", ResourceType.TwoDA)
twoda = read_2da(res.data)

done_flags = []
plot_flags = []
for i in range(twoda.get_height()):
    row = twoda.get_row(i)
    name = row.get_string("name")
    typ = row.get_string("type")
    if name.upper().endswith("_DONE") and typ == "Boolean":
        done_flags.append(name)
    elif name.upper().endswith("_PLOT") and typ == "Number":
        plot_flags.append(name)

print(f"Generating checks for {len(done_flags)} quest flags, {len(plot_flags)} plot trackers")

# Locations are built from the journal, not these flags -- see CheckJournal
# below. CheckQuests()/CheckPlot() (using done_flags/plot_flags above) stay
# only as bonus reconciliation-side signal, not a location source: the
# player never sees these internal flags flip, only their journal update.
jrl_res = installation.resource("global", ResourceType.JRL)
jrl_gff = read_gff(jrl_res.data)
journal_tags = [
    jrl_gff.root.get_list("Categories").at(i).get_string("Tag")
    for i in range(len(jrl_gff.root.get_list("Categories")))
]
print(f"Generating journal checks for {len(journal_tags)} quest categories (player-visible)")

lines = []
lines.append("// AUTO-GENERATED by scripts/generate_poll_shared.py -- do not hand-edit.")
lines.append("// The single shared 'brain' script every area trampoline calls via")
lines.append("// ExecuteScript(\"ap_poll_shared\", OBJECT_SELF). Editing/recompiling THIS")
lines.append("// file is the only redevelopment cost for new checks -- the 97 area")
lines.append("// trampolines that call it never need to change.")
lines.append('#include "kse"')
lines.append('#include "ap_jolee_field"')
lines.append('#include "ap_lev_cast"')
lines.append("")
lines.append("// Area-visited checks are done INLINE in each area trampoline, not here --")
lines.append("// a global set immediately before ExecuteScript was confirmed NOT visible")
lines.append("// to the called script in this engine build (true for both string and")
lines.append("// number globals). See generate_area_trampolines.py for the area-check")
lines.append("// logic and PHASE10 notes for the full writeup.")
lines.append("")
lines.append("// NOTE: custom (non-globalcat.2da) global variable names were confirmed")
lines.append("// this session to NOT persist in this engine build -- SetGlobalBoolean/")
lines.append("// SetGlobalNumber on any made-up name silently fails to stick, even")
lines.append("// same-tick in the cleanest possible test. So none of the checks below")
lines.append("// use custom globals for dedup/seen-tracking any more -- they report")
lines.append("// UNCONDITIONALLY every poll whenever the real, engine-native condition")
lines.append("// (a real globalcat.2da quest flag, IsAvailableCreature, current XP) is")
lines.append("// true. Deduplication now lives on the extender/AP-client side, which has")
lines.append("// real, uncapped persistent storage -- not in the game scripts.")
lines.append("//")
lines.append("// Nothing in the client reads CHECK|QUEST (locations are journal-based), so it is only a")
lines.append("// support record: a flag is printed when it is first seen set and when it changes, not")
lines.append("// every poll. One KSE data-store string (\"q_bits\", one 0/1 character per flag) holds the")
lines.append("// previous poll's state; after a game restart the first poll prints every flag that is set.")
lines.append("void CheckQuests()")
lines.append("{")
lines.append('    string sNow = "";')
for name in done_flags:
    lines.append(f'    sNow = sNow + IntToString(GetGlobalBoolean("{name}"));')
lines.append('    string sLast = "";')
lines.append('    if (KSE_HasData("q_bits")) sLast = KSE_GetData("q_bits");')
lines.append("    if (sNow == sLast) return;")
lines.append('    KSE_SetData("q_bits", sNow);')
for i, name in enumerate(done_flags):
    lines.append(f'    if (GetSubString(sNow, {i}, 1) == "1" && GetSubString(sLast, {i}, 1) != "1")')
    lines.append(f'        KSE_Diag(21, "AP|CHECK|QUEST|{name}");')
lines.append("}")
lines.append("")
lines.append("// _PLOT trackers are real globalcat.2da Number globals (same proven-")
lines.append("// reliable category as the _DONE booleans above -- not a custom name, so")
lines.append("// no workaround needed). Reports the CURRENT stage value every poll,")
lines.append("// skipping 0 (not-yet-started, nothing for the client to act on). The")
lines.append("// client derives 'newly reached stage N' by comparing against its own")
lines.append("// memory of the highest stage already converted into a check, and can")
lines.append("// map each newly-crossed threshold to a separate AP location.")
lines.append("// Like CheckQuests, printed on change only (nothing in the client reads CHECK|PLOT): the")
lines.append("// previous poll's values are kept in one data-store string, 3 digits per tracker (\"p_vals\").")
lines.append("void CheckPlot()")
lines.append("{")
lines.append('    string sNow = "";')
for name in plot_flags:
    lines.append(f'    sNow = sNow + GetStringRight(IntToString(1000 + GetGlobalNumber("{name}")), 3);')
lines.append('    string sLast = "";')
lines.append('    if (KSE_HasData("p_vals")) sLast = KSE_GetData("p_vals");')
lines.append("    if (sNow == sLast) return;")
lines.append('    KSE_SetData("p_vals", sNow);')
for i, name in enumerate(plot_flags):
    lines.append(f'    if (GetSubString(sNow, {3 * i}, 3) != GetSubString(sLast, {3 * i}, 3) && GetSubString(sNow, {3 * i}, 3) != "000")')
    lines.append(f'        KSE_Diag(25, "AP|CHECK|PLOT|{name}|value=" + IntToString(StringToInt(GetSubString(sNow, {3 * i}, 3))));')
lines.append("}")
lines.append("")
lines.append("// Game-wide quest tracking via KOTOR's own journal system -- covers all")
lines.append("// 9 planets (the _DONE/_PLOT globals above are Dantooine/Manaan-specific")
lines.append("// internal bookkeeping, not player-visible, so they aren't used as a")
lines.append("// location source; the journal is what the player actually sees update).")
lines.append("// GetJournalEntry(tag) reads the current stage for any quest, same")
lines.append("// reliability class as GetGlobalNumber -- a real, documented engine call,")
lines.append("// not a workaround. Reports nonzero stages every poll, same stateless")
lines.append("// pattern as CheckPlot(): the client tracks which (tag, stage) pairs it's")
lines.append("// already converted into a check.")
lines.append("//")
lines.append("// Printed on change plus a full re-dump on the first poll and then every 12th (about once a")
lines.append("// minute), not every 5 s: a client that attaches late or reconnects mid-session still catches")
lines.append("// up within a minute, and the tracker ignores repeats anyway. The previous poll's values are")
lines.append("// one data-store string, 3 digits per quest (\"j_vals\"; stages are well under 1000).")
lines.append("void CheckJournal()")
lines.append("{")
lines.append("    int nJ = 0;")
lines.append('    if (KSE_HasData("j_n")) nJ = StringToInt(KSE_GetData("j_n"));')
lines.append('    KSE_SetData("j_n", IntToString(nJ + 1));')
lines.append("    int bFull = (nJ % 12 == 0);")
lines.append('    string sNow = "";')
for tag in journal_tags:
    lines.append(f'    sNow = sNow + GetStringRight(IntToString(1000 + GetJournalEntry("{tag}")), 3);')
lines.append('    string sLast = "";')
lines.append('    if (KSE_HasData("j_vals")) sLast = KSE_GetData("j_vals");')
lines.append("    if (sNow == sLast && !bFull) return;")
lines.append('    KSE_SetData("j_vals", sNow);')
for i, tag in enumerate(journal_tags):
    lines.append(f'    if (GetSubString(sNow, {3 * i}, 3) != "000" && (bFull || GetSubString(sNow, {3 * i}, 3) != GetSubString(sLast, {3 * i}, 3)))')
    lines.append(f'        KSE_Diag(30, "AP|CHECK|JOURNAL|{tag}|value=" + IntToString(StringToInt(GetSubString(sNow, {3 * i}, 3))));')
lines.append("}")
lines.append("")
lines.append("// Persistent companion-recruit markers. The recruit scripts report")
lines.append("// AP|CHECK|COMPANION|<idx> exactly once, at the moment of recruitment; if no")
lines.append("// client was attached then, that line is gone for good. They also write the")
lines.append("// journal quest ap_recruit_<key> (build_ap_tracker_quest.py / ap_recruit_")
lines.append("// marker.nss), which lives in the SAVE, and this re-reports every set one on")
lines.append("// every poll -- the same stateless pattern as CheckJournal() above. The client")
lines.append("// dedups against its checked locations, so repeats are harmless. Not a")
lines.append("// IsAvailableCreature poll: slot 0 is reused by Trask in the prologue.")
lines.append("// GetJournalEntry reads -1 for a quest global.jrl doesn't declare, so this")
lines.append("// is simply silent on an install without the recruit quests.")
lines.append("void CheckRecruitMarkers()")
lines.append("{")
for _idx, (_key, _display) in enumerate(RECRUITS):
    lines.append(f'    if (GetJournalEntry("{RECRUIT_QUEST_PREFIX}{_key}") > 0)')
    lines.append(f'        KSE_Diag(22, "AP|CHECK|COMPANION|{_idx}");')
lines.append("}")
lines.append("")
lines.append("// Entitlement markers (build_ap_tracker_quest.py): per companion 0 = none, 10 = entitled (written by the grant arm), 20 = trapped off.")
lines.append("void CheckCrewMarkers()")
lines.append("{")
lines.append("    string sReport = \"AP|CREWREPORT\";")
lines.append("    sReport = sReport + \"|bastila=\" + IntToString(GetJournalEntry(\"ap_ent_bastila\"));")
lines.append("    sReport = sReport + \"|canderous=\" + IntToString(GetJournalEntry(\"ap_ent_canderous\"));")
lines.append("    sReport = sReport + \"|carth=\" + IntToString(GetJournalEntry(\"ap_ent_carth\"));")
lines.append("    sReport = sReport + \"|hk47=\" + IntToString(GetJournalEntry(\"ap_ent_hk47\"));")
lines.append("    sReport = sReport + \"|jolee=\" + IntToString(GetJournalEntry(\"ap_ent_jolee\"));")
lines.append("    sReport = sReport + \"|juhani=\" + IntToString(GetJournalEntry(\"ap_ent_juhani\"));")
lines.append("    sReport = sReport + \"|mission=\" + IntToString(GetJournalEntry(\"ap_ent_mission\"));")
lines.append("    sReport = sReport + \"|t3m4=\" + IntToString(GetJournalEntry(\"ap_ent_t3m4\"));")
lines.append("    sReport = sReport + \"|zaalbar=\" + IntToString(GetJournalEntry(\"ap_ent_zaalbar\"));")
lines.append("    KSE_Diag(192, sReport);")
lines.append("}")
lines.append("")
lines.append("// Level of every party member, logged when it changes. Companions only")
lines.append("// level from real combat XP (the PC's XP is set directly by AP items), so")
lines.append("// this shows how far behind they are. The PC's tag is empty.")
lines.append("void CheckPartyLevels()")
lines.append("{")
lines.append('    string sLevels = "";')
lines.append("    int nMember = 0;")
lines.append("    while (nMember < 3)")
lines.append("    {")
lines.append("        object oMember = GetPartyMemberByIndex(nMember);")
lines.append("        if (GetIsObjectValid(oMember))")
lines.append("        {")
lines.append('            string sTag = GetTag(oMember);')
lines.append('            if (sTag == "") sTag = "pc";')
lines.append('            sLevels = sLevels + sTag + "=" + IntToString(GetHitDice(oMember)) + "|";')
lines.append("        }")
lines.append("        nMember = nMember + 1;")
lines.append("    }")
lines.append('    string sLast = "";')
lines.append('    if (KSE_HasData("party_levels")) sLast = KSE_GetData("party_levels");')
lines.append("    if (sLevels != sLast)")
lines.append("    {")
lines.append('        KSE_SetData("party_levels", sLevels);')
lines.append('        KSE_Diag(177, "AP|PARTYLEVELS|" + sLevels);')
lines.append("    }")
lines.append("}")
lines.append("")
lines.append("// True while a scripted scene has companions staged or held on purpose: the")
lines.append("// Leviathan sequence, the Zaalbar/Jolee temporary-companion scenes (PC local")
lines.append("// boolean 78 and the Taris KSE flags) and the Bastila+Carth party gate")
lines.append("// (module local boolean 50). Shared by the roster report and the stuck-")
lines.append("// companion check, which must both leave such scenes alone.")
lines.append("// Which scene holds the busy flag, as bits (1 Leviathan sequence, 2 PC boolean 78 = Jolee's field scene, 4 forcefield Mission staging,")
lines.append("// 8 Zaalbar Mission staging, 16 the Bastila+Carth party gate; the roster report adds 32 for a conversation and 64 for an Unknown World")
lines.append("// module). The roster report carries it as bz= so a flag that never clears shows up in the log.")
lines.append("int ApSceneBusyMask()")
lines.append("{")
lines.append("    object oPC = GetFirstPC();")
lines.append("    int nMask = 0;")
lines.append("    if (InLeviathanSequence()) nMask = nMask + 1;")
lines.append("    // Not 77: that PC boolean is the Zaalbar cell scene's permanent \"already played\" marker (ap_zaal_mission.nss), so treating it as busy kept")
lines.append("    // every busy-gated correction switched off for the rest of the game once the scene had played. Its staging is the KSE flag below.")
lines.append("    if (GetLocalBoolean(oPC, 78)) nMask = nMask + 2;")
lines.append("    if (KSE_GetData(\"ff_mission_staged\") == \"1\") nMask = nMask + 4;")
lines.append("    if (KSE_GetData(\"zaal_mission_staged\") == \"1\") nMask = nMask + 8;")
lines.append("    if (GetLocalBoolean(GetModule(), 50)) nMask = nMask + 16;")
lines.append("    // The Taris Duel Ring: the organizer's dialog (k_ptar_duelring) sets TAR_DUELINPROGRESS, takes the party out and jumps the player to the arena; the")
lines.append("    // end scripts (k_ptar_duelend, k_ptar_duelend2, k_ptar_dlcutend, k_ptar_dueply_ex) clear it and restore the party by index from stored globals, so no companion or")
lines.append("    // class job may run meanwhile. Only counted inside the cantina module, so a flag left set by a crash cannot hold deliveries elsewhere.")
lines.append("    if (GetGlobalBoolean(\"TAR_DUELINPROGRESS\") && GetStringLowerCase(GetModuleFileName()) == \"tar_m02ae\") nMask = nMask + 32;")
lines.append("    return nMask;")
lines.append("}")
lines.append("")
lines.append("int ApSceneBusy()")
lines.append("{")
lines.append("    if (ApSceneBusyMask() != 0) return TRUE;")
lines.append("    return FALSE;")
lines.append("}")
lines.append("")
lines.append("// Companions that stop following or stop fighting (seen live: they stand")
lines.append("// still while the leader walks off or fights, whatever else is going on).")
lines.append("// For each of the two companion slots, counted in polls (about 5 s each):")
lines.append("//   uncommandable   the companion is not commandable (a scene's lock that")
lines.append("//                   was never released) for 2 polls")
lines.append("//   idle_far        idle (empty action queue) more than 10 m from the leader")
lines.append("//                   for 3 polls: not following")
lines.append("//   other_area      the companion is not in the leader's area (left behind by an")
lines.append("//                   area change) for 3 polls")
lines.append("//   idle_in_combat  the leader is in combat and the companion is not, and")
lines.append("//                   idle, for 2 polls: not engaging")
lines.append("// The fix clears the companion's actions and makes them commandable; for")
lines.append("// idle_far it also sends them to the leader, for idle_in_combat to the")
lines.append("// nearest enemy, and a companion that is stuck again soon after a fix, or more")
lines.append("// than 30 m away, is teleported 2 m from the leader. Left alone: conversations, a restricted or")
lines.append("// uncommandable leader, scenes ApSceneBusy() reports and the Endar Spire")
lines.append("// prologue. Each fix is logged")
lines.append("// as AP|COMPANIONFIX. Counters live in KSE data (in-DLL memory).")
lines.append("// One companion slot of CheckCompanionStuck. Written with early RETURNS and nested ifs, never")
lines.append("// `continue`: the first version looped over both slots with `continue`, and from the")
lines.append("// first conversation after it was deployed the poll stopped partway at that call on")
lines.append("// every run (seen live, twice; every other check after it never ran).")
lines.append("void CheckCompanionSlot(int nIdx, object oLeader, int bSkip, int bNoMove, int nPoll)")
lines.append("{")
lines.append("    string sK = IntToString(nIdx);")
lines.append("    int nStreak = 0;")
lines.append('    if (KSE_HasData("cs_streak_" + sK)) nStreak = StringToInt(KSE_GetData("cs_streak_" + sK));')
lines.append('    KSE_SetData("cs_streak_" + sK, "0");')
lines.append("    if (bSkip) return;")
lines.append("    object oM = GetPartyMemberByIndex(nIdx);")
lines.append("    if (!GetIsObjectValid(oM)) return;")
lines.append("    if (GetIsDead(oM)) return;")
lines.append("")
lines.append("    int nAct = GetCurrentAction(oM);")
lines.append("    int bSameArea = (GetArea(oM) == GetArea(oLeader));")
lines.append("    float fDist = -1.0;")
lines.append("    if (bSameArea) fDist = GetDistanceBetween(oM, oLeader);")
lines.append("    int bIdle = (nAct == ACTION_QUEUEEMPTY || nAct == ACTION_INVALID);")
lines.append('    string sType = "";')
lines.append("    int nNeed = 3;")
lines.append('    if (!bSameArea) sType = "other_area";')
lines.append('    else if (!GetCommandable(oM)) { sType = "uncommandable"; nNeed = 2; }')
lines.append("    // Not engaging: the leader fights and this companion does not, whether it stands idle or just")
lines.append("    // keeps following (seen live in the Star Forge). A passive party AI style is the player's")
lines.append("    // choice and is left alone.")
lines.append('    else if (GetIsInCombat(oLeader) && !GetIsInCombat(oM) && (bIdle || nAct == ACTION_FOLLOWLEADER) && fDist < 30.0 && GetPartyAIStyle() != PARTY_AISTYLE_PASSIVE) { sType = "idle_in_combat"; nNeed = 2; }')
lines.append('    else if (bIdle && fDist > 10.0) sType = "idle_far";')
lines.append('    if (sType == "") return;')
lines.append("    // Scenes that park or jump companions on purpose allow only the combat fix, never a move or teleport.")
lines.append('    if (bNoMove && sType != "idle_in_combat") return;')
lines.append("")
lines.append("    nStreak = nStreak + 1;")
lines.append('    KSE_SetData("cs_streak_" + sK, IntToString(nStreak));')
lines.append("    int nCool = 0;")
lines.append('    if (KSE_HasData("cs_cool_" + sK)) nCool = StringToInt(KSE_GetData("cs_cool_" + sK));')
lines.append("    if (nStreak < nNeed) return;")
lines.append("    if (nPoll < nCool) return;")
lines.append("")
lines.append("    // Stuck again soon after a fix (within 24 polls) or more than 30 m away: jump straight to the leader.")
lines.append("    int nLastFix = -1000;")
lines.append('    if (KSE_HasData("cs_fix_" + sK)) nLastFix = StringToInt(KSE_GetData("cs_fix_" + sK));')
lines.append("    int bEscalate = (nPoll - nLastFix <= 24 || fDist > 30.0);")
lines.append("    SetCommandable(TRUE, oM);")
lines.append("    AssignCommand(oM, ClearAllActions());")
lines.append("    // The spot 2 m from the leader: slot 1 behind-left, slot 2 behind-right of the way the leader")
lines.append("    // faces, so a teleported companion is next to them, not on them.")
lines.append("    vector vLead = GetPosition(oLeader);")
lines.append("    float fSide = 150.0;")
lines.append("    if (nIdx == 2) fSide = 210.0;")
lines.append("    float fRad = (GetFacing(oLeader) + fSide) * 0.0174533;")
lines.append("    vector vJump = Vector(vLead.x + 2.0 * cos(fRad), vLead.y + 2.0 * sin(fRad), vLead.z);")
lines.append('    if (sType == "idle_in_combat")')
lines.append("    {")
lines.append("        object oEnemy = GetNearestCreature(CREATURE_TYPE_REPUTATION, REPUTATION_TYPE_ENEMY, oM, 1,")
lines.append("            CREATURE_TYPE_IS_ALIVE, TRUE, CREATURE_TYPE_PERCEPTION, PERCEPTION_SEEN);")
lines.append("        if (!GetIsObjectValid(oEnemy))")
lines.append("            oEnemy = GetNearestCreature(CREATURE_TYPE_REPUTATION, REPUTATION_TYPE_ENEMY, oLeader, 1,")
lines.append("                CREATURE_TYPE_IS_ALIVE, TRUE, CREATURE_TYPE_PERCEPTION, PERCEPTION_SEEN);")
lines.append("        if (GetIsObjectValid(oEnemy)) AssignCommand(oM, ActionAttack(oEnemy));")
lines.append("    }")
lines.append('    else if (sType == "other_area")')
lines.append("    {")
lines.append("        // Left behind in the area they came from: only a jump to an object crosses areas. It lands")
lines.append("        // them on the leader, so a moment later move them to the spot.")
lines.append("        AssignCommand(oM, JumpToObject(oLeader));")
lines.append("        DelayCommand(0.5, AssignCommand(oM, ActionJumpToLocation(Location(vJump, GetFacing(oLeader)))));")
lines.append("    }")
lines.append("    else if (bEscalate)")
lines.append("    {")
lines.append("        AssignCommand(oM, ActionJumpToLocation(Location(vJump, GetFacing(oLeader))));")
lines.append("    }")
lines.append('    else if (sType == "idle_far")')
lines.append("    {")
lines.append("        AssignCommand(oM, ActionMoveToObject(oLeader, TRUE, 3.0));")
lines.append("    }")
lines.append('    KSE_SetData("cs_streak_" + sK, "0");')
lines.append('    KSE_SetData("cs_fix_" + sK, IntToString(nPoll));')
lines.append('    KSE_SetData("cs_cool_" + sK, IntToString(nPoll + 6));')
lines.append('    KSE_Diag(174, "AP|COMPANIONFIX|" + sType + "|" + GetTag(oM) + "|dist=" + IntToString(FloatToInt(fDist))')
lines.append('        + "|action=" + IntToString(nAct) + "|escalated=" + IntToString(bEscalate));')
lines.append("}")
lines.append("")
lines.append("void CheckCompanionStuck()")
lines.append("{")
lines.append("    object oLeader = GetPartyMemberByIndex(0);")
lines.append("    object oPC = GetFirstPC();")
lines.append("    // Poll counter for the fix cooldowns below; every caller of the poll (heartbeat and area trampolines) advances it.")
lines.append("    int nPoll = 0;")
lines.append('    if (KSE_HasData("cs_poll")) nPoll = StringToInt(KSE_GetData("cs_poll"));')
lines.append("    nPoll = nPoll + 1;")
lines.append('    KSE_SetData("cs_poll", IntToString(nPoll));')
lines.append("    int bSkip = FALSE;")
lines.append("    int bNoMove = FALSE;")
lines.append("    if (!GetIsObjectValid(oLeader)) bSkip = TRUE;")
lines.append("    else if (!GetIsObjectValid(oPC)) bSkip = TRUE;")
lines.append("    else if (GetPartyMemberCount() < 2) bSkip = TRUE;")
lines.append("    else if (GetIsDead(oPC)) bSkip = TRUE;")
lines.append("    else if (GetIsInConversation(oPC)) bSkip = TRUE;")
lines.append("    else if (!GetCommandable(oPC)) bSkip = TRUE;")
lines.append("    else if (GetPlayerRestrictMode(oPC)) bSkip = TRUE;")
lines.append("    else if (ApSceneBusy()) bSkip = TRUE;")
lines.append("    if (!bSkip)")
lines.append("    {")
lines.append("        // The prologue is left entirely alone. Scenes that park or jump party members on purpose")
lines.append("        // (the Unknown World guide ritual and temple: solo mode, floor-panel puzzle, summit")
lines.append("        // staging; the Star Forge; the cutscene modules) get only the combat fix, never a move.")
lines.append("        string sMod = GetStringLowerCase(GetModuleFileName());")
lines.append('        if (GetStringLeft(sMod, 7) == "end_m01") bSkip = TRUE;')
lines.append('        else if (sMod == "unk_m41ad") bNoMove = TRUE;')
lines.append('        else if (GetStringLeft(sMod, 7) == "unk_m44") bNoMove = TRUE;')
lines.append('        else if (GetStringLeft(sMod, 7) == "sta_m45") bNoMove = TRUE;')
lines.append('        else if (GetStringLeft(sMod, 5) == "stunt") bNoMove = TRUE;')
lines.append("    }")
lines.append("    CheckCompanionSlot(1, oLeader, bSkip, bNoMove, nPoll);")
lines.append("    CheckCompanionSlot(2, oLeader, bSkip, bNoMove, nPoll);")
lines.append("}")
lines.append("")
# REMOVED: CheckCompanions() used to poll IsAvailableCreature(i) for all 9
# NPC_* slots every heartbeat. Confirmed BROKEN live -- slot 0 (NPC_BASTILA)
# is reused by Trask Ulgo during the Endar Spire prologue
# (k_pend_traskdl29 calls AddAvailableNPCByTemplate(0, "end_trask")), so
# this fired a false "Bastila recruited" check within the first minute of
# a new game, long before she's actually rescued. All 9 companions already
# have a dedicated wrapper script hooked directly into their REAL
# recruitment script (k_ptar_bastpart, k_ptar_candadd, k_ptar_addcarth,
# k_ptat_hk47add, k_pkas_joleejoin, k_pdan_vandar02, k_ptar_addmissio,
# k_ptar_addt3m4, k_ptar_addzaal -- see extender/scripts_src/), each
# emitting the same AP|CHECK|COMPANION|<idx> diag at the exact right
# moment with no slot-reuse ambiguity. This generic poll was 100%
# redundant even before the Trask collision was found, and strictly less
# accurate -- removed rather than patched to exclude index 0, since the
# same class of bug could exist for other slots too and was never actually
# needed.
lines.append("")
lines.append("// XP handling has moved off the old in-game revert-on-detect design")
lines.append("// entirely: the game no longer decides what XP is 'legitimate'. It just")
lines.append("// honestly reports current XP every poll -- the AP client is authoritative")
lines.append("// on what XP the player SHOULD have (sum of AP-granted XP items so far)")
lines.append("// and sends back a SetXP correction through the existing apply pipeline")
lines.append("// when the reported value doesn't match. No in-game persistence needed.")
lines.append("void CheckXP()")
lines.append("{")
lines.append("    object oPC = GetFirstPC();")
lines.append('    KSE_Diag(24, "AP|XPREPORT|current=" + IntToString(GetXP(oPC)));')
lines.append("}")
lines.append("")
lines.append("// Same stateless model as XP -- credits picked up from loot/kills need the")
lines.append("// same suppression treatment as items, not just the explicit \"credits\" AP")
lines.append("// grant item. The STOREOPENED markers already snapshot credits at the start")
lines.append("// of a purchase; this is the continuous every-poll report the client needs")
lines.append("// to know the current total at all, same role CheckXP plays for XP.")
lines.append("void CheckCredits()")
lines.append("{")
lines.append("    object oPC = GetFirstPC();")
lines.append('    KSE_Diag(29, "AP|CREDITSREPORT|current=" + IntToString(GetGold(oPC)));')
lines.append("}")
lines.append("")
lines.append("// Same stateless design again: ability grants are written into the")
lines.append("// character's base scores, which live in the specific save they were")
lines.append("// applied to -- a brand new save (or a restarted playthrough) starts")
lines.append("// without them, same as vanilla. Reporting scores every poll lets the")
lines.append("// client notice a fresh save is behind what's actually been earned and")
lines.append("// reapply the missing grants automatically, instead of the player losing")
lines.append("// progress.")
lines.append("void CheckAbilityScores()")
lines.append("{")
lines.append("    object oPC = GetFirstPC();")
lines.append('    string sReport = "AP|ABILITYREPORT|str=" + IntToString(GetAbilityScore(oPC, ABILITY_STRENGTH))')
lines.append('        + "|dex=" + IntToString(GetAbilityScore(oPC, ABILITY_DEXTERITY))')
lines.append('        + "|con=" + IntToString(GetAbilityScore(oPC, ABILITY_CONSTITUTION))')
lines.append('        + "|int=" + IntToString(GetAbilityScore(oPC, ABILITY_INTELLIGENCE))')
lines.append('        + "|wis=" + IntToString(GetAbilityScore(oPC, ABILITY_WISDOM))')
lines.append('        + "|cha=" + IntToString(GetAbilityScore(oPC, ABILITY_CHARISMA));')
lines.append("    KSE_Diag(27, sReport);")
lines.append("    // GetAbilityScore is the EFFECTIVE score (base + item bonuses + temporary")
lines.append("    // effects such as combat debuffs). The native selector below logs the six")
lines.append("    // TRUE base scores as AP|ABILITYBASEREPORT right behind it; the client only")
lines.append("    // consults them when the effective score drops, to tell a temporary")
lines.append("    // debuff from a real loss.")
lines.append("    KSE_SetCreatureField(oPC, KSE_FIELD_REPORT_ABILITY_BASES(), 0);")
lines.append("}")
lines.append("")
lines.append("// Reports current Jedi class levels every poll so the client can check")
lines.append("// 'does this character already have class X' BEFORE sending a class-switch")
lines.append("// grant, not just trust its own delivery bookkeeping. AddMultiClass +")
lines.append("// ShowLevelUpGUI are one-shot, not safe to re-fire (confirmed: re-applying")
lines.append("// class_sentinel on an already-multiclassed character as part of a reconnect")
lines.append("// resend crashed the game). Bookkeeping alone can't be trusted across saves")
lines.append("// (an older save reloaded later may genuinely still need the grant), so this")
lines.append("// reads real game state instead -- self-correcting regardless of which save")
lines.append("// is currently loaded.")
lines.append("void CheckClasses()")
lines.append("{")
lines.append("    object oPC = GetFirstPC();")
lines.append('    string sReport = "AP|CLASSREPORT|guardian=" + IntToString(GetLevelByClass(CLASS_TYPE_JEDIGUARDIAN, oPC))')
lines.append('        + "|consular=" + IntToString(GetLevelByClass(CLASS_TYPE_JEDICONSULAR, oPC))')
lines.append('        + "|sentinel=" + IntToString(GetLevelByClass(CLASS_TYPE_JEDISENTINEL, oPC));')
# kotor_reconciliation.py's _CLASSREPORT_RE expects an optional trailing
# "|baseclass=X|baselevel=Y" -- this generator must actually emit it, or
# any reader of current_classes.get("baselevel", 0) silently gets the 0
# default and treats every non-Jedi character as level 0 regardless of
# their real level.
# Position 1 (NWScript's class positions are 1-indexed, confirmed via
# nwscript.nss's own doc comment: "nClassPosition: 1, 2 or 3" -- a
# single-class creature only ever has a value at position 1) is always the
# character's ORIGINAL class slot (Soldier/Scout/Scoundrel for anyone who
# hasn't been made a Jedi via AddMultiClass yet, or whatever they started
# as even after a later class gets ADDED at position 2) -- GetLevelByClass
# above already covers the 3 Jedi classes separately, so this is
# deliberately just the base slot, not total level.
# KNOWN CAVEAT, not fixed here: if starting_class=jedi_start/jedi_granted
# ever puts a Jedi class directly at position 1 with no separate base slot
# at all (not the case for this project's current jedi_granted flow, which
# starts a normal base class and adds Jedi later), this would double-count
# that level once here and once via the matching GetLevelByClass line above
# -- worth revisiting if that flow ever changes.
lines.append('    int nBaseClass = GetClassByPosition(1, oPC);')
lines.append('    int nBaseLevel = GetLevelByPosition(1, oPC);')
lines.append('    sReport = sReport + "|baseclass=" + IntToString(nBaseClass) + "|baselevel=" + IntToString(nBaseLevel);')
lines.append("    KSE_Diag(65, sReport);")
lines.append("}")
lines.append("")
lines.append("// Reports current base-class (position 1) for each of the 7 non-droid")
lines.append("// companions, so the reconciler can self-heal a companion's class the same")
lines.append("// way CheckClasses() does for the PC -- companion class previously had NO")
lines.append("// live polling at all, only a one-shot recruit-time send with no way to")
lines.append("// detect drift afterward (e.g. a crash/reload landing on a save from before")
lines.append("// a companion_class grant actually took). -1 means not currently recruited")
lines.append("// (IsNPCPartyMember false) -- distinct from a real CLASS_TYPE_* value,")
lines.append("// including CLASS_TYPE_SOLDIER's own 0. HK-47/T3-M4 (droids) are excluded --")
lines.append("// Randomize_class never targets them, same scope as _COMPANION_NPC_CONST in")
lines.append("// generate_trampoline_batch.py.")
lines.append("void CheckCompanionClasses()")
lines.append("{")
lines.append('    string sReport = "AP|COMPANIONCLASSREPORT";')
_COMPANION_CLASS_POLL = [
    ("bastila", "Bastila", "NPC_BASTILA"),
    ("canderous", "Cand", "NPC_CANDEROUS"),
    ("carth", "Carth", "NPC_CARTH"),
    ("jolee", "Jolee", "NPC_JOLEE"),
    ("juhani", "Juhani", "NPC_JUHANI"),
    ("mission", "Mission", "NPC_MISSION"),
    ("zaalbar", "Zaalbar", "NPC_ZAALBAR"),
]
for key, tag, npc_const in _COMPANION_CLASS_POLL:
    var = key[0].upper() + key[1:]
    lines.append(f'    object o{var} = GetObjectByTag("{tag}");')
    lines.append(f'    int n{var} = -1;')
    lines.append(f'    if (IsNPCPartyMember({npc_const}) && GetIsObjectValid(o{var}))')
    lines.append("    {")
    lines.append(f'        n{var} = GetClassByPosition(1, o{var});')
    lines.append("    }")
    lines.append(f'    sReport = sReport + "|{key}=" + IntToString(n{var});')
lines.append('    KSE_Diag(138, sReport);')
lines.append("}")
lines.append("")

# The feats CheckFeats() reports for the player character (the reconciler's fallback when the full list has not arrived yet; the Remove Half Known
# Feats trap uses the full list from CheckFeatsFull()): the ids the feat training offers plus the Jedi class feats.
_PC_FEAT_SCAN_IDS = sorted({40, 42, 43, 4, 5, 6, 14, 28, 29, 11, 30, 8, 31, 60, 104, 101, 88, 98, 55, 107, 116})

# Items whose silent loss would strand the player (the 24 story-gate progression items and the Archipelago Vendor
# passes). A narrow, targeted GetItemPossessedBy() check per resref, not full reconciliation -- these
# are simple possession facts (has it or doesn't). Keep this list in sync by hand with entitlement.py's
# own PROGRESSION_ITEM_RESREFS and worlds/kotor/Items.py's PROGRESSION_ITEM_RESREFS (these three don't share an import boundary).
_PROGRESSION_ITEM_RESREFS = [
    (f"tok_{_key}{_n}", f"ap_tk_{_key}{_n}")
    for _key in ("tar", "dan", "tat", "kas", "man", "kor", "unk", "fin") for _n in (1, 2, 3)
] + [
    # Archipelago Vendor passes -- same keys/order as entitlement.py's PROGRESSION_ITEM_RESREFS.
    ("vendor_skill", "ap_vtok_skill"),
    ("vendor_ability", "ap_vtok_abil"),
    ("vendor_feat", "ap_vtok_feat"),
    ("vendor_power", "ap_vtok_power"),
    ("vendor_align", "ap_vtok_align"),
] + [
    # 0.2.0 plot items -- same keys/order as entitlement.py's PROGRESSION_ITEM_RESREFS.
    (f"ft_{_k}", f"ap_ft_{_k}") for _k in ("bastila", "canderous", "carth", "jolee", "juhani", "mission", "zaalbar")
] + [
    ("nc_console", "ap_nc_console"),
    ("party_console", "ap_partycon_a"),
]
lines.append("// Roster report for the reconciler's stray-companion cleanup (kotor_")
lines.append("// reconciliation.py). Reports which of the 9 companions are AVAILABLE (on the")
lines.append("// roster, whether or not they are in the active party) and whether a scripted")
lines.append("// scene currently has someone staged on purpose (busy=1): the Leviathan")
lines.append("// sequence, a conversation, or one of the temporary-companion scenes (PC local")
lines.append("// booleans 77 Zaalbar's cell scene, 78 Jolee's repulsor field). The reconciler")
lines.append("// compares it with what the player is ENTITLED to and purges the rest. Nothing")
lines.append("// is reported in the Endar Spire: slot 0 is Trask there, not Bastila.")
lines.append("void CheckRoster()")
lines.append("{")
lines.append("    object oPC = GetFirstPC();")
lines.append("    if (!GetIsObjectValid(oPC)) return;")
lines.append('    if (GetStringLeft(GetStringLowerCase(GetModuleFileName()), 7) == "end_m01") return;')
lines.append("    int nMask = ApSceneBusyMask();")
lines.append("    if (GetIsInConversation(oPC)) nMask = nMask + 32;")
lines.append("    // The Unknown World finale: its wrapper backfills Carth/Canderous/Mission/T3-M4")
lines.append("    // as available on purpose. The Star Forge is NOT busy: the reconciler's Star Forge")
lines.append("    // pass (sf/fc/bp below) cleans the roster there.")
lines.append("    string sRosterMod = GetStringLowerCase(GetModuleFileName());")
lines.append('    if (GetStringLeft(sRosterMod, 4) == "unk_") nMask = nMask + 64;')
lines.append("    int nBusy = 0;")
lines.append("    if (nMask != 0) nBusy = 1;")
lines.append('    string sReport = "AP|ROSTERREPORT|busy=" + IntToString(nBusy);')
lines.append('    sReport = sReport + "|bastila=" + IntToString(IsAvailableCreature(NPC_BASTILA));')
lines.append('    sReport = sReport + "|canderous=" + IntToString(IsAvailableCreature(NPC_CANDEROUS));')
lines.append('    sReport = sReport + "|carth=" + IntToString(IsAvailableCreature(NPC_CARTH));')
lines.append('    sReport = sReport + "|hk47=" + IntToString(IsAvailableCreature(NPC_HK_47));')
lines.append('    sReport = sReport + "|jolee=" + IntToString(IsAvailableCreature(NPC_JOLEE));')
lines.append('    sReport = sReport + "|juhani=" + IntToString(IsAvailableCreature(NPC_JUHANI));')
lines.append('    sReport = sReport + "|mission=" + IntToString(IsAvailableCreature(NPC_MISSION));')
lines.append('    sReport = sReport + "|t3m4=" + IntToString(IsAvailableCreature(NPC_T3_M4));')
lines.append('    sReport = sReport + "|zaalbar=" + IntToString(IsAvailableCreature(NPC_ZAALBAR));')
lines.append("    // lev = the journal entry of lev_captured (99 once the Leviathan has been")
lines.append("    // escaped); the reconciler only purges after that.")
lines.append('    sReport = sReport + "|lev=" + IntToString(GetJournalEntry("lev_captured"));')
lines.append("    // sf = in a Star Forge module, fc = G_FinalChoice (1 dark, 2 light), bp = Bastila is in")
lines.append("    // the active party. Used by the reconciler's Star Forge pass.")
lines.append("    // sf also covers the Ebon Hawk while it is docked at the Star Forge: the galaxy map's")
lines.append("    // Star Forge entry (k_pebn_starf) sets K_CURRENT_PLANET to 50, and the reconcile then")
lines.append("    // fires before the player leaves the ship, landing at the transition into the Star Forge.")
lines.append('    int nSF = (GetStringLeft(sRosterMod, 7) == "sta_m45");')
lines.append('    if (GetStringLeft(sRosterMod, 4) == "ebo_" && GetGlobalNumber("K_CURRENT_PLANET") == 50) nSF = TRUE;')
lines.append('    sReport = sReport + "|sf=" + IntToString(nSF)')
lines.append('        + "|fc=" + IntToString(GetGlobalNumber("G_FinalChoice"))')
lines.append('        + "|bp=" + IntToString(IsNPCPartyMember(NPC_BASTILA))')
lines.append('        + "|md=" + IntToString(GetGlobalBoolean("STA_MALAK_DEAD"));')
lines.append("    // sel = whether each companion can be picked on the party screen (same order as the")
lines.append("    // availability fields above). Used to fix an entitled companion who is listed but unselectable.")
lines.append('    sReport = sReport + "|sel=" + IntToString(GetNPCSelectability(NPC_BASTILA) > 0)')
lines.append('        + IntToString(GetNPCSelectability(NPC_CANDEROUS) > 0)')
lines.append('        + IntToString(GetNPCSelectability(NPC_CARTH) > 0)')
lines.append('        + IntToString(GetNPCSelectability(NPC_HK_47) > 0)')
lines.append('        + IntToString(GetNPCSelectability(NPC_JOLEE) > 0)')
lines.append('        + IntToString(GetNPCSelectability(NPC_JUHANI) > 0)')
lines.append('        + IntToString(GetNPCSelectability(NPC_MISSION) > 0)')
lines.append('        + IntToString(GetNPCSelectability(NPC_T3_M4) > 0)')
lines.append('        + IntToString(GetNPCSelectability(NPC_ZAALBAR) > 0);')
lines.append("    // bz = which busy sources are set (see ApSceneBusyMask); km = K_KOTOR_MASTER, the story stage (40 or more: the Unknown World trip has begun).")
lines.append('    sReport = sReport + "|bz=" + IntToString(nMask) + "|km=" + IntToString(GetGlobalNumber("K_KOTOR_MASTER"));')
lines.append("    KSE_Diag(143, sReport);")
lines.append("}")
lines.append("")
lines.append("// Reports whether the PC currently possesses each tracked progression item")
lines.append("// progression items, so the reconciler can re-grant any that go missing")
lines.append("// (lost/sold/dropped) without waiting on a full inventory reconciliation --")
lines.append("// see PROGRESSION_ITEM_RESREFS's own comment (entitlement.py) for why these")
lines.append("// specifically need this and the general gear pool doesn't.")
lines.append("void CheckProgressionItems()")
lines.append("{")
lines.append("    object oPC = GetFirstPC();")
lines.append('    string sReport = "AP|PROGRESSIONITEMSREPORT";')
for key, resref in _PROGRESSION_ITEM_RESREFS:
    lines.append(f'    int b{key.title().replace("_", "")} = GetIsObjectValid(GetItemPossessedBy(oPC, "{resref}"));')
    lines.append(f'    sReport = sReport + "|{key}=" + IntToString(b{key.title().replace("_", "")});')
lines.append("    KSE_Diag(140, sReport);")
lines.append("}")

# Taris: Invited to a Party starts (tar_party 1) from Sarna's or Yun Genda's invitation. Taking the Sith armor some other way first
# leaves that quest unstartable, so its check could never fire. Reported only while the quest has not started and the armor is held;
# the client then completes the check (kotor_location_tracker.py, _SITH_ARMOR_RE).
lines.append("void CheckSithArmor()")
lines.append("{")
lines.append("    object oPC = GetFirstPC();")
lines.append('    if (GetJournalEntry("tar_party") < 1 && GetIsObjectValid(GetItemPossessedBy(oPC, "ptar_sitharmor")))')
lines.append("    {")
lines.append('        KSE_Diag(193, "AP|SITHARMOR|1");')
lines.append("    }")
lines.append("}")
lines.append("")

# Boss datapads (scripts/patch_boss_datapads.py): reports each datapad the player is carrying so
# the client can credit the matching "Boss: ..." check. Keys match Locations.py's datapad_key and
# the resrefs patch_boss_datapads.py writes. Emitted on every poll while held (the tracker ignores
# repeats), so a check lost to a reconnect is credited again on the next poll.
_BOSS_DATAPADS = [
    ("calo", "ap_dp_calo"),
    ("bandon", "ap_dp_bandon"),
    ("karath", "ap_dp_karath"),
]
lines.append("void CheckBossDatapads()")
lines.append("{")
lines.append("    object oPC = GetFirstPC();")
lines.append("    int nD = 0;")
lines.append('    if (KSE_HasData("d_n")) nD = StringToInt(KSE_GetData("d_n"));')
lines.append('    KSE_SetData("d_n", IntToString(nD + 1));')
lines.append("    int bFull = (nD % 12 == 0);")
lines.append('    string sNow = "";')
for key, resref in _BOSS_DATAPADS:
    lines.append(f'    sNow = sNow + IntToString(GetIsObjectValid(GetItemPossessedBy(oPC, "{resref}")));')
lines.append('    string sLast = "";')
lines.append('    if (KSE_HasData("d_vals")) sLast = KSE_GetData("d_vals");')
lines.append("    if (sNow == sLast && !bFull) return;")
lines.append('    KSE_SetData("d_vals", sNow);')
for i, (key, resref) in enumerate(_BOSS_DATAPADS):
    lines.append(f'    if (GetSubString(sNow, {i}, 1) == "1") KSE_Diag(178, "AP|DATAPAD|{key}");')
lines.append("}")
lines.append("")

# Quest items (Locations.py, location_type "quest_item"): reports each quest item the player holds, by tag, so the client can credit
# the matching "Quest Item: ..." check whatever the way the item was obtained. Keep the tags in step with Locations.py's quest_item_tags
# (worlds/kotor/test/test_generation.py checks this). Same on-change-plus-a-full-report-every-12-polls shape as the datapads.
_QUEST_ITEM_TAGS = [
    "ptar_sitharmor", "ptar_sithpapers", "ptar_shieldcodes", "rakghoulserum", "tat17_sandperdis", "tat20aa_westmap",
    "tat20_banthafod", "k33_itm_sithmdln", "k37_itm_freedont", "kor_itm_sithtabl", "kas25_swordblade", "man28_envirosuit", "w_ddata",
]
lines.append("void CheckQuestItems()")
lines.append("{")
lines.append("    object oPC = GetFirstPC();")
lines.append("    int nQ = 0;")
lines.append('    if (KSE_HasData("qi_n")) nQ = StringToInt(KSE_GetData("qi_n"));')
lines.append('    KSE_SetData("qi_n", IntToString(nQ + 1));')
lines.append("    int bFull = (nQ % 12 == 0);")
lines.append('    string sNow = "";')
for tag in _QUEST_ITEM_TAGS:
    lines.append(f'    sNow = sNow + IntToString(GetIsObjectValid(GetItemPossessedBy(oPC, "{tag}")));')
lines.append('    string sLast = "";')
lines.append('    if (KSE_HasData("qi_vals")) sLast = KSE_GetData("qi_vals");')
lines.append("    if (sNow == sLast && !bFull) return;")
lines.append('    KSE_SetData("qi_vals", sNow);')
for i, tag in enumerate(_QUEST_ITEM_TAGS):
    lines.append(f'    if (GetSubString(sNow, {i}, 1) == "1") KSE_Diag(202, "AP|QUESTITEM|{tag}");')
lines.append("}")
lines.append("")

# Archipelago Bazaar receipts: the Jawa gives one plot item per purchase (ap_bz_buy) and per token exchange (ap_bz_swap); the check
# numbers are their stack counts, so the client credits by count like the bounty cards. One line "AP|BAZAAR|<purchases>|<exchanges>",
# on change and about once a minute.
lines.append("void CheckBazaar()")
lines.append("{")
lines.append("    object oPC = GetFirstPC();")
lines.append("    int nB = 0;")
lines.append('    if (KSE_HasData("bz_n")) nB = StringToInt(KSE_GetData("bz_n"));')
lines.append('    KSE_SetData("bz_n", IntToString(nB + 1));')
lines.append("    int bFull = (nB % 12 == 0);")
lines.append("    int nBuy = 0;")
lines.append("    int nSwap = 0;")
lines.append('    object oBuy = GetItemPossessedBy(oPC, "ap_bz_buy");')
lines.append("    if (GetIsObjectValid(oBuy)) nBuy = GetItemStackSize(oBuy);")
lines.append('    object oSwap = GetItemPossessedBy(oPC, "ap_bz_swap");')
lines.append("    if (GetIsObjectValid(oSwap)) nSwap = GetItemStackSize(oSwap);")
lines.append('    string sNow = IntToString(nBuy) + "|" + IntToString(nSwap);')
lines.append('    string sLast = "";')
lines.append('    if (KSE_HasData("bz_vals")) sLast = KSE_GetData("bz_vals");')
lines.append("    if (sNow == sLast && !bFull) return;")
lines.append('    KSE_SetData("bz_vals", sNow);')
lines.append('    if (nBuy > 0 || nSwap > 0) KSE_Diag(203, "AP|BAZAAR|" + sNow);')
lines.append("}")
lines.append("")

# Korriban, Naga Sadow's tomb (korr_m39aa): taking the ceremonial saber closes and locks the star map door and the Uthar / Yuthura scene locks the
# exit; the game unlocks both again only on certain outcomes. A player who took the saber before the star map (the third Korriban item gates the
# star map) and killed both was left with the star map door and the exit locked, unable to return for the map. Once both are dead, unlock both.
lines.append("void CheckTombDoors()")
lines.append("{")
lines.append('    if (GetStringLowerCase(GetModuleFileName()) != "korr_m39aa") return;')
lines.append('    object oUthar = GetObjectByTag("kor39_utharwynn");')
lines.append('    object oYuthura = GetObjectByTag("kor39_yuthura");')
lines.append("    if (!GetIsObjectValid(oUthar) || !GetIsDead(oUthar)) return;")
lines.append("    if (!GetIsObjectValid(oYuthura) || !GetIsDead(oYuthura)) return;")
lines.append('    object oMap = GetObjectByTag("k39_door_starmap");')
lines.append('    object oExit = GetObjectByTag("kor39_kor36");')
lines.append("    if (GetIsObjectValid(oMap) && GetLocked(oMap))")
lines.append("    {")
lines.append("        SetLocked(oMap, FALSE);")
lines.append('        KSE_Diag(205, "AP|TOMB|unlocked|k39_door_starmap");')
lines.append("    }")
lines.append("    if (GetIsObjectValid(oExit) && GetLocked(oExit))")
lines.append("    {")
lines.append("        SetLocked(oExit, FALSE);")
lines.append('        KSE_Diag(205, "AP|TOMB|unlocked|kor39_kor36");')
lines.append("    }")
lines.append("}")
lines.append("")

# Visited-area markers (scripts/generate_location_items.py): every area's entry script gives the player the plot
# item ap_loc_<idx> the first time it is entered, and the item stays in the save. This reports the set the
# player holds as a comma list of area indexes, on change and about once a minute, so the client can credit
# every "Visited:" location even if it was not running when the area was entered. Looks each marker up by tag
# (a fixed 78 lookups, independent of inventory size) instead of walking the whole inventory.
_AREA_MARKER_COUNT = 78
lines.append("void CheckVisitedMarkers()")
lines.append("{")
lines.append("    object oPC = GetFirstPC();")
lines.append("    int nV = 0;")
lines.append('    if (KSE_HasData("av_n")) nV = StringToInt(KSE_GetData("av_n"));')
lines.append('    KSE_SetData("av_n", IntToString(nV + 1));')
lines.append("    int bFull = (nV % 12 == 0);")
lines.append('    string sNow = "";')
lines.append("    int i;")
lines.append(f"    for (i = 0; i < {_AREA_MARKER_COUNT}; i++)")
lines.append("    {")
lines.append("        string sIdx = IntToString(i);")
lines.append('        if (i < 10) sIdx = "0" + sIdx;')
lines.append('        sNow = sNow + IntToString(GetIsObjectValid(GetItemPossessedBy(oPC, "ap_loc_" + sIdx)));')
lines.append("    }")
lines.append('    string sLast = "";')
lines.append('    if (KSE_HasData("av_vals")) sLast = KSE_GetData("av_vals");')
lines.append("    if (sNow == sLast && !bFull) return;")
lines.append('    KSE_SetData("av_vals", sNow);')
lines.append('    string sList = "";')
lines.append(f"    for (i = 0; i < {_AREA_MARKER_COUNT}; i++)")
lines.append("    {")
lines.append('        if (GetSubString(sNow, i, 1) == "1") sList = sList + IntToString(i) + ",";')
lines.append("    }")
lines.append('    if (sList != "") KSE_Diag(179, "AP|AREASVISITED|" + sList);')
lines.append("}")
lines.append("")

# Taris Hideout snapshot (diagnostic only): the escape pod lands the player in tar_m02af, where a placed Carth stand-in
# and the vanilla trigger tar02_carstr start his reunion conversation. Inside that module only, prints what is actually
# there whenever it changes -- whether the Carth and Carth02 objects and the trigger exist, whether Carth is available
# or in the party, whether a conversation is running, the party size and the planet global -- so a missing Carth or a
# conversation that never starts shows which of those was wrong. Change-gated, so a few lines per visit.
lines.append("void CheckHideoutCarth()")
lines.append("{")
lines.append('    if (GetModuleFileName() != "tar_m02af") return;')
lines.append("    object oPC = GetFirstPC();")
lines.append('    string sNow = "carth=" + IntToString(GetIsObjectValid(GetObjectByTag("Carth")))')
lines.append('        + "|carth02=" + IntToString(GetIsObjectValid(GetObjectByTag("Carth02")))')
lines.append('        + "|trigger=" + IntToString(GetIsObjectValid(GetObjectByTag("tar02_carstr")))')
lines.append('        + "|avail=" + IntToString(IsAvailableCreature(NPC_CARTH))')
lines.append('        + "|inparty=" + IntToString(IsNPCPartyMember(NPC_CARTH))')
lines.append('        + "|conv=" + IntToString(GetIsInConversation(oPC))')
lines.append('        + "|party=" + IntToString(GetPartyMemberCount())')
lines.append('        + "|planet=" + IntToString(GetGlobalNumber("K_CURRENT_PLANET"));')
lines.append('    string sLast = "";')
lines.append('    if (KSE_HasData("hd_state")) sLast = KSE_GetData("hd_state");')
lines.append("    if (sNow == sLast) return;")
lines.append('    KSE_SetData("hd_state", sNow);')
lines.append('    KSE_Diag(183, "AP|HIDEOUT|" + sNow);')
lines.append("}")
lines.append("")

# Player ID (scripts/patch_player_id.py): the plot item `ap_pid` a new level-1 character receives at the Endar Spire
# entry. Its name ("Player ID: <slot> <hash>") records which seed and slot the character was started for; "NONE"
# means the character has no such item. Printed on change and about once a minute (not every poll), so the log
# gains one short line a minute. The client records it next to each delivery and warns on a mismatch; nothing
# is enforced.
lines.append("void CheckPlayerId()")
lines.append("{")
lines.append("    object oPC = GetFirstPC();")
lines.append("    int nP = 0;")
lines.append('    if (KSE_HasData("pid_n")) nP = StringToInt(KSE_GetData("pid_n"));')
lines.append('    KSE_SetData("pid_n", IntToString(nP + 1));')
lines.append("    int bFull = (nP % 12 == 0);")
lines.append('    string sNow = "NONE";')
lines.append('    object oId = GetItemPossessedBy(oPC, "ap_pid");')
lines.append("    if (GetIsObjectValid(oId)) sNow = GetName(oId);")
lines.append('    string sLast = "";')
lines.append('    if (KSE_HasData("pid_last")) sLast = KSE_GetData("pid_last");')
lines.append("    if (sNow == sLast && !bFull) return;")
lines.append('    KSE_SetData("pid_last", sNow);')
lines.append('    KSE_Diag(180, "AP|PLAYERID|" + sNow);')
lines.append("}")
lines.append("")

# "Archipelago Tracker" journal quest (build_ap_tracker_quest.py) -- reports
# the player's CURRENT stage every poll, so kotor_reconciliation.py's
# check-percentage branch knows whether it still needs to send the next
# journal_tracker_<N> arm (generate_trampoline_batch.py) without relying
# purely on client-side in-flight tracking. 0 legitimately means "not
# added yet" -- see nwscript.nss's own GetJournalEntry doc and
# build_ap_tracker_quest.py's STAGES comment for why stage 0 was dropped
# from the real stage list (1/20/40/60/80/100 instead).
lines.append('void CheckAPTrackerStage()')
lines.append("{")
lines.append('    KSE_Diag(167, "AP|APTRACKERREPORT|stage=" + IntToString(GetJournalEntry("ap_tracker")));')
lines.append("}")
lines.append("")

# Traps (see Options.py's Traps): the Remove Half Known
# Feats / Remove Half Known Force Powers traps need to know WHICH ids the
# character currently has before picking half at random -- there's no
# "list every feat/power a creature knows" native, only per-id membership
# (KSE_GetFeatAcquired / GetHasSpell), so this reports only the HELD ids
# (comma-joined), not a full bitmap over every candidate id -- keeps the
# report compact regardless of how large the candidate list grows.
# force_powers_and_feats.json is this project's own confirmed real-id
# reference data (feat.2da/spells.2da rows, read via pykotor) -- feats
# uses every row present (122, all real -- confirmed via pykotor, not a
# placeholder subset), force_powers is filtered to rows with a real
# in-game name (44 of 51 -- the other 7 are unused/master placeholder
# rows like "FORCE_POWER_MASTER_ALTER_XXX").
with open(os.path.join(REPO_ROOT, "force_powers_and_feats.json"), encoding="utf-8") as f:
    _fp_feats = json.load(f)
_ALL_FEAT_IDS = sorted(int(k) for k in _fp_feats["feats"].keys())
_ALL_FORCE_POWER_IDS = sorted(int(k) for k, v in _fp_feats["force_powers"].items() if v.get("name"))

lines.append("// Traps feature -- reports every feat.2da id the character")
lines.append("// currently holds (KSE_GetFeatAcquired is per-id membership only, there's")
lines.append("// no 'list all feats' native), so the client can pick half at random for")
lines.append("// the Remove Half Known Feats trap without guessing at what's held.")
lines.append("//")
lines.append("// Every poll this checks ONLY a short list of feats (the ones feat training offers plus the Jedi class feats)")
lines.append("// -- each KSE_GetFeatAcquired call writes a native log line, and scanning all of them every")
lines.append("// 5 s was most of kse.log. The full list the Remove Half Known Feats trap needs is reported by")
lines.append("// CheckFeatsFull() below, about once a minute.")
lines.append("void CheckFeats()")
lines.append("{")
lines.append("    object oPC = GetFirstPC();")
lines.append('    string sHeld = "";')
for feat_id in _PC_FEAT_SCAN_IDS:
    lines.append(f"    if (KSE_GetFeatAcquired({feat_id}, oPC)) sHeld += \"{feat_id},\";")
lines.append('    KSE_Diag(135, "AP|FEATREPORT|" + sHeld);')
lines.append("}")
lines.append("")
lines.append("// The full held-feat list, on the first poll after launch and then every 12th poll (~1 min).")
lines.append("void CheckFeatsFull()")
lines.append("{")
lines.append("    int nFull = 0;")
lines.append('    if (KSE_HasData("ff_n")) nFull = StringToInt(KSE_GetData("ff_n"));')
lines.append('    KSE_SetData("ff_n", IntToString(nFull + 1));')
lines.append("    if (nFull % 12 != 0) return;")
lines.append("    object oPC = GetFirstPC();")
lines.append('    string sHeld = "";')
for feat_id in _ALL_FEAT_IDS:
    lines.append(f"    if (KSE_GetFeatAcquired({feat_id}, oPC)) sHeld += \"{feat_id},\";")
lines.append('    KSE_Diag(135, "AP|FEATFULL|" + sHeld);')
lines.append("}")
lines.append("")
lines.append("// Same shape as CheckFeats() above, for spells.2da (force powers) --")
lines.append("// GetHasSpell is likewise per-id membership only.")
lines.append("//")
lines.append("// GUARD: same reasoning as CheckForce()'s guard below --")
lines.append("// GetHasSpell() running fine on a PERMANENTLY non-Jedi character (a")
lines.append("// null/empty known-powers array is a well-defined state) does not prove")
lines.append("// it's safe on a character that was JUST raw-multiclassed via")
lines.append("// AddMultiClass() and never went through a real level-up -- that's a")
lines.append("// different internal state, and this native has never been proven safe")
lines.append("// against it specifically.")
lines.append("void CheckForcePowers()")
lines.append("{")
lines.append("    object oPC = GetFirstPC();")
lines.append("    int nJediTotal = GetLevelByClass(CLASS_TYPE_JEDIGUARDIAN, oPC)")
lines.append("        + GetLevelByClass(CLASS_TYPE_JEDICONSULAR, oPC)")
lines.append("        + GetLevelByClass(CLASS_TYPE_JEDISENTINEL, oPC);")
lines.append("    if (nJediTotal == 1) return;")
lines.append('    string sHeld = "";')
for power_id in _ALL_FORCE_POWER_IDS:
    lines.append(f"    if (GetHasSpell({power_id}, oPC)) sHeld += \"{power_id},\";")
lines.append('    KSE_Diag(136, "AP|POWERREPORT|" + sHeld);')
lines.append("}")
lines.append("")
lines.append("// Character name, reported every poll -- the client keys its persistent")
lines.append("// delivery log on (character name, item index) so a fresh character (a")
lines.append("// deliberate restart) gets everything re-granted, while reconnecting to the")
lines.append("// SAME character doesn't replay history it's already received. See")
lines.append("// KotorClient.py's delivery log for the other half of this.")
lines.append("void CheckCharacterName()")
lines.append("{")
lines.append("    object oPC = GetFirstPC();")
lines.append('    KSE_Diag(66, "AP|NAMEREPORT|" + GetName(oPC));')
lines.append("}")
lines.append("")
lines.append("// Same stateless design as everything above. Skills are already grantable")
lines.append("// via KSE_AdjustCreatureSkills (proven working in an earlier phase) -- this")
lines.append("// is just the reporting half, so the client can be authoritative on what")
lines.append("// skill ranks the player should have (same as XP/credits/inventory) rather")
lines.append("// than the game deciding anything for itself.")
lines.append("//")
lines.append("// GetSkillRank is NOT the rank -- it adds the ability modifier and any")
lines.append("// effects, so it moves with abilities, gear and combat debuffs. The native")
lines.append("// selector below logs the eight TRUE ranks as AP|SKILLBASEREPORT; it runs")
lines.append("// BEFORE the SKILLREPORT line because SKILLREPORT is the cycle-complete")
lines.append("// marker that triggers reconciliation, which needs the true ranks in hand.")
lines.append("void CheckSkills()")
lines.append("{")
lines.append("    object oPC = GetFirstPC();")
lines.append("    KSE_SetCreatureField(oPC, KSE_FIELD_REPORT_SKILL_RANKS(), 0);")
lines.append('    string sReport = "AP|SKILLREPORT|computeruse=" + IntToString(GetSkillRank(SKILL_COMPUTER_USE, oPC))')
lines.append('        + "|demolitions=" + IntToString(GetSkillRank(SKILL_DEMOLITIONS, oPC))')
lines.append('        + "|stealth=" + IntToString(GetSkillRank(SKILL_STEALTH, oPC))')
lines.append('        + "|awareness=" + IntToString(GetSkillRank(SKILL_AWARENESS, oPC))')
lines.append('        + "|persuade=" + IntToString(GetSkillRank(SKILL_PERSUADE, oPC))')
lines.append('        + "|repair=" + IntToString(GetSkillRank(SKILL_REPAIR, oPC))')
lines.append('        + "|security=" + IntToString(GetSkillRank(SKILL_SECURITY, oPC))')
lines.append('        + "|treatinjury=" + IntToString(GetSkillRank(SKILL_TREAT_INJURY, oPC));')
lines.append("    KSE_Diag(28, sReport);")
lines.append("}")
lines.append("")
lines.append("// No CheckInventory() here: it used to build ONE giant string")
lines.append("// via repeated concatenation across the whole backpack + equipped slots")
lines.append("// (sReport = sReport + GetTag(oItem) + ...), reported as AP|INVENTORY|...")
lines.append("// every poll. NWScript's own string type")
lines.append("// has a hard ~512-byte engine limit, and a real 28+-item backpack")
lines.append("// truncates mid-word well before the scan finishes. This silently lost")
lines.append("// data for ANY tag near the end of a large enough backpack (see")
lines.append("// CheckBountyCount() below for its targeted")
lines.append("// single-tag replacement, which can't hit this limit since it only ever")
lines.append("// emits a bounded integer, never a per-item concatenation). The only other")
lines.append("// consumer, kotor_reconciliation.py's current_inventory (Remove Half")
lines.append("// Inventory trap), no longer needs a live poll at all -- that trap now")
lines.append("// does its own on-demand inventory walk + native random selection")
lines.append("// entirely in NWScript at delivery time (see generate_trampoline_batch.py's")
lines.append("// build_trap_block, remove_half_inventory branch), so dropping this")
lines.append("// function removes a full inventory walk + string build from every single")
lines.append("// 5-second heartbeat tick with no functional loss.")
lines.append("")
lines.append("// DeathLink outgoing half. Same stateless design as everything else here --")
lines.append("// just honestly reports whether the PC is currently dead every poll, no")
lines.append("// in-game persistence or edge-detection. The client is authoritative on")
lines.append("// dedup (only bounce one DeathLink per death, reset once alive again) since")
lines.append("// custom globals don't persist across saves/reloads and this event will")
lines.append("// otherwise repeat every single poll for as long as the player stays dead.")
lines.append("void CheckDeath()")
lines.append("{")
lines.append("    object oPC = GetFirstPC();")
lines.append("    if (GetIsDead(oPC))")
lines.append("    {")
lines.append('        KSE_Diag(64, "AP|CHECK|DEATH");')
lines.append("    }")
lines.append("}")
lines.append("")
wants_additional_enemies = bool(cli_args.additional_enemies) if cli_args.additional_enemies is not None else _connected_wants_additional_enemies()
wants_droid_look = _connected_wants_droid_look()
if wants_additional_enemies:
    lines.append("// Bounty Card count -- replaces the old AP|INVENTORY-based")
    lines.append("// _bounty_card_count parsing, which relied on CheckInventory()'s giant")
    lines.append("// concatenated string (see the comment above for the 512-byte")
    lines.append("// truncation this hit). This scans for exactly ONE tag and emits a")
    lines.append("// single bounded integer, never a per-item string build, so it can't hit")
    lines.append("// that limit no matter how large the backpack is. Only generated when")
    lines.append("// additional_enemies_mode != 0 for this seed -- bounty carriers don't")
    lines.append("// exist at all otherwise, so the scan would be pure waste.")
    lines.append("void CheckBountyCount()")
    lines.append("{")
    lines.append("    object oPC = GetFirstPC();")
    lines.append("    int nCount = 0;")
    lines.append("    object oItem = GetFirstItemInInventory(oPC);")
    lines.append("    while (GetIsObjectValid(oItem))")
    lines.append("    {")
    lines.append('        if (GetTag(oItem) == "ap_bounty_card") nCount = nCount + GetItemStackSize(oItem);')
    lines.append("        oItem = GetNextItemInInventory(oPC);")
    lines.append("    }")
    lines.append("")
    lines.append("    // Only report on an actual change -- same only-when-it-moves shape as")
    lines.append("    // the rest of this file's stateful checks, avoids re-sending an")
    lines.append("    // unchanged count every 5s for as long as the player holds any cards.")
    lines.append("    int nLast = -1;")
    lines.append('    if (KSE_HasData("bounty_last_count")) nLast = StringToInt(KSE_GetData("bounty_last_count"));')
    lines.append("    if (nCount != nLast)")
    lines.append("    {")
    lines.append('        KSE_SetData("bounty_last_count", IntToString(nCount));')
    lines.append('        KSE_Diag(157, "AP|BOUNTY|COUNT|" + IntToString(nCount));')
    lines.append("    }")
    lines.append("}")
    lines.append("")
lines.append("// Light/dark alignment, reported every poll -- same stateless design as")
lines.append("// everything else here. GetGoodEvilValue is 0 (full dark) to 100 (full")
lines.append("// light), 50 neutral. The client tracks the last-known value itself and")
lines.append("// derives newly-crossed thresholds (and the Fallen")
lines.append("// Jedi/Redeemed Sith bonus checks, which need a bit of history) -- see")
lines.append("// kotor_location_tracker.py.")
lines.append("void CheckAlignment()")
lines.append("{")
lines.append("    object oPC = GetFirstPC();")
lines.append('    KSE_Diag(83, "AP|ALIGNMENT|" + IntToString(GetGoodEvilValue(oPC)));')
lines.append("}")
lines.append("")
lines.append("// Goal detection: STA_MALAK_DEAD is a real, pre-declared globalcat.2da")
lines.append("// Boolean, set unconditionally true in sta_m45ad across every narrative")
lines.append("// branch of Malak's death (k_psta_mlkend/k_psta_ud_malak and its _mal2-8")
lines.append("// variants) and never reset -- same proven detection shape as the _DONE")
lines.append("// quest flags above, just not sharing their naming convention so it isn't")
lines.append("// swept up by the generic *_DONE scan. Reported unconditionally once true,")
lines.append("// same stateless design as everything else here -- the client decides what")
lines.append("// to do with it (only the defeat_malak Goal option cares).")
lines.append("void CheckGoal()")
lines.append("{")
lines.append('    if (GetGlobalBoolean("STA_MALAK_DEAD"))')
lines.append("    {")
lines.append('        KSE_Diag(84, "AP|CHECK|GOAL|MALAK_DEAD");')
lines.append("    }")
lines.append("}")
lines.append("")
lines.append("// Character level, for the max_level Goal option. GetHitDice returns total")
lines.append("// character level regardless of class/multiclass split -- exactly the same")
lines.append("// number exptable.2da's cumulative XP thresholds are keyed on.")
lines.append("void CheckLevel()")
lines.append("{")
lines.append("    object oPC = GetFirstPC();")
lines.append('    KSE_Diag(85, "AP|LEVELREPORT|" + IntToString(GetHitDice(oPC)));')
lines.append("}")
lines.append("")
lines.append("// Feeds the delevel reconciler's Force-point scaling (see")
lines.append("// kotor_reconciliation.py's _FORCE_RE/current_force) -- GetCurrentForcePoints()/")
lines.append("// GetMaxForcePoints() and GetLevelByClass() above are real standard")
lines.append("// natives, no new offset/native needed just to READ these.")
lines.append("//")
lines.append("// GUARD: GetCurrentForcePoints()/")
lines.append("// GetMaxForcePoints() crash the game when called on the PC immediately")
lines.append("// after a raw AddMultiClass()+CLASS1_LEVEL=1 grant (class_consular),")
lines.append("// before any real UI level-up has happened -- the crash fires")
lines.append("// on this poll's own automatic next tick, not any player action (no")
lines.append("// character sheet/inventory/Force Powers screen needs to be opened, and the class")
lines.append("// change need never even be visually seen before the crash). Matches this")
lines.append("// project's own earlier companion-class-switch finding that a freshly")
lines.append("// multiclassed slot's underlying Force-power data isn't allocated until a")
lines.append("// real level-up runs -- these two natives apparently need to walk that")
lines.append("// same not-yet-allocated structure, unlike a raw KSE_FIELD_FORCE offset")
lines.append("// read/write, which doesn't. Skip while any Jedi slot is fresh (total")
lines.append("// Jedi levels == 1) -- exactly the dangerous state, and not useful data")
lines.append("// anyway since every real formula data point so far came from levels well")
lines.append("// past this point.")
lines.append("void CheckForce()")
lines.append("{")
lines.append("    object oPC = GetFirstPC();")
lines.append("    int nJediTotal = GetLevelByClass(CLASS_TYPE_JEDIGUARDIAN, oPC)")
lines.append("        + GetLevelByClass(CLASS_TYPE_JEDICONSULAR, oPC)")
lines.append("        + GetLevelByClass(CLASS_TYPE_JEDISENTINEL, oPC);")
lines.append("    if (nJediTotal == 1) return;")
lines.append('    KSE_Diag(137, "AP|FORCEREPORT|current=" + IntToString(GetCurrentForcePoints(oPC))')
lines.append('        + "|max=" + IntToString(GetMaxForcePoints(oPC)));')
lines.append("}")
lines.append("")
wants_area_randomizer = bool(cli_args.area_randomizer) if cli_args.area_randomizer is not None else _connected_wants_area_randomizer()
if wants_area_randomizer:
    lines.append("// Forces every real, non-scripted-cutscene planet available/selectable")
    lines.append("// on the Galaxy Map from the very start -- ONLY generated when the latest")
    lines.append("// seed has area_randomizer=True. With doors shuffled,")
    lines.append("// walking through a completely normal door can land a player on a planet")
    lines.append("// whose real story-progression trigger (the thing that would normally call")
    lines.append("// SetPlanetAvailable()) never fired, since they arrived out of the intended")
    lines.append("// order -- the Ebon Hawk's ramp-exit gate then checks GetSelectedPlanet(),")
    lines.append("// which never got set, and refuses to let the player leave at all. Doors")
    lines.append("// are already fully shuffled once this option is on, so story-order gating")
    lines.append("// of planet availability serves no purpose any more anyway -- it can only")
    lines.append("// strand the player. Leviathan/Unknown World/Star Forge/Endar Spire are")
    lines.append("// deliberately excluded, matching EntranceRando.py's own")
    lines.append("// EXCLUDED_BOTH_WAYS_PREFIXES: those are entered via a forced scripted")
    lines.append("// cutscene, never a real door/trigger, so making them freely selectable")
    lines.append("// would let a player sequence-break directly into end-game content instead")
    lines.append("// of fixing a stuck-ship problem. One-shot per session, same KSE_HasData")
    lines.append("// guard pattern as hb_tick_time above.")
    lines.append("void CheckPlanetAvailability()")
    lines.append("{")
    lines.append('    if (KSE_HasData("planets_unlocked")) return;')
    lines.append('    KSE_SetData("planets_unlocked", "1");')
    for planet_const in (
        "PLANET_TARIS", "PLANET_DANTOOINE", "PLANET_TATOOINE",
        "PLANET_KASHYYYK", "PLANET_MANAAN", "PLANET_KORRIBAN",
    ):
        lines.append(f"    SetPlanetAvailable({planet_const}, TRUE);")
        lines.append(f"    SetPlanetSelectable({planet_const}, TRUE);")
    lines.append("}")
    lines.append("")

# Bonus loot mode's grant logic used to live here, as a
# CheckPickupCount() re-scanning ALL 672 suppress-eligible tags against
# current holdings on EVERY 5s heartbeat tick forever (an interim fix for
# an earlier, even more expensive per-HELD-ITEM version). Both versions
# did real, unnecessary recurring work
# regardless of whether anything changed. Moved entirely into
# patch_item_suppression.py's HandleAcquiredItem() instead -- it already
# runs the same 672-way whitelist check exactly once per actual
# Mod_OnAcquirItem event (cheap; pickups are inherently rare compared to
# a 5s timer), and already knows exactly which one tag just fired, so
# there's no reason to also scan the other 671 nobody touched. See that
# file's build_handler_body() docstring for the full history. No
# generation needed here any more -- loot_mode is read there directly at
# patch time, not derived from the latest seed's zip like this file does.

lines.append("// Restarts the heartbeat when it is dead (see the comment below). Called FIRST in")
lines.append("// main(), and again at the end: it used to run only at the end, so a poll that")
lines.append("// stopped partway on an area entry (seen in play: polling and the")
lines.append("// heartbeat stayed dead for almost three minutes until the area was reloaded)")
lines.append("// never got to restart it.")
lines.append("void EnsureHeartbeat()")
lines.append("{")
lines.append("    // Self-healing heartbeat restart, staleness-based (not a one-shot flag).")
lines.append("    // Confirmed this session: a same-process in-game Load Game silently kills")
lines.append("    // the heartbeat's DelayCommand chain while leaving KSE's in-session data")
lines.append("    // store untouched (that store is DLL-memory, tied to the process, not the")
lines.append("    // save) -- so a one-shot \"hb_started\" flag that's only ever SET, never")
lines.append("    // cleared, can never detect that case: it stays true forever after the")
lines.append("    // first start, even once the actual heartbeat is dead. Fixed by having")
lines.append("    // Tick() stamp the current time into KSE data on every tick, and treating")
lines.append("    // the heartbeat as dead if that stamp is missing OR older than 20s (4x")
lines.append("    // the 5s tick interval, generous slack for scheduling jitter). This also")
lines.append("    // replaces hb_started entirely -- covers first-ever start (no stamp yet),")
lines.append("    // full process restart (KSE store wiped, no stamp), and a same-process")
lines.append("    // Load Game (stamp present but stale) with the same single check.")
lines.append("    int nNow = GetTimeHour() * 3600 + GetTimeMinute() * 60 + GetTimeSecond();")
lines.append("    int nHeartbeatDead = 1;")
lines.append('    if (KSE_HasData("hb_tick_time"))')
lines.append("    {")
lines.append('        int nLastTick = StringToInt(KSE_GetData("hb_tick_time"));')
lines.append("        int nDelta = nNow - nLastTick;")
lines.append("        if (nDelta < 0) nDelta = nDelta + 86400; // midnight wraparound")
lines.append("        if (nDelta < 20) nHeartbeatDead = 0;")
lines.append("    }")
lines.append("    if (nHeartbeatDead)")
lines.append("    {")
lines.append("        // Stamp immediately, before the new heartbeat's own first tick runs --")
lines.append("        // otherwise a second poll_shared call arriving moments later (e.g. a")
lines.append("        // module-load and an area-enter firing back to back) would still see")
lines.append("        // a stale/missing stamp and spawn a SECOND heartbeat, double-ticking")
lines.append("        // everything from then on.")
lines.append('        KSE_SetData("hb_tick_time", IntToString(nNow));')
lines.append('        ExecuteScript("ap_heartbeat", OBJECT_SELF);')
lines.append("    }")
lines.append("}")
lines.append("")
if wants_droid_look:
    lines.append("// starting_class=droid: the PC's HK-47 variant look is a permanent EffectDisguise (the pc_droid arm applies it).")
    lines.append("// Vanilla scripts that end a disguise remove EVERY disguise effect on the party -- the Manaan underwater")
    lines.append("// level's RemoveSuits(), the Tatooine sand-person and Leviathan disguises -- which would silently drop that")
    lines.append("// look. This puts it back whenever the PC is a Battle Droid (race 5, class 9) with no disguise at all;")
    lines.append("// while a vanilla disguise is active it does nothing, so it never fights the suit or the sand-person robe.")
    lines.append("void CheckDroidLook()")
    lines.append("{")
    lines.append("    object oPC = GetFirstPC();")
    lines.append("    if (GetRacialType(oPC) != 5 || GetClassByPosition(1, oPC) != 9) return;")
    lines.append("    effect eFx = GetFirstEffect(oPC);")
    lines.append("    while (GetIsEffectValid(eFx))")
    lines.append("    {")
    lines.append("        if (GetEffectType(eFx) == EFFECT_TYPE_DISGUISE) return;")
    lines.append("        eFx = GetNextEffect(oPC);")
    lines.append("    }")
    lines.append("    ApplyEffectToObject(DURATION_TYPE_PERMANENT, EffectDisguise(1), oPC);")
    lines.append('    KSE_Diag(188, "AP|DROIDLOOK|restored");')
    lines.append("}")
    lines.append("")
if cli_args.dispatch_test:
    DT_FUNCTIONS = r'''
// ---- the job dispatcher (generate_poll_shared.py; every delivery goes through it) -----------------------------------
// A job from the client arrives in the in-DLL inbox, KSE data "dt_job" = "<seq>:<action>:<args>[^^<message>]" (the extender writes it for the
// client's DISPATCH: command). seq is a number 0-255 kept in the PC's local booleans 48-55, which are saved with the game, so a
// reloaded save brings back the number that matches its own state. A job fires only when the saved number is seq - 1; the number is
// advanced and the inbox cleared BEFORE the action runs, so a job can be lost but never run twice. A job already applied
// (saved number = seq) is dropped as a duplicate; any other number is reported so the client can resync. A job also waits for a
// calm moment (see DtGateBits). The optional message after ^^ is shown to the player in the same apply, once the action has run.
// Every decision is logged as AP|DISPATCH|... (KSE_Diag 199).
void DtMarkReady()
{
    KSE_SetData("dt_ready", "1");
}

void DtLog(string sMsg)
{
    KSE_Diag(199, "AP|DISPATCH|" + sMsg + "|mod=" + GetModuleFileName());
}

int DtGetSeq(object oPC)
{
    int nSeq = 0;
    int nMul = 1;
    int i = 0;
    while (i < 8)
    {
        if (GetLocalBoolean(oPC, 48 + i) != 0) nSeq = nSeq + nMul;
        nMul = nMul * 2;
        i = i + 1;
    }
    return nSeq;
}

void DtSetSeq(object oPC, int nSeq)
{
    int nRest = nSeq;
    int i = 0;
    while (i < 8)
    {
        SetLocalBoolean(oPC, 48 + i, nRest % 2);
        nRest = nRest / 2;
        i = i + 1;
    }
}

// Which scene-like states are on right now, as bits: 1 scripted scene flag (ApSceneBusyMask), 2 conversation, 4 STUNT cutscene module,
// 8 PC not commandable, 16 combat, 128 player restrict mode, 256 PC dead. Logged on every change as PROBE, whether or not a
// job is waiting, so a real cutscene shows which of them it actually sets.
int DtProbeMask(object oPC)
{
    int nBits = 0;
    if (ApSceneBusyMask() != 0) nBits = nBits + 1;
    if (GetIsInConversation(oPC)) nBits = nBits + 2;
    if (GetStringLeft(GetStringLowerCase(GetModuleFileName()), 5) == "stunt") nBits = nBits + 4;
    if (!GetCommandable(oPC)) nBits = nBits + 8;
    if (GetIsInCombat(oPC)) nBits = nBits + 16;
    if (GetPlayerRestrictMode(oPC)) nBits = nBits + 128;
    if (GetIsDead(oPC)) nBits = nBits + 256;
    return nBits;
}

// A job fires only when this is 0: the probe bits plus 32 settling after an area change (3 s) and 64 no party.
int DtGateBits(object oPC)
{
    int nBits = DtProbeMask(oPC);
    if (GetPartyMemberCount() < 1) nBits = nBits + 64;
    return nBits;
}

// On-screen text does not work in this game (docs/MODE_DEPENDENCIES.md); the one-line dialog ap_gate_msg does.
void DtShowMessage(object oPC, string sMsg)
{
    // "~~" in the text is a line break (the client joins the messages of a batch of jobs with it)
    int nBr = FindSubString(sMsg, "~~");
    while (nBr >= 0)
    {
        sMsg = GetSubString(sMsg, 0, nBr) + "\n" + GetSubString(sMsg, nBr + 2, GetStringLength(sMsg));
        nBr = FindSubString(sMsg, "~~");
    }
    SetCustomToken(901, sMsg);
    AssignCommand(oPC, ActionStartConversation(oPC, "ap_gate_msg", FALSE, CONVERSATION_TYPE_CINEMATIC, TRUE));
}

// give_item:<resref>:<count> -- the same grant as the area-entry give_item block (items created one at a time, marked so the loot
// handler does not destroy them), without that block's starpad progress marker.
int DtGiveItem(object oPC, string sArgs)
{
    string sRes = sArgs;
    int nCount = 1;
    int nC = FindSubString(sArgs, ":");
    if (nC >= 0)
    {
        sRes = GetSubString(sArgs, 0, nC);
        nCount = StringToInt(GetSubString(sArgs, nC + 1, GetStringLength(sArgs)));
    }
    if (nCount < 1) nCount = 1;
    if (nCount > 50) nCount = 50;
    KSE_SetData("granted_exempt_" + GetStringLowerCase(sRes), "1");
    int nMade = 0;
    int i = 0;
    while (i < nCount)
    {
        object oItem = CreateItemOnObject(sRes, oPC, 1);
        if (GetIsObjectValid(oItem)) nMade = nMade + 1;
        i = i + 1;
    }
    DtLog("GIVE|resref=" + sRes + "|asked=" + IntToString(nCount) + "|created=" + IntToString(nMade) + "|held=" + IntToString(GetItemStackSize(GetItemPossessedBy(oPC, sRes))));
    if (nMade < 1) return 2;
    return 1;
}

// The actions. Returns 0 for one it does not know, 1 when done, 2 when it ran but could not do its job (for example an item
// that does not exist). "notify" does nothing itself: its text is the message.
// "arm:<name>" runs one of the fixed arms (DtArm, generated from generate_trampoline_batch.py's APPLIES table).
int DtRun(object oPC, string sAction, string sArgs)
{
    if (sAction == "notify") return 1;
    if (sAction == "arm") return DtArm(sArgs);
    if (sAction == "give_item") return DtGiveItem(oPC, sArgs);
    if (sAction == "set_xp") return DtSetXp(sArgs);
    if (sAction == "delevel") return DtDelevel(sArgs);
    if (sAction == "force_power") return DtForcePower(sArgs);
    if (sAction == "companion_class") return DtCompanionClass(sArgs);
    if (sAction == "trap") return DtTrap(sArgs);
    if (sAction == "set_credits")
    {
        KSE_SetCredits(oPC, StringToInt(sArgs));
        if (GetGold(oPC) != StringToInt(sArgs)) return 2;
        return 1;
    }
    return 0;
}

void DtTick()
{
    object oPC = GetFirstPC();
    if (!GetIsObjectValid(oPC)) return;
    int nPoll = 0;
    if (KSE_HasData("dt_poll")) nPoll = StringToInt(KSE_GetData("dt_poll"));
    nPoll = nPoll + 1;
    KSE_SetData("dt_poll", IntToString(nPoll));
    int nSeq = DtGetSeq(oPC);

    // an area change restarts the settling period; the companions are not materialized yet at the instant of entry
    int bState = FALSE;
    string sMod = GetModuleFileName();
    string sLastMod = "";
    if (KSE_HasData("dt_mod")) sLastMod = KSE_GetData("dt_mod");
    if (sMod != sLastMod)
    {
        KSE_SetData("dt_mod", sMod);
        KSE_SetData("dt_ready", "0");
        DelayCommand(3.0, DtMarkReady());
        DtLog("area_change|from=" + sLastMod);
        bState = TRUE;
    }
    // the saved number as the client needs it: on every change (a reloaded save), at an area change, and every 12th poll
    string sLastSeq = "";
    if (KSE_HasData("dt_lastseq")) sLastSeq = KSE_GetData("dt_lastseq");
    if (sLastSeq != IntToString(nSeq)) bState = TRUE;
    if (nPoll % 12 == 0) bState = TRUE;
    if (bState)
    {
        KSE_SetData("dt_lastseq", IntToString(nSeq));
        DtLog("STATE|seq=" + IntToString(nSeq));
    }

    int nProbe = DtProbeMask(oPC);
    int nProbeLast = -1;
    if (KSE_HasData("dt_probe")) nProbeLast = StringToInt(KSE_GetData("dt_probe"));
    if (nProbe != nProbeLast)
    {
        KSE_SetData("dt_probe", IntToString(nProbe));
        DtLog("PROBE|mask=" + IntToString(nProbe) + "|prev=" + IntToString(nProbeLast));
    }

    string sJob = "";
    if (KSE_HasData("dt_job")) sJob = KSE_GetData("dt_job");
    if (sJob == "") return;
    int nC1 = FindSubString(sJob, ":");
    if (nC1 < 1)
    {
        KSE_SetData("dt_job", "");
        DtLog("BAD|raw=" + sJob);
        return;
    }
    int nJobSeq = StringToInt(GetSubString(sJob, 0, nC1));
    string sRest = GetSubString(sJob, nC1 + 1, GetStringLength(sJob));
    string sMsg = "";
    int nMsg = FindSubString(sRest, "^^");
    if (nMsg >= 0)
    {
        sMsg = GetSubString(sRest, nMsg + 2, GetStringLength(sRest));
        sRest = GetSubString(sRest, 0, nMsg);
    }
    string sAction = sRest;
    string sArgs = "";
    int nC2 = FindSubString(sRest, ":");
    if (nC2 >= 0)
    {
        sAction = GetSubString(sRest, 0, nC2);
        sArgs = GetSubString(sRest, nC2 + 1, GetStringLength(sRest));
    }
    if (sAction == "notify") sMsg = sArgs;

    // nothing is judged during the settling period after an area change: the saved number is read once the game has finished loading
    int nWaited = 0;
    if (KSE_HasData("dt_waitseq") && KSE_GetData("dt_waitseq") == IntToString(nJobSeq)) nWaited = StringToInt(KSE_GetData("dt_waited"));
    else
    {
        KSE_SetData("dt_waitseq", IntToString(nJobSeq));
        KSE_SetData("dt_lastgate", "-1");
    }
    nWaited = nWaited + 1;
    KSE_SetData("dt_waited", IntToString(nWaited));
    int nGate = 0;
    if (!KSE_HasData("dt_ready") || KSE_GetData("dt_ready") != "1") nGate = 32;
    else
    {
        // "state" only asks for the saved number (the client has not learned it yet); it changes nothing
        if (sAction == "state")
        {
            KSE_SetData("dt_job", "");
            KSE_SetData("dt_lastseq", IntToString(nSeq));
            DtLog("STATE|seq=" + IntToString(nSeq));
            return;
        }
        if (nJobSeq == nSeq)
        {
            KSE_SetData("dt_job", "");
            DtLog("DUP|seq=" + IntToString(nJobSeq));
            return;
        }
        if (nJobSeq != (nSeq + 1) % 256)
        {
            KSE_SetData("dt_job", "");
            DtLog("SYNC|seq=" + IntToString(nJobSeq) + "|have=" + IntToString(nSeq));
            return;
        }
        nGate = DtGateBits(oPC);
        // An incoming DeathLink is not held for combat (that is when it matters), and a player who is already dead is not a reason to wait: the
        // arm reads wasDead itself. Every other gate (conversation, scene, cutscene, locked player, area just loaded, no party) still holds it.
        if (sAction == "arm" && sArgs == "force_death")
        {
            if ((nGate / 16) % 2 == 1) nGate = nGate - 16;
            if ((nGate / 256) % 2 == 1) nGate = nGate - 256;
        }
    }

    if (nGate != 0)
    {
        int nLast = StringToInt(KSE_GetData("dt_lastgate"));
        if (nGate != nLast || nWaited % 6 == 1)
        {
            KSE_SetData("dt_lastgate", IntToString(nGate));
            DtLog("WAIT|seq=" + IntToString(nJobSeq) + "|gate=" + IntToString(nGate) + "|waited=" + IntToString(nWaited));
        }
        return;
    }

    DtSetSeq(oPC, nJobSeq);
    KSE_SetData("dt_job", "");
    KSE_SetData("dt_lastseq", IntToString(nJobSeq));
    int nRan = DtRun(oPC, sAction, sArgs);
    if (nRan == 1)
    {
        DtLog("APPLIED|seq=" + IntToString(nJobSeq) + "|action=" + sAction + "|waited=" + IntToString(nWaited) + "|party=" + IntToString(GetPartyMemberCount()));
        if (sMsg != "") DtShowMessage(oPC, sMsg);
    }
    else if (nRan == 2)
        DtLog("FAILED|seq=" + IntToString(nJobSeq) + "|action=" + sAction + "|args=" + sArgs);
    else
        DtLog("UNKNOWN|seq=" + IntToString(nJobSeq) + "|action=" + sAction);
}
'''
    # The fixed arms the dispatcher can run, with the same bodies the area-entry batches use (one source of truth).
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import generate_trampoline_batch as _gtb
    _DT_ARM_LABELS = [
        "class_guardian", "class_consular", "class_sentinel", "pc_class_soldier", "pc_class_scout", "pc_class_scoundrel",
        "companion_bastila", "companion_canderous", "companion_carth", "companion_hk47", "companion_jolee",
        "companion_juhani", "companion_mission", "companion_t3m4", "companion_zaalbar", "xp", "credits",
        "force_death",   # an incoming DeathLink (not held for combat, see DtTick)
        "computer_use", "demolitions", "stealth", "awareness", "persuade", "repair", "security", "treat_injury",
        "ability_strength", "ability_dexterity", "ability_constitution", "ability_intelligence", "ability_wisdom",
        "ability_charisma",
        "pc_droid",
        "journal_tracker_20", "journal_tracker_40", "journal_tracker_60", "journal_tracker_80", "journal_tracker_100", "journal_tracker_1",
    ]
    _by_label = {label: body for label, body in _gtb.APPLIES.values()}
    _arm_funcs = ["// ---- fixed arms (generated from APPLIES) ----"]
    for _label in _DT_ARM_LABELS:
        _arm_funcs.append("void DtArm_" + _label + "()")
        _arm_funcs.append("{")
        _arm_funcs.extend("    " + stmt for stmt in _by_label[_label])
        _arm_funcs.append("}")
        _arm_funcs.append("")
    import dispatch_actions as _da
    _arm_funcs.append(_da.build_arm_checks(_by_label, _DT_ARM_LABELS))
    _arm_funcs.append("// 0 = no such arm, 1 = it ran and did its job, 2 = it ran but the result is not there (see dispatch_actions.build_arm_checks)")
    _arm_funcs.append("int DtArm(string sName)")
    _arm_funcs.append("{")
    _arm_funcs.append("    object oPC = GetFirstPC();")
    _arm_funcs.append("    int nBefore = DtArmValue(oPC, sName);")
    for _label in _DT_ARM_LABELS:
        _arm_funcs.append('    if (sName == "' + _label + '") { DtArm_' + _label + "(); return DtArmCheck(sName, nBefore, DtArmValue(oPC, sName)); }")
    _arm_funcs.append("    return 0;")
    _arm_funcs.append("}")
    _arm_funcs.append("")
    _marker = "// On-screen text does not work in this game"
    assert DT_FUNCTIONS.count(_marker) == 1
    DT_FUNCTIONS = DT_FUNCTIONS.replace(_marker, "\n".join(_arm_funcs) + "\n// ---- parameterized actions (dispatch_actions.py) ----\n"
                                        + _da.build_source(_gtb) + "\n" + _marker)
    lines.extend(DT_FUNCTIONS.split("\n"))
lines.append("void main()")
lines.append("{")
lines.append("    // A begin without an end in kse.log marks a poll that stopped partway. The stage markers")
lines.append("    // s1-s4 (which find WHERE it stopped) are only logged when the previous poll never reached")
lines.append("    // its end, so a poll that keeps stopping at the same place leaves its trail from the next")
lines.append("    // poll on without four extra lines on every healthy poll.")
lines.append('    int bTrace = (KSE_HasData("poll_open") && KSE_GetData("poll_open") == "1");')
lines.append('    KSE_SetData("poll_open", "1");')
lines.append('    KSE_Diag(176, "AP|POLLRUN|begin|party=" + IntToString(GetPartyMemberCount()));')
lines.append("    EnsureHeartbeat();")
if cli_args.dispatch_test:
    lines.append("    DtTick();")
lines.append('    if (bTrace) KSE_Diag(176, "AP|POLLRUN|s1");')
lines.append("    CheckCompanionStuck();")
lines.append('    if (bTrace) KSE_Diag(176, "AP|POLLRUN|s2");')
lines.append("    CheckPartyLevels();")
lines.append('    if (bTrace) KSE_Diag(176, "AP|POLLRUN|s3");')
lines.append("    CheckJoleeFieldRevert();")
lines.append('    if (bTrace) KSE_Diag(176, "AP|POLLRUN|s4");')
lines.append("    CheckQuests();")
lines.append("    CheckPlot();")
lines.append("    CheckJournal();")
lines.append("    CheckRecruitMarkers();")
lines.append("    CheckCrewMarkers();")
lines.append("    CheckXP();")
lines.append("    CheckCredits();")
lines.append("    CheckAbilityScores();")
lines.append("    CheckClasses();")
if wants_droid_look:
    lines.append("    CheckDroidLook();")
lines.append("    CheckCompanionClasses();")
lines.append("    CheckRoster();")
lines.append("    CheckProgressionItems();")
lines.append("    CheckSithArmor();")
lines.append("    CheckBossDatapads();")
lines.append("    CheckQuestItems();")
lines.append("    CheckBazaar();")
lines.append("    CheckTombDoors();")
lines.append("    CheckVisitedMarkers();")
lines.append("    CheckPlayerId();")
lines.append("    CheckHideoutCarth();")
lines.append("    CheckAPTrackerStage();")
lines.append("    CheckFeats();")
lines.append("    CheckFeatsFull();")
lines.append("    CheckForcePowers();")
lines.append("    CheckCharacterName();")
lines.append("    CheckSkills();")
lines.append("    CheckDeath();")
if wants_additional_enemies:
    lines.append("    CheckBountyCount();")
lines.append("    CheckAlignment();")
lines.append("    CheckGoal();")
lines.append("    CheckLevel();")
lines.append("    CheckForce();")
if wants_area_randomizer:
    lines.append("    CheckPlanetAvailability();")
lines.append("")
lines.append("    EnsureHeartbeat();")
lines.append('    KSE_SetData("poll_open", "0");')
lines.append('    KSE_Diag(176, "AP|POLLRUN|end");')
lines.append("}")

_poll_name = "ap_poll_shared"
out_path = os.path.join(SRC_DIR, f"{_poll_name}.nss")
with open(out_path, "w") as f:
    f.write("\n".join(lines) + "\n")

print(f"Wrote {out_path} ({len(lines)} lines) -- area_randomizer={wants_area_randomizer}")
if cli_args.dispatch_test:
    print("The job dispatcher is in this poll.")

if cli_args.no_deploy:
    sys.exit(0)

ncs_path = os.path.join(SRC_DIR, f"{_poll_name}.ncs")
# Same os.path.exists()-only bug generate_trampoline_batch.py already hit and
# fixed: extender/scripts_src/ ships a precompiled fallback .ncs for machines
# without nwnnsscomp, so a silently-failed compile would leave that stale
# file sitting there and this check would report success anyway -- and this
# script runs on EVERY Connect, regenerating area_randomizer/additional_
# enemies_mode polling for the seed, so a masked failure here means stale
# poll data forever, not just once. mtime_before + a compile-error stdout
# scan catches that.
mtime_before = os.path.getmtime(ncs_path) if os.path.exists(ncs_path) else None
result = subprocess.run(
    [NWNNSSCOMP, "-c", out_path, "-o", ncs_path],
    capture_output=True, text=True, cwd=SRC_DIR, timeout=30,
)
compiled_fresh = os.path.exists(ncs_path) and (
    mtime_before is None or os.path.getmtime(ncs_path) != mtime_before
)
compile_error = "Compilation aborted" in result.stdout or "Error:" in result.stdout
if not compiled_fresh or compile_error:
    print(f"COMPILE FAILED:\n{result.stdout}\n{result.stderr}")
    sys.exit(1)
print(f"Compiled -> {ncs_path}")

override_dir = os.path.join(GAME_DIR, "Override")
if not os.path.isdir(override_dir):
    print(f"ERROR: no Override folder at {override_dir} -- is --game-dir correct?")
    sys.exit(1)
deploy_path = os.path.join(override_dir, "ap_poll_shared.ncs")
with open(ncs_path, "rb") as f:
    data = f.read()
with open(deploy_path, "wb") as f:
    f.write(data)
print(f"Deployed -> {deploy_path}")
