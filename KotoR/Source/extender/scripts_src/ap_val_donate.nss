#include "kse"

void main()
{
    object oPC = GetPCSpeaker();
    int nAfter = KSE_SetCredits(oPC, GetGold(oPC) - 5000);
    AdjustAlignment(oPC, ALIGNMENT_LIGHT_SIDE, 10);
    KSE_Diag(200, "AP|APPLIED|vendor_align_donate|creditsAfter=" + IntToString(nAfter));
}
