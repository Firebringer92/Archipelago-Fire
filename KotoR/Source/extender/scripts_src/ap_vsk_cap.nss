#include "kse"

int StartingConditional()
{
    return GetIsObjectValid(GetItemPossessedBy(GetPCSpeaker(), "ap_vtok_skill")) && GetLocalNumber(GetPCSpeaker(), 60) < 5;
}
