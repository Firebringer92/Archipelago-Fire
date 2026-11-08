#include "k2se"
// Exit script of the party selection screen opened from the roster menu: log who is in the party and how many creatures
// exist per companion tag, to see whether picking made duplicates.
void main()
{
    object oPC = GetFirstPC();
    string s = "selection closed, cancelled=" + IntToString(!GetRunScriptVar()) + ", members:";
    int i;
    for (i = 0; i < 12; i++)
    {
        if (IsNPCPartyMember(i)) s = s + " " + IntToString(i);
    }
    s = s + " | active by index:";
    for (i = 0; i < 5; i++) s = s + " " + IntToString(i) + "=" + GetTag(GetPartyMemberByIndex(i));
    string tags = "carth bastila hanharr mira";
    s = s + " | creatures near the player: ";
    string t1 = "carth"; int n1 = 0; while (GetIsObjectValid(GetNearestObjectByTag(t1, oPC, n1 + 1))) n1++;
    string t2 = "bastila"; int n2 = 0; while (GetIsObjectValid(GetNearestObjectByTag(t2, oPC, n2 + 1))) n2++;
    string t3 = "hanharr"; int n3 = 0; while (GetIsObjectValid(GetNearestObjectByTag(t3, oPC, n3 + 1))) n3++;
    string t4 = "mira"; int n4 = 0; while (GetIsObjectValid(GetNearestObjectByTag(t4, oPC, n4 + 1))) n4++;
    s = s + "carth " + IntToString(n1) + ", bastila " + IntToString(n2) + ", hanharr " + IntToString(n3) + ", mira " + IntToString(n4);
    if (K2SE_IsPresent()) K2SE_Diag("PS", s);
}
