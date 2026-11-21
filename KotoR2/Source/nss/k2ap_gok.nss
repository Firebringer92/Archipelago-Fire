// k2ap_gok.nss -- condition of the gift menu's replies: the reply for the companion in script parameter 1 is shown only when that companion can be picked now.
#include "k2ap_gift"

int StartingConditional()
{
    return K2AP_GiftOffered(GetScriptParameter(1));
}
