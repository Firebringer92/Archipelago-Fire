#include "kse"

void main()
{
    object oPC = GetPCSpeaker();
    int nAfter = KSE_SetCredits(oPC, GetGold(oPC) - 3000);
    KSE_GrantFeatArrayA(43, oPC);
    KSE_Diag(200, "AP|APPLIED|vendor_train_feat|feat=43|creditsAfter=" + IntToString(nAfter));
}
