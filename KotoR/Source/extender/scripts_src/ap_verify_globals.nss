// Diagnostic -- reads back AP_AREA_HINT and AP_LAST_AREA directly to debug
// why area checks aren't firing even though companion checks are.
#include "kse"

void DoVerify()
{
    string sHint = GetGlobalString("AP_AREA_HINT");
    string sLast = GetGlobalString("AP_LAST_AREA");
    object oPC = GetFirstPC();
    object oArea = GetArea(oPC);
    string sRealTag = GetTag(oArea);

    KSE_Diag(23, "AP|VERIFYGLOBALS|hint=[" + sHint + "]|last=[" + sLast + "]|realtag=[" + sRealTag + "]");
}

void main()
{
    DelayCommand(3.0, DoVerify());
}
