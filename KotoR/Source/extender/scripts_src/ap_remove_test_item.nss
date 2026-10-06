// Test-only: proves the actual item-removal mechanism works, ahead of real
// AP client integration. Finds the test lightsaber (g_w_lghtsbr01) in the
// backpack and destroys it. Stops advancing the iterator once found/
// destroyed, rather than calling GetNextItemInInventory afterward, to avoid
// mutating the inventory list mid-walk.
#include "kse"

void DoApply()
{
    object oPC = GetFirstPC();
    object oItem = GetFirstItemInInventory(oPC);
    int nRemoved = FALSE;
    while (GetIsObjectValid(oItem) && !nRemoved)
    {
        if (GetTag(oItem) == "g_w_lghtsbr01")
        {
            DestroyObject(oItem);
            nRemoved = TRUE;
        }
        else
        {
            oItem = GetNextItemInInventory(oPC);
        }
    }
    KSE_Diag(91, "AP|TESTPREP|remove_test_item|removed=" + IntToString(nRemoved));
}

void main()
{
    DelayCommand(3.0, DoApply());
}
