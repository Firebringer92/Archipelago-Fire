// Story gate K3 (Kashyyyk): Chorrawl on the Great Walkway, dialog side. Condition script for the "not yet" starter that
// scripts/story_gate_dialogs_unknown.py inserts ahead of the only starter of kas22_chorraw_02 (kas_m22ab only). Chorrawl's conversation ends in
// k_pkas_backking, which walks the player into the throne room; the throne room's own conversation is held until three Kashyyyk progression items
// are held (sg_k_pkas_freydead2, sg_k_pkas_freyyhelp, sg_k_pkas_freyydead). This returns TRUE while the player holds fewer than three, which makes
// the dialog play one short "not yet" line and end, so the player is not led into a hall whose conversation cannot start; it returns FALSE
// otherwise and the vanilla conversation runs exactly as before. It changes no state, and no movement script is touched (k_pkas_backking stays the
// game's own): the player can walk on the Walkway and use the baskets freely.
#include "ap_gate"

int StartingConditional()
{
    if (ApGateOpen("kas", 3)) return FALSE;
    ApGateMsg("Kashyyyk", 3);
    // After Chorrawl's one line and the end of the conversation the player says the closed-gate line ("I need 3 Kashyyyk Progression items before I
    // can go on."), as for the other gates that sit in a dialog starter.
    ApGateSayLater("Kashyyyk", 3);
    return TRUE;
}
