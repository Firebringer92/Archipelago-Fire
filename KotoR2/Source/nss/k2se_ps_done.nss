#include "k2se"
// Exit script of the research party selection screen: log the result, then remove every companion the test made available.
void main()
{
    string s = "party selection closed, picked (cancelled=" + IntToString(!GetRunScriptVar()) + "):";
    int i;
    for (i = 0; i < 12; i++)
    {
        if (IsNPCPartyMember(i)) s = s + " " + IntToString(i);
    }
    if (K2SE_IsPresent())
    {
        K2SE_Diag("PS", s);
        int nBack = K2SE_WriteMem(GetFirstPC(), 3, 0x8A09A0, 1, 0xE0) + K2SE_WriteMem(GetFirstPC(), 3, 0x8A09C4, 1, 0xE2) + K2SE_WriteMem(GetFirstPC(), 3, 0x8A09E7, 1, 0xE1) +
                    K2SE_WriteMem(GetFirstPC(), 3, 0x8A0DE1, 1, 0xE1) + K2SE_WriteMem(GetFirstPC(), 3, 0x8A0E05, 1, 0xE0) + K2SE_WriteMem(GetFirstPC(), 3, 0x8A0E29, 1, 0xE2);
        K2SE_Diag("PS", "panel patch restored: " + IntToString(nBack) + " of 6 bytes");
    }
    for (i = 0; i < 12; i++)
    {
        if (i != 8)
        {
            if (IsNPCPartyMember(i)) RemovePartyMember(i);
            RemoveAvailableNPC(i);
            SetNPCSelectability(i, -1);
        }
    }
}
