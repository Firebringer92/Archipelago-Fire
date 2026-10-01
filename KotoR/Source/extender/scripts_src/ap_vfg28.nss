#include "kse"

void main()
{
    object oPC = GetPCSpeaker();
    int nAfter = KSE_SetCredits(oPC, GetGold(oPC) - 3000);
    KSE_GrantFeatArrayA(28, oPC);
    KSE_Diag(200, "AP|APPLIED|vendor_train_feat|feat=28|creditsAfter=" + IntToString(nAfter));
}
