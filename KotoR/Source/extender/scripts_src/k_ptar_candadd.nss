// Recruit wrapper for Canderous's real story recruitment script
// (originally tar_m08aa's k_ptar_candadd, preserved as apo_cand_orig).
//
// Runs the real script unchanged (AddAvailableNPCByTemplate + party
// selection GUI + world-object cleanup), then BENCHES him (ApBenchNpc, ap_companion_roster.nss):
// out of the party and not selectable, but still on the roster and in the world. The real grant
// comes from AP later, through the companion_canderous apply script.
//
// GUARD: same fix as k_ptar_addcarth.nss -- if
// NPC_CANDEROUS is ALREADY available when this fires, our own
// companion_canderous AP arm already ran and Canderous is already an
// active party member. Confirmed (on Carth): running the vanilla
// script + RemoveAvailableNPC on an already-recruited companion kicks
// them OUT of the active party. Skip both in that case; the AP location
// check still fires either way below.
#include "kse"
#include "ap_recruit_marker"
#include "ap_companion_roster"

void main()
{
    if (!IsAvailableCreature(NPC_CANDEROUS))
    {
        ExecuteScript("apo_cand_orig", OBJECT_SELF);
        if (!ApNpcEntitled(NPC_CANDEROUS)) ApBenchNpc(NPC_CANDEROUS);
        KSE_Diag(27, "AP|SUPPRESSED|companion_candadd");
    }
    else
    {
        KSE_Diag(27, "AP|SUPPRESSED|companion_candadd|skipped_already_recruited");
    }
    // Same reasoning as k_ptar_addcarth.nss: report the AP check directly
    // from the only place that reliably knows recruitment was just
    // reached, regardless of whether recruitment logic ran above.
    RecordRecruit("canderous", 1);
}
