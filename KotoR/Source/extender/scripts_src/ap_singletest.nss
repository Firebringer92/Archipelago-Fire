// Minimal diagnostic: sets ONE brand-new custom global using a static
// string literal (no loop, no runtime concatenation) and reads it back
// immediately, to isolate whether ANY new custom global can still be
// created, independent of the captest loop/concatenation, on a save
// with minimal prior custom-global history.
#include "kse"

void DoTest()
{
    SetGlobalBoolean("AP_SINGLETEST", TRUE);
    int nResult = GetGlobalBoolean("AP_SINGLETEST");
    KSE_Diag(45, "AP|SINGLETEST|result=" + IntToString(nResult));
}

void main()
{
    DelayCommand(1.0, DoTest());
}
