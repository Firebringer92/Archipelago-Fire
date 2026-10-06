// Sets XP to an unusual, specific decimal value (654321) instead of adding a
// round number -- a value like this is very unlikely to coincidentally
// appear as padding/timer/size data elsewhere in the process, unlike 500
// which collided with several unrelated tables during memory scanning.
#include "kse"

void DoApply()
{
    object oPC = GetFirstPC();
    int nBefore = GetXP(oPC);

    SetXP(oPC, 654321);

    int nAfter = GetXP(oPC);
    KSE_Diag(8, "AP|APPLIED|xp_marker|before=" + IntToString(nBefore) + "|after=" + IntToString(nAfter));
}

void main()
{
    DelayCommand(3.0, DoApply());
}
