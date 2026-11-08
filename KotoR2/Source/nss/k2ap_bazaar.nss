// k2ap_bazaar.nss -- the Archipelago Bazaar: a Jawa trader on the Ebon Hawk (include file; docs/FIRST_RUN_BUILD_PLAN.md section 18).
//
// The Jawa gives the player a CHECK, never an item (the design of the KotOR 1 Bazaar):
//   * five purchases for credits, each dearer than the last (1,000 and then 2,000 more each time); a purchase gives the plot item ap_bz_buy;
//   * twenty token exchanges, five Bazaar tokens (ap_bz_token) for one; an exchange gives the plot item ap_bz_swap;
//   * the number of receipts the player holds is the number of deals done, so the state lives in the save (a loaded older save simply holds fewer receipts) and the
//     client credits the checks by count: the poll reports B|<purchases>|<exchanges> (tools/generate_poll.py PollBazaar).
// The hundred tokens sit in the module files' containers, placed by the client when it patches the game (client/k2_bazaar_tokens.py), not by a script.
// All prices and counts below are those of data/bazaar.json (a test compares them).

#include "k2ap_gate"

int K2AP_Held(object oPC, string sTag)
{
    int nHeld = 0;
    object oItem = GetFirstItemInInventory(oPC);
    while (GetIsObjectValid(oItem))
    {
        if (GetTag(oItem) == sTag) nHeld += GetItemStackSize(oItem);
        oItem = GetNextItemInInventory(oPC);
    }
    return nHeld;
}

int K2AP_BazaarPrice(int nBought)
{
    return 1000 + 2000 * nBought;
}

// ---- the Jawa on the Ebon Hawk: put into the main Hawk module when the seed has the Bazaar on (called from the dispatcher's tick)
void K2AP_BazaarEnsure(object oPC)
{
    if (K2AP_Patched() == 0 || K2AP_Bazaar() == 0) return;
    if (GetStringLowerCase(GetModuleName()) != "003ebo") return;
    if (GetIsObjectValid(GetObjectByTag("apjawa"))) return;
    object oSpot = GetObjectByTag("WP_cargo");
    if (!GetIsObjectValid(oSpot)) return;
    object oJawa = CreateObject(OBJECT_TYPE_CREATURE, "apjawa", GetLocation(oSpot));
    if (GetIsObjectValid(oJawa)) K2AP_Trace("bazaar", "the Jawa is on the Hawk");
    else K2AP_Trace("bazaar", "the Jawa could not be created");
}
