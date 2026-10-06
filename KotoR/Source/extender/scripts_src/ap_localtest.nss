// Tests whether per-object local variables (SetLocalBoolean/SetLocalNumber,
// a mechanism architecturally separate from the module-level global table)
// actually persist, unlike SetGlobalBoolean/SetGlobalNumber which were just
// confirmed broken for any name not pre-declared in globalcat.2da.
#include "kse"

void DoTest()
{
    object oPC = GetFirstPC();

    SetLocalBoolean(oPC, 0, TRUE);
    int nBoolResult = GetLocalBoolean(oPC, 0);

    SetLocalNumber(oPC, 0, 12345);
    int nNumResult = GetLocalNumber(oPC, 0);

    KSE_Diag(46, "AP|LOCALTEST|bool=" + IntToString(nBoolResult)
        + "|num=" + IntToString(nNumResult));
}

void main()
{
    DelayCommand(1.0, DoTest());
}
