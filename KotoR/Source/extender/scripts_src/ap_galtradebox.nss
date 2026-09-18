// Galactic Shop container handler (Options.py's GalacticShop) -- the
// OnInvDisturbed script on Override/ap_voidbox.utp, the template
// scripts/patch_galactic_shop.py retargets the Ebon Hawk cargo-hold crates
// (ebo_m12aa) to. Confirmed this exact hook + GetInventoryDisturbItem/GetTag/
// DestroyObject/CreateItemOnObject round trip works.
//
// PROVEN REAL by BioWare's own shipped code before the spike was written:
// korr_m37aa's k_pkor_therangen uses this same pattern on a placeable's
// OnInvDisturbed -- not assumed.
//
// This script deliberately knows NOTHING about the shared pool. Every
// network-facing decision (which other player's item you get, the
// never-your-own-deposit rule, the withdraw race, the empty-pool default)
// lives in KotorClient.py's _galactic_* methods, which react to the two
// KSE_Diag lines below and hand the result back through the ordinary
// give_item grant path (next area transition). The spike's single local
// KSE_SetData "held item" slot is gone -- the server IS the slot now.
//
// KNOWN SIMPLIFICATION, carried over from the spike: base NWScript has no
// GetResRef(object), so GetTag() stands in for the deposited item's
// resref (BioWare's own convention -- their real scripts compare tags
// that are themselves resrefs, just re-cased; CreateItemOnObject's
// lookup is case-insensitive). Correct for every standard item; an item
// with a custom mismatched Tag would come back out as whatever that Tag
// resolves to, or nothing. Not fixed here -- flagged in FutureDesign.md.
#include "kse"

void main()
{
    int nType = GetInventoryDisturbType();
    if (nType != INVENTORY_DISTURB_TYPE_ADDED) return;

    object oItem = GetInventoryDisturbItem();
    if (!GetIsObjectValid(oItem)) return;

    string sTag = GetTag(oItem);
    int nStack = GetItemStackSize(oItem);
    if (nStack < 1) nStack = 1;

    if (sTag == "ap_galcoin")
    {
        // CLAIM: the coin is consumed here and now; what (if anything)
        // comes back is the client's decision, delivered later.
        DestroyObject(oItem);
        KSE_Diag(142, "AP|VOIDTRADE|CLAIM");
        return;
    }

    // DEPOSIT: any other item. Gone from this game the moment it lands in
    // the box; the client records it into the shared pool. The coin is
    // marked granted_exempt so loot_mode=destroy/replace's acquire-time
    // suppression (patch_item_suppression.py) never eats it when the
    // player picks it back out of this container.
    DestroyObject(oItem);
    KSE_SetData("granted_exempt_ap_galcoin", "1");
    CreateItemOnObject("ap_galcoin", OBJECT_SELF, 1);
    KSE_Diag(142, "AP|VOIDTRADE|DEPOSIT|" + sTag + "|" + IntToString(nStack));
}
