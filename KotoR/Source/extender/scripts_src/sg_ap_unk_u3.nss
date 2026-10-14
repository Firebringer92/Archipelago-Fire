// Story gate U3 (Unknown World): the temple computer. Condition script for the "access denied" starter that
// scripts/story_gate_dialogs_unknown.py inserts ahead of the existing starter of unk44_comp (unk_m44ac), the only
// conversation that runs k_punk_shieldoff and k_punk_disfldoff in that module. Returns TRUE while the player holds fewer
// than three Unknown World progression items, which makes the computer show a denial and log off instead of its command menu; it
// returns FALSE otherwise, so the vanilla menu is unchanged. It changes no state.
#include "ap_gate"

int StartingConditional()
{
    if (ApGateOpen("unk", 3)) return FALSE;
    ApGateMsg("Unknown World", 3);
    return TRUE;
}
