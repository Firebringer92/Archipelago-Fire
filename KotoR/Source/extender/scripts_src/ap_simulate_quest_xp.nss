// Test-only: simulates a quest completion that ALSO grants story XP, exactly
// as a real quest-completion script would (flag flip + GiveXPToCreature in
// the same moment). Used to prove ap_poll_shared's XP-suppression logic:
// the next poll tick should see both events together and revert the XP.
#include "kse"

void DoApply()
{
    object oPC = GetFirstPC();
    int nBefore = GetXP(oPC);

    GiveXPToCreature(oPC, 250);
    SetGlobalBoolean("DAN_VANDARJ_DONE", TRUE);

    int nAfter = GetXP(oPC);
    KSE_Diag(41, "AP|APPLIED|simulate_quest_xp|before=" + IntToString(nBefore) + "|after=" + IntToString(nAfter));
}

void main()
{
    DelayCommand(3.0, DoApply());
}
