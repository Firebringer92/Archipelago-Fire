#include "kse"

void main()
{
    object oPC = GetPCSpeaker();
    int nAfter = KSE_SetCredits(oPC, GetGold(oPC) - 4000);
    KSE_SetCreatureField(oPC, KSE_FIELD_INCREMENT_CON_BASE(), 1);
    int nCount = GetLocalNumber(oPC, 61) + 1;
    SetLocalNumber(oPC, 61, nCount);
    KSE_Diag(200, "AP|APPLIED|vendor_train_ability|ability=ABILITY_CONSTITUTION|creditsAfter=" + IntToString(nAfter) + "|count=" + IntToString(nCount));
}
