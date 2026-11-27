// Recruit wrapper for jolee's real story recruitment script
// (originally kas_m24aa's k_pkas_joleejoin, preserved as apo_jolee_orig).
//
// Runs the real script unchanged, then BENCHES the companion (ApBenchNpc in
// ap_companion_roster.nss): out of the party and not selectable, but still on
// the roster and still existing in the world, exactly like Zaalbar during the
// Kashyyyk story. The real grant (selectable, in the party) comes from AP
// later, through the companion apply script (DtArm_companion_jolee).
//
// GUARD: if NPC_JOLEE is ALREADY available when this fires, either our own
// companion_jolee AP arm already ran (early item, or an admin re-grant) or
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
    if (!IsAvailableCreature(NPC_JOLEE))
    {
        SetGlobalBoolean("G_JoleeJoined", TRUE);
        DelayCommand(1.0, DestroyObject(OBJECT_SELF));
        if (!ApNpcEntitled(NPC_JOLEE)) ApBenchNpc(NPC_JOLEE);
        KSE_Diag(30, "AP|SUPPRESSED|companion_jolee");
    }
    else
    {
        KSE_Diag(30, "AP|SUPPRESSED|companion_jolee|skipped_already_recruited");
        SetGlobalBoolean("G_JoleeJoined", TRUE);
        DelayCommand(1.0, DestroyObject(OBJECT_SELF));
    }
    // The check-fire below is atomic with the guard above within this one
    // script call -- no other script (including the regular poll's
    // CheckCompanions()) needs to observe anything here. Report the AP
    // location check directly from here, the only place that reliably
    // knows recruitment was just reached. RecordRecruit also writes the
    // persistent journal marker for this recruit (ap_recruit_marker.nss) so
    // the check survives a missed relay.
    RecordRecruit("jolee", 4);
}
