// k2ap_gans.nss -- answer of the gift menu's replies: give the companion in script parameter 1 a gift.
#include "k2ap_gift"

void main()
{
    object oPC = GetPCSpeaker();
    if (!GetIsObjectValid(oPC)) oPC = GetFirstPC();
    K2AP_GiftGive(oPC, GetScriptParameter(1));
}
