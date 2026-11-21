// k2ap_pcopen.nss -- the Party Console's reply "Change your active party.": opens the game's party selection screen (the paged one, with every unlocked companion,
// when the seed has extra companions; client/k2_extras.py writes the switches). The screen is the game's own: where the story has locked it (the prologue Ebon Hawk, some
// scenes) it shows nothing to change, exactly as when opened by hand. k2ap_pcdone runs when it closes.
#include "k2se"

void main()
{
    if (K2SE_IsPresent()) K2SE_Diag("ITEM", "party console: party screen opened, party count " + IntToString(GetPartyMemberCount()));
    ShowPartySelectionGUI("k2ap_pcdone", -1, -1, TRUE);
}
