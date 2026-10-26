#include "kse"

int Held(object oPC, string sTag)
{
    object oItem = GetItemPossessedBy(oPC, sTag);
    if (!GetIsObjectValid(oItem)) return 0;
    return GetItemStackSize(oItem);
}

void main()
{
    object oPC = GetPCSpeaker();
    int nBought = Held(oPC, "ap_bz_buy");
    if (nBought >= 5) return;
    int nPrice = (1000 + 2000 * nBought);
    if (GetGold(oPC) < nPrice) return;
    int nAfter = KSE_SetCredits(oPC, GetGold(oPC) - nPrice);
    CreateItemOnObject("ap_bz_buy", oPC, 1);
    KSE_Diag(204, "AP|APPLIED|bazaar_buy|price=" + IntToString(nPrice) + "|creditsAfter=" + IntToString(nAfter) + "|count=" + IntToString(nBought + 1));
}
