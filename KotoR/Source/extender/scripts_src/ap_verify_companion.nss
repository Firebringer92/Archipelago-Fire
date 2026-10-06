// Diagnostic -- checks class positions 0, 1, AND 2 on the first companion,
// to see whether AddMultiClass actually created a new class slot even
// though it reports 0 levels in it (matching how the player case needed
// ShowLevelUpGUI to actually spend the first level).
#include "kse"

void DoVerify()
{
    object oTarget = GetPartyMemberByIndex(1);
    int nValid = GetIsObjectValid(oTarget);

    int nClass0 = GetClassByPosition(0, oTarget);
    int nLevel0 = GetLevelByPosition(0, oTarget);
    int nClass1 = GetClassByPosition(1, oTarget);
    int nLevel1 = GetLevelByPosition(1, oTarget);
    int nClass2 = GetClassByPosition(2, oTarget);
    int nLevel2 = GetLevelByPosition(2, oTarget);

    int nHD = GetHitDice(oTarget);

    KSE_Diag(11, "AP|VERIFYCOMPANION|valid=" + IntToString(nValid)
        + "|class0=" + IntToString(nClass0) + "@" + IntToString(nLevel0)
        + "|class1=" + IntToString(nClass1) + "@" + IntToString(nLevel1)
        + "|class2=" + IntToString(nClass2) + "@" + IntToString(nLevel2)
        + "|hd=" + IntToString(nHD));
}

void main()
{
    DelayCommand(3.0, DoVerify());
}
