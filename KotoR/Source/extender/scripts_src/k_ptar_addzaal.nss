// Recruit wrapper for zaalbar's real story recruitment script
// (originally tar_m05aa's k_ptar_addzaal, preserved as apo_zaalbar_orig).
//
// Runs the real script unchanged, then BENCHES the companion (ApBenchNpc in
// ap_companion_roster.nss): out of the party and not selectable, but still on
// the roster and still existing in the world, exactly like Zaalbar during the
// Kashyyyk story. The real grant (selectable, in the party) comes from AP
// later, through the companion apply script (DtArm_companion_zaalbar).
//
// GUARD: if NPC_ZAALBAR is ALREADY available when this fires, either our own
// companion_zaalbar AP arm already ran (early item, or an admin re-grant) or
// this recruit already happened and the companion is benched. Running the
// vanilla script again could put them into the party, so it is skipped in
// that case; the AP location check still fires either way below, since
// reaching this trigger is the check regardless of whether recruitment logic
// needs to run.
#include "kse"
#include "ap_recruit_marker"
#include "ap_companion_roster"
#include "ap_zaal_mission"

void main()
{
    if (!IsAvailableCreature(NPC_ZAALBAR))
    {
        ExecuteScript("apo_zaalbar_orig", OBJECT_SELF);
        if (!ApNpcEntitled(NPC_ZAALBAR)) ApBenchNpc(NPC_ZAALBAR);
        KSE_Diag(35, "AP|SUPPRESSED|companion_zaalbar");
    }
    else
    {
        KSE_Diag(35, "AP|SUPPRESSED|companion_zaalbar|skipped_already_recruited");
        SetAreaUnescapable(FALSE);
    }
    // The check-fire below is atomic with the guard above within this one
    // script call -- no other script (including the regular poll's
    // CheckCompanions()) needs to observe anything here. Report the AP
    // location check directly from here, the only place that reliably
    // knows recruitment was just reached. RecordRecruit also writes the
    // persistent journal marker for this recruit (ap_recruit_marker.nss) so
    // the check survives a missed relay.
    RecordRecruit("zaalbar", 8);
    ZaalbarSceneComplete();
}
