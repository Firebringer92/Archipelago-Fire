// Story gate U2 (Unknown World): the Bastila scene at the temple summit. Condition script for the "not yet" starter that
// scripts/story_gate_dialogs_unknown.py inserts ahead of the existing starters of unk44_evilbast and unk44_evilbast2
// (unk_m44ac). Returns TRUE while the player holds fewer than two Unknown World progression items, which makes the dialog play its
// short "not yet" line and end, whichever way it was started (the cutscene trigger, clicking Bastila, or the fight's
// end); it returns FALSE otherwise, so the vanilla starters are evaluated exactly as before. It changes no state.
#include "ap_gate"

int StartingConditional()
{
    if (ApGateOpen("unk", 2)) return FALSE;
    ApGateMsg("Unknown World", 2);
    return TRUE;
}
