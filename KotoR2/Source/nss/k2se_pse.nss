#include "k2se"
// Exit script of the party screen test (research stage 52): logs that the screen's exit script ran and who is in the party.
void main()
{
    string sIn = "";
    int i;
    for (i = 0; i < 12; i++)
        if (IsNPCPartyMember(i)) sIn = sIn + IntToString(i) + " ";
    K2SE_Diag("PSE", "exit script ran; party count " + IntToString(GetPartyMemberCount()) + "; companions in party: " + sIn);
}
