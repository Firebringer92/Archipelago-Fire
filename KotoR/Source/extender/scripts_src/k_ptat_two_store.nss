// Store-open marker wrapper for k_ptat_two_store (module tat_m17ab).
// Not a suppression -- there's nothing to reverse here. Runs the real
// script unchanged (opens the store UI), then reports a credits snapshot
// so the AP client can later correlate "new item + credits dropped since
// this marker" with the next poll's inventory report to infer a purchase
// vs. suppressible loot. See AP_WORLD_NOTES.md.
#include "kse"

void main()
{
    ExecuteScript("apo_st25", OBJECT_SELF);
    object oPC = GetFirstPC();
    KSE_Diag(75, "AP|STOREOPENED|k_ptat_two_store|credits=" + IntToString(GetGold(oPC)));
}
