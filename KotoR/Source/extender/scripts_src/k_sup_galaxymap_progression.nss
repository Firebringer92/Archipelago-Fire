// Progression System travel gate (2026-09-08) -- the vanilla galaxy map
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
#include "kse"

void main()
{
    int nSelected = GetSelectedPlanet();
    string sFlag = "";

    if (nSelected == 4)      sFlag = "granted_exempt_tat_starpad";
    else if (nSelected == 5) sFlag = "granted_exempt_kas_starpad";
    else if (nSelected == 6) sFlag = "granted_exempt_man_starpad";
    else if (nSelected == 7) sFlag = "granted_exempt_kor_starpad";

    if (sFlag != "" && !KSE_HasData(sFlag))
    {
        KSE_Diag(130, "AP|PROGRESSION_BLOCKED|galaxymap|planet=" + IntToString(nSelected));
        return;
    }

    ExecuteScript("apo_k_sup_galaxymap_orig", OBJECT_SELF);
}
