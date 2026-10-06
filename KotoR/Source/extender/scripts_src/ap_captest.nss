// Diagnostic: finds the engine's cap on custom (non-globalcat.2da) global
// variable names. Sets 40 brand-new boolean globals never referenced
// anywhere else in the project, checks them back IMMEDIATELY (same tick,
// to test whether the cap blocks the write itself or only persistence),
// then logs how many read back TRUE. A second, separate script
// (ap_captest_read.nss) re-checks them on a LATER tick to test true
// cross-invocation persistence.
#include "kse"

void DoTest()
{
    int i;
    int nTotalOk = 0;
    int nFirstFail = 0;
    for (i = 1; i <= 40; i++)
    {
        string sKey = "AP_CAPTEST_" + IntToString(i);
        SetGlobalBoolean(sKey, TRUE);
        if (GetGlobalBoolean(sKey))
        {
            nTotalOk++;
        }
        else if (nFirstFail == 0)
        {
            nFirstFail = i;
        }
    }
    KSE_Diag(43, "AP|CAPTEST|sametick_totalOk=" + IntToString(nTotalOk)
        + "|firstFail=" + IntToString(nFirstFail));
}

void main()
{
    DelayCommand(1.0, DoTest());
}
