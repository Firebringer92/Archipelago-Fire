// k2ap_craft.nss -- the Crafting Console (include file; docs/FIRST_RUN_BUILD_PLAN.md section 23).
//
// With crafting mode or crafting gating on, the player carries the Crafting Console (item k2se_craft, built by tools/build_craft_console.py): using it opens the
// menu of the workbench, the upgrade screen and the chemical lab, each shown only while the seed allows it (nss/k2se_cok_*.nss). It is never used up; if it is lost
// (sold, dropped, a trap) the next calm tick gives it back.

#include "k2ap_gate"

void K2AP_CraftEnsure(object oPC)
{
    if (K2AP_Patched() == 0) return;
    if (K2AP_CraftingMode() == 0 && K2AP_CraftingGated() == 0) return;
    if (GetIsObjectValid(GetItemPossessedBy(oPC, "k2se_craft"))) return;
    if (GetIsObjectValid(CreateItemOnObject("k2se_craft", oPC, 1, 1))) K2AP_Trace("craft", "the Crafting Console was given");
}
