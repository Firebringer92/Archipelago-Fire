#include "kse"

void main()
{
    object oPC = GetPCSpeaker();
    int nAfter = KSE_SetCredits(oPC, GetGold(oPC) + 1000);
    int nNew = GetGoodEvilValue(oPC) - 10;
    if (nNew < 0) nNew = 0;
    SetGoodEvilValue(oPC, nNew);
    KSE_Diag(200, "AP|APPLIED|vendor_align_steal|creditsAfter=" + IntToString(nAfter));
}
