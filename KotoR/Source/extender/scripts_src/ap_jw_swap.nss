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
    int nSwapped = Held(oPC, "ap_bz_swap");
    if (nSwapped >= 20) return;
    object oTokens = GetItemPossessedBy(oPC, "ap_bz_token");
    if (!GetIsObjectValid(oTokens)) return;
    int nHave = GetItemStackSize(oTokens);
    if (nHave < 5) return;
    if (nHave == 5) DestroyObject(oTokens);
    else SetItemStackSize(oTokens, nHave - 5);
    CreateItemOnObject("ap_bz_swap", oPC, 1);
    KSE_Diag(205, "AP|APPLIED|bazaar_swap|tokensLeft=" + IntToString(nHave - 5) + "|count=" + IntToString(nSwapped + 1));
}
