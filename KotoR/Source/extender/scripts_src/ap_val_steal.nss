#include "kse"

void main()
{
    object oPC = GetPCSpeaker();
    int nAfter = KSE_SetCredits(oPC, GetGold(oPC) + 1000);
    AdjustAlignment(oPC, ALIGNMENT_DARK_SIDE, 10);
    KSE_Diag(200, "AP|APPLIED|vendor_align_steal|creditsAfter=" + IntToString(nAfter));
}
