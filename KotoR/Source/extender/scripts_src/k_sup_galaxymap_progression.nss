// Progression System travel gate -- the vanilla galaxy map
// script (preserved as apo_k_sup_galaxymap_orig) has NO destination
// availability check of its own; every planet is selectable from the
// start (confirmed via full disassembly -- GetSelectedPlanet() is called
// once at the top and stored into K_FUTURE_PLANET, with zero gating on
// the result anywhere else in the script). This wrapper adds one: for
// the 4 planets whose Star Map is a tracked Progression System item
// (Tatooine/Kashyyyk/Manaan/Korriban), block travel until that planet's
// AP check has actually been delivered. Reuses the SAME
// granted_exempt_<resref> flag give_item: delivery already sets
// (generate_trampoline_batch.py's build_give_item_block()) -- no new
// delivery-side plumbing needed.
//
// Planet constants (4/5/6/7 = Tatooine/Kashyyyk/Manaan/Korriban) match
// pykotor's documented PLANET_* nwscript.nss constants, which match
// planetary.2da's row order.
//
// NOT YET LIVE-VERIFIED: whether calling GetSelectedPlanet() a second
// time here is safe -- the delegated original calls it again itself.
// Near-certain (it almost certainly just reads current GUI selection
// state, not a one-shot consumed event), but flagged for a live test
// before shipping.
//
// Checks a LocalBoolean bit on a dedicated marker item
// (ap_progress_marker) instead of the old KSE_HasData("granted_exempt_")
// flag -- that in-DLL store doesn't survive a game restart. LocalBoolean
// on an object is genuinely save-persistent. See
// scripts/generate_trampoline_batch.py's STARPAD_MARKER_BIT for the bit
// assignment (must match) and patch_item_suppression.py's
// PROGRESS_MARKER_RESREF comment for the full reasoning.
#include "kse"

void main()
{
    int nSelected = GetSelectedPlanet();
    int nBit = -1;

    if (nSelected == 4)      nBit = 0; // tat_starpad
    else if (nSelected == 5) nBit = 1; // kas_starpad
    else if (nSelected == 6) nBit = 2; // man_starpad
    else if (nSelected == 7) nBit = 3; // kor_starpad

    if (nBit != -1)
    {
        object oMarker = GetItemPossessedBy(GetFirstPC(), "ap_progress_marker");
        int nGranted = GetIsObjectValid(oMarker) && GetLocalBoolean(oMarker, nBit);
        if (!nGranted)
        {
            KSE_Diag(130, "AP|PROGRESSION_BLOCKED|galaxymap|planet=" + IntToString(nSelected));
            return;
        }
    }

    ExecuteScript("apo_k_sup_galaxymap_orig", OBJECT_SELF);
}
