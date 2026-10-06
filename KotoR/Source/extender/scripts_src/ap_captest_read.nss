// Companion to ap_captest.nss -- re-checks the same 40 globals on a LATER,
// separate script invocation to test true cross-tick persistence (as
// opposed to same-tick read-after-write, which may behave differently).
#include "kse"

void DoRead()
{
    int i;
    int nTotalOk = 0;
    int nFirstFail = 0;
    for (i = 1; i <= 40; i++)
    {
        string sKey = "AP_CAPTEST_" + IntToString(i);
        if (GetGlobalBoolean(sKey))
        {
            nTotalOk++;
        }
        else if (nFirstFail == 0)
        {
            nFirstFail = i;
        }
    }
    KSE_Diag(44, "AP|CAPTEST|laterTick_totalOk=" + IntToString(nTotalOk)
        + "|firstFail=" + IntToString(nFirstFail));
}

void main()
{
    DelayCommand(1.0, DoRead());
}
