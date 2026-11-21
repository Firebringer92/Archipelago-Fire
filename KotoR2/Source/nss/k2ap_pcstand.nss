// k2ap_pcstand.nss -- the Party Console's reply "Choose standing companions.": the active followers are put aside (they stay in the area) and the party selection screen opens
// empty; whoever the player picks (up to two) stands beside the Exile instead. k2ap_pcsdone runs when the screen closes. See nss/k2ap_stand.nss.
#include "k2ap_stand"

void main()
{
    int k;
    for (k = 0; k < 2; k++) K2AP_StandSaveSet(k, K2AP_StandActive(k));
    for (k = 0; k < 2; k++)
    {
        if (K2AP_StandSaved(k) >= 0) RemovePartyMember(K2AP_StandSaved(k));
    }
    K2AP_StandLog("pick", IntToString(K2AP_StandSaved(0)) + "|" + IntToString(K2AP_StandSaved(1)));
    ShowPartySelectionGUI("k2ap_pcsdone", -1, -1, TRUE);
}
