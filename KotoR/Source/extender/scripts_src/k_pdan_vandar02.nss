// Suppression wrapper for juhani's real story recruitment script
// (originally danm13's k_pdan_vandar02, preserved as apo_juhani_orig).
//
// Runs the real script unchanged, then immediately reverses the
// availability grant with RemoveAvailableNPC so the vanilla unlock never
// actually sticks -- the real grant will come from AP later, through the
// existing companion apply script (phase 06).
//
// GUARD: if NPC_JUHANI is ALREADY available when this fires, our own
// companion_juhani AP arm already ran (early item, or an admin re-grant)
// and juhani is already an active party member. Running apo_juhani_orig
// + RemoveAvailableNPC on an already-recruited companion kicks them OUT
// of the active party -- RemoveAvailableNPC is not the harmless no-op on
// an active member that the vanilla script assumes. So skip the vanilla
// script and the
// RemoveAvailableNPC in that case; the AP location check still fires
// either way below, since reaching this trigger is the check regardless
// of whether recruitment logic needs to run.
#include "kse"
#include "ap_recruit_marker"

void main()
{
    if (!IsAvailableCreature(NPC_JUHANI))
    {
        ExecuteScript("apo_juhani_orig", OBJECT_SELF);
        RemoveAvailableNPC(NPC_JUHANI);
        KSE_Diag(31, "AP|SUPPRESSED|companion_juhani");
    }
    else
    {
        KSE_Diag(31, "AP|SUPPRESSED|companion_juhani|skipped_already_recruited");
        SetGlobalBoolean("DAN_JUHANI_JOINED", TRUE);
        object oPlacedJuhani = GetObjectByTag("dan13_juhani");
        if (GetIsObjectValid(oPlacedJuhani)) DestroyObject(oPlacedJuhani);
    }
    // The check-fire below is atomic with the guard above within this one
    // script call -- no other script (including the regular poll's
    // CheckCompanions()) needs to observe anything here. Report the AP
    // location check directly from here, the only place that reliably
    // knows recruitment was just reached. RecordRecruit also writes the
    // persistent journal marker for this recruit (ap_recruit_marker.nss) so
    // the check survives a missed relay.
    RecordRecruit("juhani", 5);
}
