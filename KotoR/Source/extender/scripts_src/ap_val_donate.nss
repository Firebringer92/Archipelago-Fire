#include "kse"

void main()
{
    object oPC = GetPCSpeaker();
    int nAfter = KSE_SetCredits(oPC, GetGold(oPC) - 5000);
    AdjustAlignment(oPC, ALIGNMENT_LIGHT_SIDE, 10);
    int nCount = GetLocalNumber(oPC, 63) + 1;
    SetLocalNumber(oPC, 63, nCount);
    KSE_Diag(200, "AP|APPLIED|vendor_align_donate|creditsAfter=" + IntToString(nAfter) + "|count=" + IntToString(nCount));
}
