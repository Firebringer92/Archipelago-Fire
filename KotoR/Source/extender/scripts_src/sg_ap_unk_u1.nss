// Story gate U1 (Unknown World): the temple guide's ritual. Condition script for the "not yet" starter that
// scripts/story_gate_dialogs_unknown.py inserts ahead of the existing starters of unk41_guide_dlg (unk_m41ad), the
// conversation both the Elders' and The One's route end in. Returns TRUE while the player holds fewer than one Unknown
// World progression item, which makes the dialog play its short "not yet" line and end; it returns FALSE otherwise, so the vanilla
// starters are evaluated exactly as before. It changes no state.
#include "ap_gate"

int StartingConditional()
{
    if (ApGateOpen("unk", 1)) return FALSE;
    ApGateMsg("Unknown World", 1);
    return TRUE;
}
