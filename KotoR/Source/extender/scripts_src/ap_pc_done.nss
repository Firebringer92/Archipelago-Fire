#include "kse"

// Exit script of the party selection screen.
void main()
{
    KSE_Diag(199, "AP|PARTYCON|closed|party=" + IntToString(GetPartyMemberCount()));
}
