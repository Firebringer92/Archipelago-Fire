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
//
// Second fix (after a live run where the ending never started): the real script ends by
// starting the Deck 1 conversation (the stand-in Carth's k_sta_carth, whose lines lead to
// the ending cutscenes) from inside the closure it was run through. A conversation start
// reached through ExecuteScript silently fails to queue (see k_ptar_startconv.nss and
// ap_lev_trigger.nss), so with the original run from this wrapper everything else it does
// happened but nobody spoke and the player was left on an empty deck.
//
// The wrapper now starts that conversation itself. A first version did so after a fixed 2 s
// and the game crashed: the conversation has lines spoken by sta_carth AND sta_bastila (and
// an invisible target), and creatures created by a script appear a few seconds late. So the
// speakers are made sure of first (the stand-in Carth at sta_way_carth, Bastila at
// sta_way_bastend when she was saved, each only if the original did not produce them), and the
// conversation starts well after, from a DelayCommand placed directly in main() -- the form
// the other scenes use (ap_lev_use.nss).
#include "kse"

void StageDeckSpeaker(string sTag, string sWaypointTag)
{
    if (GetIsObjectValid(GetObjectByTag(sTag))) return;
    object oWp = GetObjectByTag(sWaypointTag);
    if (!GetIsObjectValid(oWp)) return;
    CreateObject(OBJECT_TYPE_CREATURE, sTag, GetLocation(oWp), TRUE);
}

void StageDeckSpeakers()
{
    int bNeedBast = GetGlobalBoolean("K_PSTA_BASTSAVE");
    StageDeckSpeaker("sta_carth", "sta_way_carth");
    if (bNeedBast) StageDeckSpeaker("sta_bastila", "sta_way_bastend");
    // Bastila is staged ONLY when the game's own flag says she was saved. If she was not (she
    // died or left), the conversation's saved-only lines are skipped by their own conditions, as
    // in the vanilla game, and nobody is created for her.
    object oBast = GetObjectByTag("sta_bastila");
    KSE_Diag(163, "AP|SAFEGUARD|sta45_end_speakers|carth=" + IntToString(GetIsObjectValid(GetObjectByTag("sta_carth")))
        + "|bastila=" + IntToString(GetIsObjectValid(oBast))
        + "|bastila_dead=" + IntToString(GetIsObjectValid(oBast) && GetIsDead(oBast))
        + "|bastsave=" + IntToString(bNeedBast)
        + "|fc=" + IntToString(GetGlobalNumber("G_FinalChoice"))
        + "|bastila_in_party=" + IntToString(IsNPCPartyMember(NPC_BASTILA)));
}

void main()
{
    if (!IsAvailableCreature(NPC_CARTH))
    {
        AddAvailableNPCByTemplate(NPC_CARTH, "p_carth");
    }
    ExecuteScript("apo_stainit_cart_orig", OBJECT_SELF);
    KSE_Diag(161, "AP|SAFEGUARD|sta45_init_carth");

    // Only on the pass in which the original does its work: the player entering after Malak's
    // death, before it has marked the scene done.
    if (GetIsPC(GetEnteringObject()) && GetGlobalBoolean("STA_MALAK_DEAD") && !GetLocalBoolean(OBJECT_SELF, 11))
    {
        SetLocalBoolean(OBJECT_SELF, 11, TRUE);
        DelayCommand(2.0, StageDeckSpeakers());
        DelayCommand(9.0, AssignCommand(GetObjectByTag("sta_carth"),
            ActionStartConversation(GetFirstPC(), "", FALSE, CONVERSATION_TYPE_CINEMATIC, TRUE)));
    }
}
