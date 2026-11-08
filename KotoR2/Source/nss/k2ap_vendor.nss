// k2ap_vendor.nss -- the Archipelago Vendor on the Ebon Hawk (include file; docs/FIRST_RUN_BUILD_PLAN.md section 25).
//
// A trader in the cargo hold of the free-roam Hawk (003EBO), next to the Bazaar's Jawa. Four menus, each hidden until its pass item (ap_vp_<key>, given when the
// multiworld item arrives) is held:
//   skill     one rank in a skill for credits, five times in all           (receipts: ap_vd_skill, one per purchase)
//   abil      one point in an ability for credits, five times in all       (receipts: ap_vd_abil)
//   align     ten alignment points toward the dark side for credits paid to you, or toward the light side for credits, without limit
//   supply    bundles of Components or Chemicals for credits, without limit (only offered when the seed has a crafting mode)
// Receipts are plot items, so a purchase count is the number held and a loaded older save simply holds fewer. All numbers are those of data/vendor.json.

#include "k2ap_bazaar"

// ---- the Vendor on the Hawk: put into 003EBO when the seed has the vendor on (called from the dispatcher's tick)
void K2AP_VendorEnsure(object oPC)
{
    if (K2AP_Patched() == 0 || K2SE_ConfigInt("ap_archipelago_vendor", 0) == 0) return;
    if (GetStringLowerCase(GetModuleName()) != "003ebo") return;
    if (GetIsObjectValid(GetObjectByTag("apvendor"))) return;
    object oSpot = GetObjectByTag("WP_cargo");
    if (!GetIsObjectValid(oSpot)) return;
    location lSpot = GetLocation(oSpot);
    vector vAt = GetPositionFromLocation(lSpot);
    vAt.x = vAt.x + 1.8;
    location lAt = Location(vAt, GetFacingFromLocation(lSpot));          // a location holds no area in this game: the object is made in the area of the script's owner, the Hawk
    object oVendor = CreateObject(OBJECT_TYPE_CREATURE, "apvendor", lAt);
    if (GetIsObjectValid(oVendor)) K2AP_Trace("vendor", "the Vendor is on the Hawk");
    else K2AP_Trace("vendor", "the Vendor could not be created");
}
