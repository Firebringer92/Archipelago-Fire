// k2ap_pcsdone.nss -- exit script of the screen opened by k2ap_pcstand: the companions picked stand beside the Exile, the active pair put aside comes back. The exit script
// has no owning object of its own, so the work is scheduled on the player. A cancelled screen (run variable 0) changes nothing about who stands: the active pair put aside
// just comes back.
#include "k2ap_stand"

void K2AP_PickFinish(int nPicked)
{
    object oPC = GetFirstPC();
    int nPick0 = -1;
    int nPick1 = -1;
    int k;
    if (nPicked != 0)
    {
        nPick0 = K2AP_StandActive(0);
        nPick1 = K2AP_StandActive(1);
        for (k = 0; k < 2; k++)
        {
            int nOld = K2AP_StandGet(k);
            if (nOld >= 0 && nOld != nPick0 && nOld != nPick1) K2AP_StandRelease(nOld);     // replaced: the new pick stands, the old one goes home
        }
        if (nPick0 >= 0) RemovePartyMember(nPick0);                                       // the creature stays where it is and stands
        if (nPick1 >= 0) RemovePartyMember(nPick1);
        K2AP_StandSet(0, nPick0);
        K2AP_StandSet(1, nPick1);
    }
    else
    {
        nPick0 = K2AP_StandGet(0);
        nPick1 = K2AP_StandGet(1);
    }
    for (k = 0; k < 2; k++)
    {
        int nBack = K2AP_StandSaved(k);
        K2AP_StandSaveSet(k, -1);
        if (nBack < 0 || nBack == nPick0 || nBack == nPick1 || IsNPCPartyMember(nBack)) continue;
        object o = K2AP_StandCreature(nBack);
        if (!GetIsObjectValid(o) && IsAvailableCreature(nBack)) o = SpawnAvailableNPC(nBack, GetLocation(oPC));
        if (GetIsObjectValid(o))
        {
            AssignCommand(o, ClearAllActions());
            AddPartyMember(nBack, o);
        }
    }
    K2AP_StandLog("picked", IntToString(nPick0) + "|" + IntToString(nPick1));
    if (K2AP_StandOn() && (nPick0 >= 0 || nPick1 >= 0)) K2AP_StandStart();
    if (nPicked != 0) FloatingTextStringOnCreature("Standing beside you: " + K2AP_StandNames(nPick0, nPick1) + ".", oPC, FALSE);
}

void main()
{
    int nPicked = GetRunScriptVar();
    AssignCommand(GetFirstPC(), DelayCommand(1.0, K2AP_PickFinish(nPicked)));
}
