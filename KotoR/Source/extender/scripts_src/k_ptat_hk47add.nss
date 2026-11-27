// Recruit wrapper for hk47's real story recruitment script
// (originally tat_m17ac's k_ptat_hk47add, preserved as apo_hk47_orig).
//
// Runs the real script unchanged, then BENCHES the companion (ApBenchNpc in
// ap_companion_roster.nss): out of the party and not selectable, but still on
// the roster and still existing in the world, exactly like Zaalbar during the
// Kashyyyk story. The real grant (selectable, in the party) comes from AP
// later, through the companion apply script (DtArm_companion_hk47).
//
// GUARD: if NPC_HK_47 is ALREADY available when this fires, either our own
// companion_hk47 AP arm already ran (early item, or an admin re-grant) or
// this recruit already happened and the companion is benched. Running the
// vanilla script again could put them into the party, so it is skipped in
// that case; the AP location check still fires either way below, since
// reaching this trigger is the check regardless of whether recruitment logic
// needs to run.
#include "kse"
#include "ap_recruit_marker"
#include "ap_companion_roster"

void main()
{
    if (!IsAvailableCreature(NPC_HK_47))
    {
        ExecuteScript("apo_hk47_orig", OBJECT_SELF);
        if (!ApNpcEntitled(NPC_HK_47)) ApBenchNpc(NPC_HK_47);
        KSE_Diag(34, "AP|SUPPRESSED|companion_hk47");
    }
    else
    {
        KSE_Diag(34, "AP|SUPPRESSED|companion_hk47|skipped_already_recruited");
    }
    // The check-fire below is atomic with the guard above within this one
    // script call -- no other script (including the regular poll's
    // CheckCompanions()) needs to observe anything here. Report the AP
    // location check directly from here, the only place that reliably
    // knows recruitment was just reached. RecordRecruit also writes the
    // persistent journal marker for this recruit (ap_recruit_marker.nss) so
    // the check survives a missed relay.
    RecordRecruit("hk47", 3);
}
