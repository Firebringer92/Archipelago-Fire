// Diagnostic-only: isolate whether TakeGoldFromCreature actually works in
// this engine build, since a set_credits downward correction produced no
// change at all (before=after).
#include "kse"

void main()
{
    object oPC = GetFirstPC();
    int nBefore = GetGold(oPC);
    TakeGoldFromCreature(500, oPC, FALSE);
    int nAfterFalse = GetGold(oPC);
    TakeGoldFromCreature(500, oPC, TRUE);
    int nAfterTrue = GetGold(oPC);
    KSE_Diag(110, "AP|TAKEGOLD_TEST|before=" + IntToString(nBefore) +
        "|after_bDestroyFALSE=" + IntToString(nAfterFalse) +
        "|after_bDestroyTRUE=" + IntToString(nAfterTrue));
}
