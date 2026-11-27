#include "kse"

void main()
{
    object oPC = GetPCSpeaker();
    int nAfter = KSE_SetCredits(oPC, GetGold(oPC) - 5000);
    int nNew = GetGoodEvilValue(oPC) + 10;
    if (nNew > 100) nNew = 100;
    SetGoodEvilValue(oPC, nNew);
    KSE_Diag(200, "AP|APPLIED|vendor_align_donate|creditsAfter=" + IntToString(nAfter));
}
