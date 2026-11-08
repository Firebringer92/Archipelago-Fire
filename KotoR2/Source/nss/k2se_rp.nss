#include "k2se"
#include "k2se_roster"
// Roster menu reply "Change who comes along". Clears the current pool, then opens the party selection screen for the first pair
// (the two who fight beside the player); k2se_ps1 then opens it again for the standing pair.
string RpTemplate(int i)
{
    if (i == 0) return "p_atton";
    if (i == 1) return "p_baodur";
    if (i == 2) return "p_mand";
    if (i == 3) return "p_g0t0";
    if (i == 4) return "p_handmaiden";
    if (i == 5) return "p_hk47";
    if (i == 6) return "p_kreia";
    if (i == 7) return "p_mira";
    if (i == 8) return "p_t3m4";
    if (i == 9) return "p_visas";
    if (i == 10) return "p_hanharr";
    return "p_disciple";
}

void main()
{
    int i;
    int k;
    string sBefore = "party members before:";
    for (i = 0; i < 12; i++)
    {
        if (IsNPCPartyMember(i))
        {
            sBefore = sBefore + " " + SlotName(i);
            RemovePartyMember(i);
        }
    }
    if (K2SE_IsPresent()) K2SE_Diag("RP", sBefore + "; party count " + IntToString(GetPartyMemberCount()) + "; player tag " + GetTag(GetFirstPC()));
    for (k = 0; k < 4; k++)
    {
        int s = PoolGet(k);
        if (s >= 0)
        {
            RemoveNPCFromPartyToBase(s);
        }
    }
    PoolClear();
    for (i = 0; i < 12; i++)
    {
        if (!IsAvailableCreature(i)) AddAvailableNPCByTemplate(i, RpTemplate(i));
        SetNPCSelectability(i, 1);
    }
    ShowPartySelectionGUI("k2se_ps1", -1, -1, TRUE);
}
