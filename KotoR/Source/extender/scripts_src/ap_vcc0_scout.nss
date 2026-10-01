#include "kse"

void main()
{
    object oPC = GetPCSpeaker();
    int nAfter = KSE_SetCredits(oPC, GetGold(oPC) - 8000);
    KSE_SetCreatureField(oPC, KSE_FIELD_CLASS0_TYPE(), CLASS_TYPE_SCOUT);
    int nCount = GetLocalNumber(oPC, 63) + 1;
    SetLocalNumber(oPC, 63, nCount);
    KSE_Diag(200, "AP|APPLIED|vendor_class_change|slot=0|class=CLASS_TYPE_SCOUT|creditsAfter=" + IntToString(nAfter) + "|count=" + IntToString(nCount));
}
