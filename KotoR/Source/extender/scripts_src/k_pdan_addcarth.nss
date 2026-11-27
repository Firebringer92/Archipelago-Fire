// Suppression wrapper for danm13's k_pdan_addcarth (the Jedi Council
// wrap-up script fired from dan13_vandar's dialogue tree, preserved
// byte-exact as apo_addcarth_orig) -- Carth's counterpart of
// k_pdan_addbast.
//
// The real script makes Carth available (AddAvailableNPCByTemplate), sets
// DAN_CARTH_AT_JEDI/DAN_CARTH_BACKUP and opens the party-selection screen.
// Under companion_mode=ap_gated/none that would hand him over before his AP
// item arrives, so the wrapper lets it run and then benches him
//
// GUARD: if NPC_CARTH was ALREADY available, his AP grant already ran and he
// is a legitimate roster member (possibly in the active party). Leave him
// alone: benching an entitled active member would kick him out of the party.
#include "kse"
#include "ap_companion_roster"

void main()
{
    int bWasAvailable = IsAvailableCreature(NPC_CARTH);

    ExecuteScript("apo_addcarth_orig", OBJECT_SELF);

    // Benched whether or not he was already on the roster: the vanilla script puts him in the party and opens the party screen.
    if (!ApNpcEntitled(NPC_CARTH))
    {
        ApBenchNpc(NPC_CARTH);
        KSE_Diag(28, "AP|SUPPRESSED|companion_carth|council|wasAvailable=" + IntToString(bWasAvailable));
    }
}
