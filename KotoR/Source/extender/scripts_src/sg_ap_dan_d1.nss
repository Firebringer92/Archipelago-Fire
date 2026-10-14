// Gate D1 "not yet" starter (Dantooine, Jedi Enclave): placed FIRST in the starting list of Dorak's dialog dan13_dorak by
// scripts/story_gate_dialogs_unknown.py. TRUE only while Zhar has sent the player to Dorak (DAN_DORAK_DONE) and the gate k_pdan_saber01 would
// still refuse, i.e. the player holds too few Dantooine progression items (or the earlier Taris items). Dorak then says one embedded
// "not yet" line and the conversation ends, instead of falling through to his ordinary greeting with no explanation. DAN_DORAK_DONE is left
// as it is, so the real conversation still plays once the progression items have arrived.
#include "ap_gate"

int StartingConditional()
{
    if (!GetGlobalBoolean("DAN_DORAK_DONE")) return FALSE;
    if (ApGateOpen("dan", 1)) return FALSE;
    ApGateMsg("Dantooine", 1);
    return TRUE;
}
