// Store-open marker wrapper for k_ptat_fazzastor (module tat_m17ad).
// Not a suppression -- there's nothing to reverse here. Runs the real
// script unchanged (opens the store UI), then reports a credits snapshot
// so the AP client can later correlate "new item + credits dropped since
// this marker" with the next poll's inventory report to infer a purchase
// vs. suppressible loot. See AP_WORLD_NOTES.md.
#include "kse"

void main()
{
    ExecuteScript("apo_st27", OBJECT_SELF);
    object oPC = GetFirstPC();
    KSE_Diag(77, "AP|STOREOPENED|k_ptat_fazzastor|credits=" + IntToString(GetGold(oPC)));
}
