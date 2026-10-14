// Story gate D2 (Dantooine): the Juhani confrontation, dialog side. Condition script for the "not yet" starter that
// scripts/story_gate_dialogs_unknown.py inserts ahead of the existing starters of dan14_juhani (danm14ac only). Returns TRUE
// while the player holds fewer than two Dantooine progression items, which makes the dialog play one short "not yet" line and end, whichever
// way it was started (the cutscene trigger or clicking Juhani); it returns FALSE otherwise, so the vanilla starters are evaluated
// exactly as before. It changes no state.
//
// The cutscene trigger's own script (k_pdan_juhani27) is not wrapped: it starts a conversation, and a conversation started from a
// script reached through ExecuteScript does not start, so a wrapper would silence the scene even with the progression items.
#include "ap_gate"

int StartingConditional()
{
    if (ApGateOpen("dan", 2)) return FALSE;
    ApGateMsg("Dantooine", 2);
    return TRUE;
}
