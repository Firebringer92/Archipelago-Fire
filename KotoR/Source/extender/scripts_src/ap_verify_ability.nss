// Read-only: reports current Charisma without re-granting, so we can check
// whether the permanent ability effect from ap_grant_test_ability survives
// a full process restart (fresh game launch, not just a later poll tick).
#include "kse"

void DoVerify()
{
    object oPC = GetFirstPC();
    int nCurrent = GetAbilityScore(oPC, ABILITY_CHARISMA);
    KSE_Diag(93, "AP|VERIFYABILITY|charisma=" + IntToString(nCurrent));
}

void main()
{
    DelayCommand(1.0, DoVerify());
}
