// k2ap_per.nss -- Shortened Peragus: the "short hallway" (variant A of docs/PERAGUS_CONDENSED.md; data/peragus.json lists the same steps).
//
// Everything happens in the module 101PER, the one module of the opening that is kept whole. Called from the area entry hook (tools/build_area_wrappers.py joins
// K2AP_PeragusEnter() onto every area entry script, after the game's own script has run), so it needs no script of its own in the module.
//
//   Act I     Entering 101PER before the Sith ship has docked: the doors that hold the opening up are unlocked (Atton's cell, the medical bay) and the story's own
//             console switch state is set, so Atton's conversation starts as soon as the cell door is opened.
//   The jump  When Atton's conversation is over (he has given the administration code) the player is told, the screen fades, and 101PER is loaded again with the
//             docking movie: Act II of the story, the Sith ship docked and Kreia waiting. What the skipped parts (the T3-M4 trip, the mining tunnels, the walk outside,
//             the dormitories) would have set is set here, and the supplies the Harbinger and the hangar consoles need are handed over.
//   Act II    Kreia is made and her conversation started (the two triggers that do that in the game fire only for a player who comes from the dormitories). Once she has
//             joined, the HK-50 scene, where Atton joins, is started by script when the player gets near it: the game starts it with a trigger the player can walk past.
//
// Nothing here runs without shortened_peragus=1 and the client's patch. The story's own scripts do the work wherever they can (a_spawnkriea2, a_door105per, a_spawnhk50
// are run as they are; all three decide by the story's globals, so running them twice, or after the game's own triggers, does nothing).
// Lines for the client's recorder: PR|<step>|<detail>.

#include "k2se_disp"

int K2AP_PerOn()
{
    if (!K2SE_IsPresent()) return FALSE;
    if (K2AP_Patched() == 0) return FALSE;
    return K2AP_ShortenedPeragus() != 0;
}

void K2AP_PerTick(int nGen);

void K2AP_PerLog(string sStep, string sDetail)
{
    K2SE_OutboxPut("PR|" + sStep + "|" + sDetail);
}

// Act I: the doors that hold the opening up. Safe to repeat.
void K2AP_PerStart()
{
    SetGlobalNumber("101PER_Switch", 2);                    // the console's security switch is "pressed" (the droids are left as they are)
    SetGlobalNumber("101PER_Kreia_Telepath", 1);            // the cell door's OnOpen starts Atton's conversation only with this set
    object oCell = GetObjectByTag("PrisonRoomDr");
    object oMed = GetObjectByTag("MedBayDoor");
    if (GetIsObjectValid(oCell)) SetLocked(oCell, FALSE);
    if (GetIsObjectValid(oMed)) SetLocked(oMed, FALSE);
    K2AP_PerLog("start", IntToString(GetIsObjectValid(oCell)) + IntToString(GetIsObjectValid(oMed)));
}

