#include "k2se"
#include "k2se_roster"
// Exit script of the first party selection screen: remember the two picked companions as pool entries 0 and 1, take them out of the
// party and the area, hide them from the next screen, and open the screen again for the standing pair. The exit script has no owning
// object of its own, so every delayed step is scheduled on the player.
void Log(string s)
{
    if (K2SE_IsPresent()) K2SE_Diag("PS1", s);
}

void SecondScreen()
{
    Log("opening the second screen");
    ShowPartySelectionGUI("k2se_ps2", -1, -1, TRUE);
}

void AfterFirst()
{
    int i;
    int n = 0;
    string s = "pool picks:";
    for (i = 0; i < 12; i++)
    {
        if (IsNPCPartyMember(i) && n < 2)
        {
            PoolSet(n, i);
            s = s + " " + SlotName(i);
            n++;
            RemoveNPCFromPartyToBase(i);
            SetNPCSelectability(i, 0);
        }
    }
    Log(s + " (" + IntToString(n) + ")");
    AssignCommand(GetFirstPC(), DelayCommand(1.0, SecondScreen()));
}

void main()
{
    Log("first screen closed, picked=" + IntToString(GetRunScriptVar()));
    if (!GetRunScriptVar())
    {
        int i;
        for (i = 0; i < 12; i++) SetNPCSelectability(i, 1);
        return;
    }
    AssignCommand(GetFirstPC(), DelayCommand(1.5, AfterFirst()));
}
