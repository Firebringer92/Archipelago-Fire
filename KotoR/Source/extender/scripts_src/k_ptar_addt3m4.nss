// Recruit wrapper for t3m4's real story recruitment script
// (originally tar_m02ab's k_ptar_addt3m4, preserved as apo_t3m4_orig).
//
// Runs the real script unchanged, then BENCHES the companion (ApBenchNpc in
// ap_companion_roster.nss): out of the party and not selectable, but still on
// the roster and still existing in the world, exactly like Zaalbar during the
// Kashyyyk story. The real grant (selectable, in the party) comes from AP
// later, through the companion apply script (DtArm_companion_t3m4).
//
// GUARD: if NPC_T3_M4 is ALREADY available when this fires, either our own
// companion_t3m4 AP arm already ran (early item, or an admin re-grant) or
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
    if (!IsAvailableCreature(NPC_T3_M4))
    {
        ExecuteScript("apo_t3m4_orig", OBJECT_SELF);
        if (!ApNpcEntitled(NPC_T3_M4)) ApBenchNpc(NPC_T3_M4);
        KSE_Diag(33, "AP|SUPPRESSED|companion_t3m4");
    }
    else
    {
        KSE_Diag(33, "AP|SUPPRESSED|companion_t3m4|skipped_already_recruited");
        SetGlobalNumber("Tar_JaniceDro", 30);
    }
    // The check-fire below is atomic with the guard above within this one
    // script call -- no other script (including the regular poll's
    // CheckCompanions()) needs to observe anything here. Report the AP
    // location check directly from here, the only place that reliably
    // knows recruitment was just reached. RecordRecruit also writes the
    // persistent journal marker for this recruit (ap_recruit_marker.nss) so
    // the check survives a missed relay.
    RecordRecruit("t3m4", 7);
}
