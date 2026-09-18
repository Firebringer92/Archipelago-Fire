// Crash-prevention wrapper for the Star Forge trigger `k45_init_carth`'s
// real OnEnter script (originally sta_m45aa's k_psta_init_cart,
// preserved byte-exact as apo_stainit_cart_orig).
//
// Same bug class as the already-fixed Unknown World finale
// (k_punk_41aa_en): the real script calls SpawnAvailableNPC(NPC_CARTH,
// ...) with NO IsAvailableCreature/IsNPCPartyMember guard anywhere in
// its 548 instructions (confirmed via disassembly -- routine 698,
// SpawnAvailableNPC, appears exactly once, and neither routine 696
// (IsAvailableCreature) nor 699 (IsNPCPartyMember) appears at all).
// SpawnAvailableNPC assumes AddAvailableNPCByTemplate already ran; on a
// companion that never was, it's a genuine engine-level crash, not a
// graceful no-op. The call is gated on GetGlobalNumber("G_FinalChoice")
// == 2, one of several mutually exclusive Malak-confrontation ending
// variants (set elsewhere in the endgame dialogue chain, not by this
// script) -- so this isn't unconditional on every playthrough, but that
// branch is a real, reachable ending, and this trigger sits on Star
// Forge, the one area with no way around it. Under companion_mode=none,
// or ap_gated with Carth's item still outstanding this late, landing in
// that branch after stepping on this trigger crashes the game.
//
// Fix: same backfill-only pattern as k_punk_41aa_en -- ensure Carth is
// AddAvailableNPCByTemplate-initialized before handing off to the real
// script, nothing else. No AddPartyMember/CreateObject here: unlike the
// Taris Hideout fix, this script's own job (once its gate passes) IS the
// spawn -- backfilling only the availability flag lets the real,
// preserved SpawnAvailableNPC call do the actual creation exactly as
// vanilla intended, with no risk of a duplicate actor.
#include "kse"

void main()
{
    if (!IsAvailableCreature(NPC_CARTH))
    {
        AddAvailableNPCByTemplate(NPC_CARTH, "p_carth");
    }
    ExecuteScript("apo_stainit_cart_orig", OBJECT_SELF);
    KSE_Diag(161, "AP|SAFEGUARD|sta45_init_carth");
}
