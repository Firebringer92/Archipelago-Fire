// Progression System star-map completion-flag safety net (2026-09-08).
// Layered UNDERNEATH the k_sup_galaxymap travel gate -- a player should
// never physically reach one of these 4 planets before earning its Star
// Map check, but this blocks the actual completion flag too, in case
// some other path onto the planet exists that the travel gate doesn't
// cover (console commands, a future feature, an unrelated bug).
//
// k_pla_actmap is the shared OnUsed script on every star-map hologram
// placeable (k_star_map_01..05, plc_starmap) across every planet. It has
// ZERO item calls anywhere in its own logic -- confirmed via full
// disassembly, it only calls GetModuleFileName() and compares against
// each planet's module name to decide which K_STAR_MAP_<PLANET> global
// boolean to set (and recompute the K_STAR_MAP counter that eventually
// feeds the Leviathan-capture trigger). GetModuleFileName() and the
// exact module-name strings/casing below are copied directly from the
// real original's own disassembly, not guessed.
//
// Vanilla original preserved as apo_k_pla_actmap_orig; delegated to
// unchanged (including its animation/cutscene timing logic, none of
// which this wrapper needs to understand) once the check has been
// granted.
#include "kse"

void main()
{
    string sModule = GetModuleFileName();
    string sFlag = "";

    if (sModule == "manm28ad")        sFlag = "granted_exempt_man_starpad";
    else if (sModule == "korr_m39aa") sFlag = "granted_exempt_kor_starpad";
    else if (sModule == "Kas_m25aa")  sFlag = "granted_exempt_kas_starpad";
    else if (sModule == "Tat_m18ac")  sFlag = "granted_exempt_tat_starpad";

    if (sFlag != "" && !KSE_HasData(sFlag))
    {
        KSE_Diag(131, "AP|PROGRESSION_BLOCKED|actmap|module=" + sModule);
        return;
    }

    ExecuteScript("apo_k_pla_actmap_orig", OBJECT_SELF);
}
