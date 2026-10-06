// Diagnostic: dumps the internal state CheckXP()/CheckQuests() rely on, to
// debug why the XP suppression test isn't behaving as expected.
#include "kse"

void DoVerify()
{
    object oPC = GetFirstPC();
    int nCurrent = GetXP(oPC);
    int nInit = GetGlobalBoolean("AP_XP_BASELINE_INIT");
    int nBaseline = GetGlobalNumber("AP_XP_BASELINE");
    int nFlag = GetGlobalBoolean("DAN_VANDARJ_DONE");
    int nSeen = GetGlobalBoolean("APSEEN_DAN_VANDARJ_DONE");

    KSE_Diag(42, "AP|VERIFYXP|current=" + IntToString(nCurrent)
        + "|baselineInit=" + IntToString(nInit)
        + "|baseline=" + IntToString(nBaseline)
        + "|flag=" + IntToString(nFlag)
        + "|seen=" + IntToString(nSeen));
}

void main()
{
    DelayCommand(1.0, DoVerify());
}
