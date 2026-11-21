// k2ap_pcdone.nss -- exit script of the party selection screen opened by the Party Console's first reply: a companion the player put in the party no longer stands
// (nss/k2ap_stand.nss), and one line goes to the extender's log.
#include "k2ap_stand"

void main()
{
    int k;
    for (k = 0; k < 2; k++)
    {
        int nSlot = K2AP_StandGet(k);
        if (nSlot >= 0 && IsNPCPartyMember(nSlot)) K2AP_StandSet(k, -1);
    }
    if (K2SE_IsPresent()) K2SE_Diag("ITEM", "party console: party screen closed, party count " + IntToString(GetPartyMemberCount()));
}
