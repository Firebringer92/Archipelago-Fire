// Test-only: grants one item from each category we care about for
// inventory-reporting tests -- a stackable consumable (Medpac), a weapon
// (Lightsaber), and armor (Combat Suit). Not part of the shipping mod.
#include "kse"

void DoApply()
{
    object oPC = GetFirstPC();

    object oMedpac = CreateItemOnObject("g_i_medeqpmnt01", oPC, 3);
    object oSaber = CreateItemOnObject("g_w_lghtsbr01", oPC, 1);
    object oArmor = CreateItemOnObject("g_a_class4001", oPC, 1);

    KSE_Diag(90, "AP|TESTPREP|grant_test_items|medpac="
        + IntToString(GetIsObjectValid(oMedpac)) + "|saber="
        + IntToString(GetIsObjectValid(oSaber)) + "|armor="
        + IntToString(GetIsObjectValid(oArmor)));
}

void main()
{
    DelayCommand(3.0, DoApply());
}
