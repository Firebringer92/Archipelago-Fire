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
    int nBought = Held(oPC, "ap_bz_buy"); return nBought < 5 && GetGold(oPC) < (1000 + 2000 * nBought);
}
