#include "kse"

void main()
{
    object oPC = GetPCSpeaker();
    int nAfter = KSE_SetCredits(oPC, GetGold(oPC) - 3000);
    KSE_SetCreatureField(oPC, KSE_FIELD_ADD_FORCE_POWER(), 18);
    KSE_Diag(200, "AP|APPLIED|vendor_train_power|power=18|creditsAfter=" + IntToString(nAfter));
}
