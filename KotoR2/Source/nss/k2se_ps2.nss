#include "k2se"
#include "k2se_roster"
// Exit script of the second party selection screen: the two picked companions become pool entries 2 and 3, everything is selectable
// again, and the first pair is put in the party with the standing pair beside the player.
void Log(string s)
{
    if (K2SE_IsPresent()) K2SE_Diag("PS2", s);
}

void AfterSecond()
{
    int i;
    int n = 2;
    string s = "pool picks:";
    for (i = 0; i < 12; i++)
    {
        if (IsNPCPartyMember(i) && n < 4)
        {
            PoolSet(n, i);
            s = s + " " + SlotName(i);
            n++;
            RemoveNPCFromPartyToBase(i);
        }
    }
    for (i = 0; i < 12; i++) SetNPCSelectability(i, 1);
    Log(s + " (" + IntToString(n - 2) + "); pool = " + IntToString(PoolGet(0)) + "," + IntToString(PoolGet(1)) + "," + IntToString(PoolGet(2)) + "," + IntToString(PoolGet(3)));
    ApplyPair(0);
    Log("pair applied");
}

void main()
{
    int i;
    Log("second screen closed, picked=" + IntToString(GetRunScriptVar()));
    if (!GetRunScriptVar())
    {
        for (i = 0; i < 12; i++) SetNPCSelectability(i, 1);
        AssignCommand(GetFirstPC(), DelayCommand(1.0, ApplyPair(0)));
        return;
    }
    AssignCommand(GetFirstPC(), DelayCommand(1.5, AfterSecond()));
}
