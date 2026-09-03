// Suppression wrapper for bastila's real story recruitment script
// (originally tar_m03af's k_ptar_bastpart, preserved as apo_bastila_orig).
//
// Runs the real script unchanged, then immediately reverses the
// availability grant with RemoveAvailableNPC so the vanilla unlock never
// actually sticks -- the real grant will come from AP later, through the
// existing companion apply script (phase 06).
//
// GUARD (added 2026-08-31): if NPC_BASTILA is ALREADY available when this
// fires, our own companion_bastila AP arm already ran (early item, or an
// admin re-grant) and bastila is already an active party member. Confirmed
// live: running apo_bastila_orig + RemoveAvailableNPC on an
// already-recruited companion kicks them OUT of the active party --
// RemoveAvailableNPC is not the harmless no-op on an active member that
// the vanilla script assumes. So skip the vanilla script and the
// RemoveAvailableNPC in that case; the AP location check still fires
// either way below, since reaching this trigger is the check regardless
// of whether recruitment logic needs to run.
#include "kse"

void main()
{
    if (!IsAvailableCreature(NPC_BASTILA))
    {
        ExecuteScript("apo_bastila_orig", OBJECT_SELF);
        RemoveAvailableNPC(NPC_BASTILA);
        KSE_Diag(29, "AP|SUPPRESSED|companion_bastila");
    }
    else
    {
        KSE_Diag(29, "AP|SUPPRESSED|companion_bastila|skipped_already_recruited");
    }
    // The check-fire below is atomic with the guard above within this one
    // script call -- no other script (including the regular poll's
    // CheckCompanions()) needs to observe anything here. Report the AP
    // location check directly from here, the only place that reliably
    // knows recruitment was just reached.
    KSE_Diag(22, "AP|CHECK|COMPANION|0");
}
