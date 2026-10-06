// Shared helpers for the Leviathan-capture fix -- #include this (never
// compiled/run standalone) from ap_lev_trigger.nss and ap_lev_use.nss (stage the
// cast) and from ap_poll_shared (InLeviathanSequence, for the roster report).
//
// Why this exists: when the Ebon Hawk is captured (module ebo_m40aa) the
// conversation lev40_carth has the crew pick who escapes capture. It assumes
// Carth, Bastila, Canderous, Mission and T3-M4 are always present: its trigger
// script (k_pebo_carthtlk) only starts it when the Carth and Bastila objects
// exist, three of its escape options (Canderous, T3-M4, Mission) are offered
// unconditionally, and each plan is spoken by that companion. Under
// companion_mode=ap_gated/none (or when a recruit's AP item has not arrived)
// the missing ones leave no speaker, the conversation dies before its last
// step (the module jump to the Leviathan) and the player is stuck on the
// Hawk.
//
// What it does: when the scene's console is used, each of the cast who is not
// standing there is spawned at the scene's own waypoint (pebn_<name>), the way
// the vanilla Hawk-population script places the ones it has, and made
// available first if they were not. They are not put in the active party (the
// three-slot cap), they only have to be standing there and on the roster.
// Someone already available (recruited) is left completely alone.
//
// Taking them away again is NOT done here and keeps no state of its own (no
// flag in memory or in the save). The reconciler (kotor_reconciliation.py)
// compares the roster the poll reports (CheckRoster in ap_poll_shared,
// busy=1 while the Leviathan sequence is running) with the companions the
// player is entitled to, and purges the rest with the purge_companion trap.
#include "kse"

// Makes sure sTag's creature is standing in the scene. Not available at all:
// make them available too. Available but not standing here (recruited and
// benched; the vanilla Hawk-population script does not place everyone): spawn
// them without touching their roster entry. Returns 1 when a roster entry was
// added (for the log only).
int StageLevCastMember(string sKey, string sTag, int nNPC, string sTemplate, string sWaypointTag)
{
    if (GetIsObjectValid(GetObjectByTag(sTag))) return 0;

    location lLoc = GetLocation(GetFirstPC());
    object oWp = GetWaypointByTag(sWaypointTag);
    if (GetIsObjectValid(oWp)) lLoc = GetLocation(oWp);

    int bWasAvailable = IsAvailableCreature(nNPC);
    if (!bWasAvailable) AddAvailableNPCByTemplate(nNPC, sTemplate);
    SpawnAvailableNPC(nNPC, lLoc);
    // SpawnAvailableNPC is not guaranteed to produce a creature right after
    // the roster entry was added; fall back to creating one from the template.
    if (!GetIsObjectValid(GetObjectByTag(sTag)))
    {
        CreateObject(OBJECT_TYPE_CREATURE, sTemplate, lLoc);
    }
    return !bWasAvailable;
}

// True when all five creatures the conversation needs are standing here.
int LevCastReady()
{
    if (!GetIsObjectValid(GetObjectByTag("carth"))) return FALSE;
    if (!GetIsObjectValid(GetObjectByTag("bastila"))) return FALSE;
    if (!GetIsObjectValid(GetObjectByTag("cand"))) return FALSE;
    if (!GetIsObjectValid(GetObjectByTag("mission"))) return FALSE;
    if (!GetIsObjectValid(GetObjectByTag("t3m4"))) return FALSE;
    return TRUE;
}

