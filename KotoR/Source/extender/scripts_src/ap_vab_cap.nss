#include "kse"

int StartingConditional()
{
    return GetIsObjectValid(GetItemPossessedBy(GetPCSpeaker(), "ap_vtok_abil")) && GetLocalNumber(GetPCSpeaker(), 61) < 5;
}
