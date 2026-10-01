#include "kse"

void main()
{
    object oPC = GetPCSpeaker();
    int nAfter = KSE_SetCredits(oPC, GetGold(oPC) - 1000);
    KSE_AdjustCreatureSkills(oPC, SKILL_SECURITY, 2);
    int nCount = GetLocalNumber(oPC, 60) + 1;
    SetLocalNumber(oPC, 60, nCount);
    KSE_Diag(200, "AP|APPLIED|vendor_train_skill|skill=SKILL_SECURITY|creditsAfter=" + IntToString(nAfter) + "|count=" + IntToString(nCount));
}
