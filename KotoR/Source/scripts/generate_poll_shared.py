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
# seed at a time, but wrong the moment a tester's own machine/seed
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
cli_args = parser.parse_args()
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
lines.append("void CheckQuests()")
lines.append("{")
for name in done_flags:
    lines.append(f'    if (GetGlobalBoolean("{name}"))')
    lines.append("    {")
    lines.append(f'        KSE_Diag(21, "AP|CHECK|QUEST|{name}");')
    lines.append("    }")
lines.append("}")
lines.append("")
lines.append("// _PLOT trackers are real globalcat.2da Number globals (same proven-")
lines.append("// reliable category as the _DONE booleans above -- not a custom name, so")
lines.append("// no workaround needed). Reports the CURRENT stage value every poll,")
lines.append("// skipping 0 (not-yet-started, nothing for the client to act on). The")
lines.append("// client derives 'newly reached stage N' by comparing against its own")
lines.append("// memory of the highest stage already converted into a check, and can")
lines.append("// map each newly-crossed threshold to a separate AP location.")
lines.append("void CheckPlot()")
lines.append("{")
for name in plot_flags:
    lines.append(f'    int n{name} = GetGlobalNumber("{name}");')
    lines.append(f'    if (n{name} > 0)')
    lines.append("    {")
    lines.append(f'        KSE_Diag(25, "AP|CHECK|PLOT|{name}|value=" + IntToString(n{name}));')
    lines.append("    }")
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
lines.append("void CheckJournal()")
lines.append("{")
for tag in journal_tags:
    var = "".join(c if c.isalnum() else "_" for c in tag)
    lines.append(f'    int n{var} = GetJournalEntry("{tag}");')
    lines.append(f'    if (n{var} > 0)')
    lines.append("    {")
    lines.append(f'        KSE_Diag(30, "AP|CHECK|JOURNAL|{tag}|value=" + IntToString(n{var}));')
    lines.append("    }")
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
lines.append("// Same stateless design again: ability scores are granted as PERMANENT")
lines.append("// effects (EffectAbilityIncrease + DURATION_TYPE_PERMANENT), which are")
lines.append("// tied to the specific character save they were applied to -- a brand")
lines.append("// new save (or a restarted playthrough) starts with none of them, same")
lines.append("// as vanilla. Reporting current scores every poll lets the client notice")
lines.append("// a fresh save is behind what's actually been earned and reapply the")
lines.append("// missing effects automatically, instead of the player losing progress.")
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
lines.append("void CheckFeats()")
lines.append("{")
lines.append("    object oPC = GetFirstPC();")
lines.append('    string sHeld = "";')
for feat_id in _ALL_FEAT_IDS:
    lines.append(f"    if (KSE_GetFeatAcquired({feat_id}, oPC)) sHeld += \"{feat_id},\";")
lines.append('    KSE_Diag(135, "AP|FEATREPORT|" + sHeld);')
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
lines.append("void CheckSkills()")
lines.append("{")
lines.append("    object oPC = GetFirstPC();")
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
lines.append("// derives newly-crossed 10-point thresholds (and the True Neutral/Fallen")
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

lines.append("void main()")
lines.append("{")
lines.append("    CheckQuests();")
lines.append("    CheckPlot();")
lines.append("    CheckJournal();")
lines.append("    CheckXP();")
lines.append("    CheckCredits();")
lines.append("    CheckAbilityScores();")
lines.append("    CheckClasses();")
lines.append("    CheckFeats();")
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

out_path = os.path.join(SRC_DIR, "ap_poll_shared.nss")
with open(out_path, "w") as f:
    f.write("\n".join(lines) + "\n")

print(f"Wrote {out_path} ({len(lines)} lines) -- area_randomizer={wants_area_randomizer}")

if cli_args.no_deploy:
    sys.exit(0)

ncs_path = os.path.join(SRC_DIR, "ap_poll_shared.ncs")
result = subprocess.run([NWNNSSCOMP, "-c", out_path, "-o", ncs_path], capture_output=True, text=True, cwd=SRC_DIR)
if not os.path.exists(ncs_path):
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
