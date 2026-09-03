// Default/idle state for the k_pend_modab.ncs trigger slot -- swapped back
// in after an APPLY, so reloading the module again doesn't repeat the grant.
#include "kse"

void main()
{
    if (KSE_GetVersion() <= 0) return;
    KSE_Diag(1, "AP|PING|heartbeat idle");
}