// The new module: the state the skipped parts would have left, then the load. Last thing that happens in Act I.
void K2AP_PerLoad(object oPC)
{
    // The T3-M4 trip: slot 8 is re-opened here or the first Ebon Hawk scene (it needs Atton, Kreia and T3-M4) never plays.
    object oT3 = GetObjectByTag("T3M4");
    if (GetIsObjectValid(oT3))
    {
        AddAvailableNPCByObject(8, oT3);
        DestroyObject(oT3);
    }
    SetNPCSelectability(8, 0);
    SetGlobalNumber("105PER_T3_End", 2);
    SetGlobalNumber("101PER_Open_Hatch", 1);
    SetGlobalNumber("106PER_Hang_Comp", 1);                 // the hangar console starts repaired
    // The Medical Bay Murders flags, so that quest can still finish.
    SetGlobalNumber("101PER_Know_Sedatives", 1);
    SetGlobalNumber("101PER_Med_Bay_Mur", 2);
    SetGlobalNumber("103PER_HK50_Voice", 1);
    SetGlobalNumber("103PER_HK50_Code", 1);
    SetGlobalNumber("103PER_Talk_HK50", 1);
    AddJournalQuestEntry("MedBayMur", 40);
    // What the Harbinger's consoles (navicomputer, maintenance, engine) and the hangar console use.
    CreateItemOnObject("g_i_progspike01", oPC, 4);
    CreateItemOnObject("g_i_parts01", oPC, 3);
    SetGlobalNumber("101PER_Sion_Arrives", 1);              // exactly 1: the HK-50 scene, Kreia and the later T3-M4 pickup all test it
    K2AP_PerLog("jump", IntToString(K2SE_ConfigInt("ap_per_inplace", 0)));
    if (K2SE_ConfigInt("ap_per_inplace", 0) == 0)
    {
        StartNewModule("101PER", "From_105PER", "permov03");
        return;
    }
    // Without a reload (config ap_per_inplace=1): the movie, the docked ship and a jump to the Act II start.
    PlayMovie("permov03");
    PlayRoomAnimation("101PERzc", 1);
    object oWay = GetWaypointByTag("From_105PER");
    if (GetIsObjectValid(oWay)) AssignCommand(oPC, ActionJumpToObject(oWay));
    SetGlobalFadeIn(0.0, 0.75, 0.0, 0.0, 0.0);
    int nGen = StringToInt(K2SE_MemGet("per_gen")) + 1;       // the loop that waited for Atton ended with the jump; Act II needs its own
    K2SE_MemSet("per_gen", IntToString(nGen));
    DelayCommand(1.5, K2AP_PerTick(nGen));
}

void K2AP_PerFade()
{
    SetGlobalFadeOut(0.0, 0.75, 0.0, 0.0, 0.0);
}

// Atton has told the player what he knows: the Sith arrive.
void K2AP_PerJump(object oPC)
{
    K2AP_PerLog("notice", "");
    FloatingTextStringOnCreature("Something large has docked with the facility. The lockdown is over, but you are not alone.", oPC, FALSE);
    ApplyEffectToObject(DURATION_TYPE_TEMPORARY, EffectCutSceneParalyze(), oPC, 5.0);
    DelayCommand(3.0, K2AP_PerFade());
    DelayCommand(4.0, K2AP_PerLoad(oPC));
}

// Every locked door of the area is unlocked: the story's own locks (the lockdown, the dormitory lift, security doors) are tied to parts of the story this variant skips, so some can
// never be opened again with the player's tools and would trap them. Reported as "PR|unlock|<how many>:<tags of the doors>" only when something was locked.
int K2AP_PerUnlockDoors(object oPC)
{
    int nOpened = 0;
    string sTags = "";
    int n;
    for (n = 1; n <= 80; n++)
    {
        object oDoor = GetNearestObject(OBJECT_TYPE_DOOR, oPC, n);
        if (!GetIsObjectValid(oDoor)) break;
        if (GetLocked(oDoor))
        {
            SetLocked(oDoor, FALSE);
            nOpened++;
            if (GetStringLength(sTags) < 110) sTags = sTags + (sTags == "" ? "" : ",") + GetTag(oDoor);
        }
    }
    if (nOpened > 0) K2AP_PerLog("unlock", IntToString(nOpened) + ":" + sTags);
    return nOpened;
}

// The dormitories (105PER) are skipped, and the lift back up from them is locked until the player has used its console (the story's own turbolift puzzle): a player who gets in
// must not be stuck there. The lift is unlocked here and its quest closed as solved. Runs on entering 105PER.
void K2AP_PerDorm()
{
    object oLift = GetObjectByTag("Door_To_101PER");
    if (GetIsObjectValid(oLift)) SetLocked(oLift, FALSE);
    K2AP_PerUnlockDoors(GetFirstPC());
    AddJournalQuestEntry("TurboliftLockdown", 99, FALSE);
    K2AP_PerLog("dorm", IntToString(GetIsObjectValid(oLift)));
}