void StageLevCast()
{
    // Each member is skipped when their creature already stands here, so
    // calling this again is harmless.
    string sAdded = "";
    if (StageLevCastMember("carth", "carth", NPC_CARTH, "p_carth", "pebn_carth")) sAdded = sAdded + "carth,";
    if (StageLevCastMember("bastila", "bastila", NPC_BASTILA, "p_bastilla", "pebn_bastila")) sAdded = sAdded + "bastila,";
    if (StageLevCastMember("cand", "cand", NPC_CANDEROUS, "p_cand", "pebn_canderous")) sAdded = sAdded + "cand,";
    if (StageLevCastMember("mission", "mission", NPC_MISSION, "p_mission", "pebn_mission")) sAdded = sAdded + "mission,";
    if (StageLevCastMember("t3m4", "t3m4", NPC_T3_M4, "p_t3m4", "pebn_t3m4")) sAdded = sAdded + "t3m4,";
    // Jolee and Juhani are not needed by any plan, but they stand on the deck
    // in the scene and talking to either of them ends it when they are absent.
    if (StageLevCastMember("jolee", "jolee", NPC_JOLEE, "p_jolee", "pebn_jolee")) sAdded = sAdded + "jolee,";
    if (StageLevCastMember("juhani", "juhani", NPC_JUHANI, "p_juhani", "pebn_juhani")) sAdded = sAdded + "juhani,";

    KSE_Diag(177, "AP|SAFEGUARD|lev_capture_cast|staged|added=" + sAdded
        + "|standing=" + IntToString(LevCastReady()));
}

// The post-escape Hawk scene (ebo_m40ad, conversation ebo_carth) needs Carth,
// who owns the conversation. Mission, Zaalbar, Jolee and Juhani are staged as
// well: their lines are chosen by who is actually there (its starters and
// k_pebo_* conditions), and talking to one who is absent ends the scene.
void StageLevCastCarth()
{
    string sAdded = "";
    if (StageLevCastMember("carth", "carth", NPC_CARTH, "p_carth", "pebn_carth")) sAdded = sAdded + "carth,";
    if (StageLevCastMember("mission", "mission", NPC_MISSION, "p_mission", "pebn_mission")) sAdded = sAdded + "mission,";
    if (StageLevCastMember("zaalbar", "zaalbar", NPC_ZAALBAR, "p_zaalbar", "pebn_zaalbar")) sAdded = sAdded + "zaalbar,";
    if (StageLevCastMember("jolee", "jolee", NPC_JOLEE, "p_jolee", "pebn_jolee")) sAdded = sAdded + "jolee,";
    if (StageLevCastMember("juhani", "juhani", NPC_JUHANI, "p_juhani", "pebn_juhani")) sAdded = sAdded + "juhani,";
    KSE_Diag(177, "AP|SAFEGUARD|lev_capture_cast|staged_escape|added=" + sAdded
        + "|carth_standing=" + IntToString(GetIsObjectValid(GetObjectByTag("carth"))));
}

// Puts the sensor console (ap_lev_console, a copy of the Hawk's galaxy-map
// terminal whose OnUsed is ap_lev_use) on the deck where nobody stands: the
// spot of HK-47 when he is not in the scene (the others' spots are staged
// into), or beside the player. The player starts the capture-plan conversation
// by using it, after the scene has loaded, whoever happens to be in the party.
void PlaceLevConsole()
{
    if (GetIsObjectValid(GetObjectByTag("ap_lev_console"))) return;

    location lLoc = GetLocation(GetFirstPC());
    if (!GetIsObjectValid(GetObjectByTag("HK47")) && GetIsObjectValid(GetWaypointByTag("pebn_hk47")))
        lLoc = GetLocation(GetWaypointByTag("pebn_hk47"));

    object oConsole = CreateObject(OBJECT_TYPE_PLACEABLE, "ap_lev_console", lLoc);
    KSE_Diag(177, "AP|SAFEGUARD|lev_capture_cast|console_placed=" + IntToString(GetIsObjectValid(oConsole)));
}

// True for every module of the capture-and-escape sequence: the captured Hawk
// (ebo_m40*, ebo_m46*) and the four Leviathan modules.
int InLeviathanSequence()
{
    string sModule = GetStringLowerCase(GetModuleFileName());
    if (GetStringLeft(sModule, 4) == "lev_") return TRUE;
    if (GetStringLeft(sModule, 7) == "ebo_m40") return TRUE;
    if (GetStringLeft(sModule, 7) == "ebo_m46") return TRUE;
    return FALSE;
}
