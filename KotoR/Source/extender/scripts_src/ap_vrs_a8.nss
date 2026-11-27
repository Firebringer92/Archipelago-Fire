#include "kse"

void main()
{
    object oPC = GetPCSpeaker();
    int nFeat = StringToInt(KSE_GetData("vslot8"));
    KSE_SetData("vend_state", "fail");
    if (nFeat <= 0) return;
    KSE_RemoveFeatArrayA(nFeat, oPC);
    if (KSE_GetFeatAcquired(nFeat, oPC))
    {
        KSE_Diag(200, "AP|REFUSED|vendor_remove_feat|feat=" + IntToString(nFeat));
        return;
    }
    KSE_SetData("vend_state", "ok");
    KSE_Diag(200, "AP|APPLIED|vendor_remove_feat|feat=" + IntToString(nFeat));
}
