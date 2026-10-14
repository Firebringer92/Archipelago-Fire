// Gate M1 "not yet" starter (Manaan, Republic embassy): placed FIRST in the starting list of Roland Wann's dialog man26_repdip by
// scripts/story_gate_dialogs_unknown.py. TRUE while the briefing has not happened (MAN_PLANET_PLOT below 2) and the gate would still
// refuse, i.e. the player lacks the Manaan progression item (or the earlier families). Roland then says one "not yet" line and the
// conversation ends before any choice, so none of his branches (the briefing, the offer to interrogate the Sith prisoner, the passcard) can
// start. With the item the dialog is the vanilla one. The two node scripts that set MAN_PLANET_PLOT keep their own gate as a backstop.
#include "ap_gate"

int StartingConditional()
{
    if (GetGlobalNumber("MAN_PLANET_PLOT") >= 2) return FALSE;
    if (ApGateOpen("man", 1)) return FALSE;
    ApGateMsg("Manaan", 1);
    return TRUE;
}
