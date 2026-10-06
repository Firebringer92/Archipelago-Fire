#include "kse"

int StartingConditional()
{
    return GetIsObjectValid(GetItemPossessedBy(GetPCSpeaker(), "ap_vtok_align")) && GetLocalNumber(GetPCSpeaker(), 63) < 5;
}
