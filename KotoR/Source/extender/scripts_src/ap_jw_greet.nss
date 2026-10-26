#include "kse"

int Held(object oPC, string sTag)
{
    object oItem = GetItemPossessedBy(oPC, sTag);
    if (!GetIsObjectValid(oItem)) return 0;
    return GetItemStackSize(oItem);
}

int StartingConditional()
{
    object oPC = GetPCSpeaker();
    int nBought = Held(oPC, "ap_bz_buy");
    int nSwapped = Held(oPC, "ap_bz_swap");
    int nTokens = Held(oPC, "ap_bz_token");
    SetCustomToken(9011, "Finds bought: " + IntToString(nBought) + " of 5. Trades done: " + IntToString(nSwapped) + " of 20. Tokens in your pack: " + IntToString(nTokens) + ".");
    SetCustomToken(9012, IntToString((1000 + 2000 * nBought)));
    return TRUE;
}
