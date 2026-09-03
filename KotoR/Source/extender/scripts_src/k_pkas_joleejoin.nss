// Suppression wrapper for jolee's real story recruitment script
// (originally kas_m24aa's k_pkas_joleejoin, preserved as apo_jolee_orig).
//
// Runs the real script unchanged, then immediately reverses the
// availability grant with RemoveAvailableNPC so the vanilla unlock never
// actually sticks -- the real grant will come from AP later, through the
// existing companion apply script (phase 06).
//
// GUARD (added 2026-08-31): if NPC_JOLEE is ALREADY available when this
// fires, our own companion_jolee AP arm already ran (early item, or an
// admin re-grant) and jolee is already an active party member. Confirmed
// live: running apo_jolee_orig + RemoveAvailableNPC on an
// already-recruited companion kicks them OUT of the active party --
// RemoveAvailableNPC is not the harmless no-op on an active member that
// the vanilla script assumes. So skip the vanilla script and the
// RemoveAvailableNPC in that case; the AP location check still fires
// either way below, since reaching this trigger is the check regardless
// of whether recruitment logic needs to run.
#include "kse"

void main()
{
    if (!IsAvailableCreature(NPC_JOLEE))
    {
        ExecuteScript("apo_jolee_orig", OBJECT_SELF);
        RemoveAvailableNPC(NPC_JOLEE);
        KSE_Diag(30, "AP|SUPPRESSED|companion_jolee");
    }
    else
    {
        KSE_Diag(30, "AP|SUPPRESSED|companion_jolee|skipped_already_recruited");
    }
    // The check-fire below is atomic with the guard above within this one
    // script call -- no other script (including the regular poll's
    // CheckCompanions()) needs to observe anything here. Report the AP
    // location check directly from here, the only place that reliably
    // knows recruitment was just reached.
    KSE_Diag(22, "AP|CHECK|COMPANION|4");
}
