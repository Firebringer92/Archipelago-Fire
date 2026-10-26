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
    return Held(oPC, "ap_bz_swap") < 20 && Held(oPC, "ap_bz_token") >= 5;
}
