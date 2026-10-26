#include "kse"

void SwapSlot(int nNpc, string sTag, string sSpot, string sTemplate)
{
    object oPC = GetPCSpeaker();
    if (!GetIsObjectValid(oPC)) oPC = GetFirstPC();
    object oOld = GetObjectByTag(sTag);
    int bInParty = IsNPCPartyMember(nNpc);
    location lLoc = GetLocation(oPC);
    object oSpot = GetWaypointByTag(sSpot);
    if (!bInParty && GetIsObjectValid(oSpot)) lLoc = GetLocation(oSpot);
    RemovePartyMember(nNpc);
    RemoveAvailableNPC(nNpc);
    if (GetIsObjectValid(oOld)) DestroyObject(oOld);
    AddAvailableNPCByTemplate(nNpc, sTemplate);
    object oNew = CreateObject(OBJECT_TYPE_CREATURE, sTemplate, lLoc);
    if (bInParty) AddPartyMember(nNpc, oNew);
    SetNPCSelectability(nNpc, TRUE);
    KSE_Diag(206, "AP|APPLIED|newcompanion_swap|template=" + sTemplate + "|inParty=" + IntToString(bInParty) + "|valid=" + IntToString(GetIsObjectValid(oNew)) + "|slot=" + sTag);
}

void main()
{
    SwapSlot(NPC_T3_M4, "t3m4", "pebn_t3m4", "p_trask_t3");
}
