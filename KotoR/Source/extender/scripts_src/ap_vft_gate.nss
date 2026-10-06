#include "kse"

int StartingConditional()
{
    return GetIsObjectValid(GetItemPossessedBy(GetPCSpeaker(), "ap_vtok_feat"));
}
