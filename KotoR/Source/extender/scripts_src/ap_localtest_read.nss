// Companion to ap_localtest.nss -- re-checks the same local variables on a
// LATER, separate script invocation to test true cross-tick persistence.
#include "kse"

void DoRead()
{
    object oPC = GetFirstPC();
    int nBoolResult = GetLocalBoolean(oPC, 0);
    int nNumResult = GetLocalNumber(oPC, 0);
    KSE_Diag(47, "AP|LOCALTEST|laterTick_bool=" + IntToString(nBoolResult)
        + "|num=" + IntToString(nNumResult));
}

void main()
{
    DelayCommand(1.0, DoRead());
}
