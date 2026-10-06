// TEMPORARY (loot-window memory-hunting research) -- A/B
// diagnostic: wired onto metalbox001.utp's OnInvDisturbed field (was
// empty) to isolate whether partpile001's OnInvDisturbed silence is
// template-specific or area-specific (end_m01aa). metalbox001 is the
// SAME template ap_voidbox (Galactic Shop, confirmed working) was
// cloned from, and is ALSO placed in end_m01aa (the "Metal Box" near the
// Parts Pile). Real, noted difference from partpile001: PartyInteract=1
// here vs 0 there (matches ap_voidbox's PartyInteract=1 too) -- a real
// candidate explanation if this fires and partpile001 doesn't.
// SCOPE WARNING: metalbox001 is a shared template reused in ~15 modules
// game-wide -- this temporarily affects every metal box in the game.
// Safe for now since the player cannot leave the Endar Spire (no Taris
// transition yet) to reach another one during this test. REVERT after.
#include "kse"

void main()
{
    int nType = GetInventoryDisturbType();
    string sType = (nType == INVENTORY_DISTURB_TYPE_ADDED) ? "ADDED" : "REMOVED";
    KSE_Diag(158, "AP|APPLIED|ap_mb001_dist|METALBOX_DISTURBED|" + sType);
    // Resolve the DISTURBED ITEM itself, not the container -- untried angle:
    // if items are stored as a linked list (each pointing to its sibling)
    // rather than the container holding a flat array, that pointer would
    // live on the item's own struct, not the container's.
    object oItem = GetInventoryDisturbItem();
    KSE_ResolveItemId(oItem, 0, 0);
}
