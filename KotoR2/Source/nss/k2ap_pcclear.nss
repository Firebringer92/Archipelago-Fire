// k2ap_pcclear.nss -- the Party Console's reply "Send the standing companions away.": they go back to the base with everything they carry.
#include "k2ap_stand"

void main()
{
    int k;
    for (k = 0; k < 2; k++)
    {
        K2AP_StandRelease(K2AP_StandGet(k));
        K2AP_StandSet(k, -1);
    }
    FloatingTextStringOnCreature("Nobody stands beside you now.", GetFirstPC(), FALSE);
}
