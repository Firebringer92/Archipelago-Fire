// Suppression wrapper for Carth's real story recruitment script
// (originally tar_m02aa's k_ptar_addcarth, preserved as apo_carth_orig).
//
// Runs the real script unchanged (AddAvailableNPCByTemplate), then
// immediately reverses the availability grant with RemoveAvailableNPC so
// the vanilla unlock never actually sticks -- the real grant will come
// from AP later, through the existing companion apply script (phase 06).
//
// GUARD (added 2026-08-31): if NPC_CARTH is ALREADY available when this
// fires, our own companion_carth AP arm already ran (early item, or an
// admin re-grant) and Carth is already an active party member. Confirmed
// live: running apo_carth_orig + RemoveAvailableNPC on an
// already-recruited companion kicks them OUT of the active party --
// RemoveAvailableNPC is not the harmless no-op on an active member that
// the vanilla script assumes. So skip the vanilla script and the
// RemoveAvailableNPC in that case; the AP location check still fires
// either way below, since reaching this trigger is the check regardless
// of whether recruitment logic needs to run.
#include "kse"

void main()
{
    if (!IsAvailableCreature(NPC_CARTH))
    {
        ExecuteScript("apo_carth_orig", OBJECT_SELF);
        RemoveAvailableNPC(NPC_CARTH);
        KSE_Diag(28, "AP|SUPPRESSED|companion_addcarth");
    }
    else
    {
        KSE_Diag(28, "AP|SUPPRESSED|companion_addcarth|skipped_already_recruited");
    }
    // The check-fire below is atomic with the guard above within this one
    // script call -- no other script (including the regular poll's
    // CheckCompanions()) needs to observe anything here. Report the AP
    // location check directly from here, the only place that reliably
    // knows recruitment was just reached.
    KSE_Diag(22, "AP|CHECK|COMPANION|2");
}
