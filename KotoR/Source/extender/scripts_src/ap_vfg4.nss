#include "kse"

void main()
{
    object oPC = GetPCSpeaker();
    KSE_SetData("vend_feat", "4");
    if (GetGold(oPC) < 3000)
    {
        KSE_SetData("vend_state", "poor");
        return;
    }
    KSE_GetVersion();   // clears the errno, so the read below belongs to this grant
    KSE_GrantFeatArrayA(4, oPC);
    if (KSE_GetFeatAcquired(4, oPC))
    {
        int nAfter = KSE_SetCredits(oPC, GetGold(oPC) - 3000);
        KSE_SetData("vend_state", "ok");
        KSE_Diag(200, "AP|APPLIED|vendor_train_feat|feat=4|creditsAfter=" + IntToString(nAfter));
        return;
    }
    if (KSE_ERRNO() == KSE_E_AT_CAPACITY())
    {
        KSE_SetData("vend_state", "full");
        KSE_Diag(200, "AP|VENDOR|feat_list_full|feat=4");
        return;
    }
    KSE_SetData("vend_state", "fail");
    KSE_Diag(200, "AP|REFUSED|vendor_train_feat|feat=4|errno=" + IntToString(KSE_ERRNO()) + "|credits=" + IntToString(GetGold(oPC)));
}
