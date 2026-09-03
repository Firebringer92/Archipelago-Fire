// Suppression wrapper for Canderous's real story recruitment script
// (originally tar_m08aa's k_ptar_candadd, preserved as apo_cand_orig).
//
// Runs the real script unchanged (AddAvailableNPCByTemplate + party
// selection GUI + world-object cleanup), then immediately reverses the
// availability grant with RemoveAvailableNPC so the vanilla unlock never
// actually sticks -- the real grant will come from AP later, through the
// existing companion_canderous apply script (phase 06).
//
// GUARD (added 2026-08-31): same fix as k_ptar_addcarth.nss -- if
// NPC_CANDEROUS is ALREADY available when this fires, our own
// companion_canderous AP arm already ran and Canderous is already an
// active party member. Confirmed live (on Carth): running the vanilla
// script + RemoveAvailableNPC on an already-recruited companion kicks
// them OUT of the active party. Skip both in that case; the AP location
// check still fires either way below.
#include "kse"

void main()
{
    if (!IsAvailableCreature(NPC_CANDEROUS))
    {
        ExecuteScript("apo_cand_orig", OBJECT_SELF);
        RemoveAvailableNPC(NPC_CANDEROUS);
        KSE_Diag(27, "AP|SUPPRESSED|companion_candadd");
    }
    else
    {
        KSE_Diag(27, "AP|SUPPRESSED|companion_candadd|skipped_already_recruited");
    }
    // Same reasoning as k_ptar_addcarth.nss: report the AP check directly
    // from the only place that reliably knows recruitment was just
    // reached, regardless of whether recruitment logic ran above.
    KSE_Diag(22, "AP|CHECK|COMPANION|1");
}
