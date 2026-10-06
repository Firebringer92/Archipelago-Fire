// Suppression wrapper for danm13's k_pdan_addcarth (the Jedi Council
// wrap-up script fired from dan13_vandar's dialogue tree, preserved
// byte-exact as apo_addcarth_orig) -- Carth's counterpart of
// k_pdan_addbast.
//
// The real script makes Carth available (AddAvailableNPCByTemplate), sets
// DAN_CARTH_AT_JEDI/DAN_CARTH_BACKUP and opens the party-selection screen.
// Under companion_mode=ap_gated/none that would hand him over before his AP
// item arrives, so the wrapper lets it run and then takes away the
// availability it added.
//
// GUARD: if NPC_CARTH was ALREADY available, his AP grant already ran and he
// is a legitimate roster member (possibly in the active party). Leave him
// alone: RemoveAvailableNPC on an active member kicks him out of the party.
#include "kse"

void main()
{
    int bWasAvailable = IsAvailableCreature(NPC_CARTH);

    ExecuteScript("apo_addcarth_orig", OBJECT_SELF);

    if (!bWasAvailable)
    {
        RemovePartyMember(NPC_CARTH);
        RemoveAvailableNPC(NPC_CARTH);
        KSE_Diag(28, "AP|SUPPRESSED|companion_carth|council");
    }
}