// Act II. Returns FALSE when there is nothing left to do.
int K2AP_PerActTwo(object oPC)
{
    int nSpawn = GetGlobalNumber("101PER_Kreia_Spawn");
    if (nSpawn < 3)
    {
        ExecuteScript("a_spawnkriea2", oPC);                // makes Kreia where the story makes her
        K2AP_PerLog("kreia", "made");
        return TRUE;
    }
    if (!DispCalm(oPC)) return TRUE;
    if (nSpawn == 3)
    {
        ExecuteScript("a_door105per", oPC);                 // opens the dormitory hatch and starts her conversation
        K2AP_PerLog("kreia", "talk");
        return TRUE;
    }
    if (GetGlobalNumber("101PER_Kreia_Joined") == 0) return TRUE;
    if (GetGlobalNumber("101PER_HK50_Spawned") != 0) return FALSE;
    object oAt = GetObjectByTag("WP_HK50_SPAWN");
    object oDoor = GetObjectByTag("151HARDoor");
    int bNear = (GetIsObjectValid(oAt) && GetDistanceBetween(oPC, oAt) < 30.0) || (GetIsObjectValid(oDoor) && GetDistanceBetween(oPC, oDoor) < 30.0);
    if (!bNear) return TRUE;
    K2AP_PerLog("hk50", IntToString(GetIsObjectValid(GetObjectByTag("Atton"))) + IntToString(GetIsObjectValid(GetObjectByTag("Kreia"))));
    ExecuteScript("a_spawnhk50", oPC);
    return FALSE;
}

void K2AP_PerTick(int nGen)
{
    if (StringToInt(K2SE_MemGet("per_gen")) != nGen) return;
    if (GetStringUpperCase(GetModuleName()) != "101PER") return;
    object oPC = GetFirstPC();
    if (GetIsObjectValid(oPC) && GetTag(oPC) == "")         // the Exile, not a body the story has handed over
    {
        K2AP_PerUnlockDoors(oPC);                           // no door stays locked, in either act (the dormitory lift too: K2AP_PerDorm brings the player back from there)
        if (GetGlobalNumber("101PER_Sion_Arrives") == 0)
        {
            if (GetGlobalNumber("101PER_Know_Adm_Code") != 0 && DispCalm(oPC))
            {
                K2SE_MemSet("per_gen", IntToString(nGen + 1));
                K2AP_PerJump(oPC);
                return;
            }
        }
        else if (!K2AP_PerActTwo(oPC)) return;
    }
    DelayCommand(1.5, K2AP_PerTick(nGen));
}

// Every Peragus module (the fuel depot, the hangar, the tunnels...) has doors whose locks wait for story steps the shortened opening skips, and some of them are locked again
// by the area's own scripts (a trigger, a terminal) after it is entered, or by a game that was saved while they were locked. They are unlocked as the area is entered and again
// every four seconds for as long as the player stays (the module files hold them unlocked too: client/k2_doors.py peragus_unlock). The loop ends with the area, like every
// timer, and a newer entry (the generation number) ends an older loop.
void K2AP_PerDoorsRepeat(int nGen)
{
    if (StringToInt(K2SE_MemGet("per_dgen")) != nGen) return;
    if (GetStringRight(GetStringUpperCase(GetModuleName()), 3) != "PER") return;
    object oPC = GetFirstPC();
    if (GetIsObjectValid(oPC)) K2AP_PerUnlockDoors(oPC);
    DelayCommand(4.0, K2AP_PerDoorsRepeat(nGen));
}

// The area entry hook (after the game's own entry script).
void K2AP_PeragusEnter()
{
    if (!K2AP_PerOn()) return;
    int nDoors = StringToInt(K2SE_MemGet("per_dgen")) + 1;
    K2SE_MemSet("per_dgen", IntToString(nDoors));
    K2AP_PerDoorsRepeat(nDoors);
    if (GetStringUpperCase(GetModuleName()) == "105PER")
    {
        K2AP_PerDorm();
        DelayCommand(2.0, K2AP_PerDorm());                      // the module's own entry script may set the lift after this hook
        return;
    }
    if (GetStringUpperCase(GetModuleName()) != "101PER") return;
    if (GetGlobalNumber("101PER_Sion_Arrives") == 0) K2AP_PerStart();
    int nGen = StringToInt(K2SE_MemGet("per_gen")) + 1;
    K2SE_MemSet("per_gen", IntToString(nGen));
    DelayCommand(1.5, K2AP_PerTick(nGen));
}
