// Story gate Ko1 (Korriban): Yuthura Ban accepts the player into the academy. A new condition with no vanilla
// counterpart (scripts/story_gate_dialogs_korriban.py puts it on the six links that lead into node E16 of kor33_yuthura,
// the node that raises kor33_enteracademy to stage 50). TRUE when the player holds one Korriban progression item. When it is FALSE
// the dialog falls through to the added "not yet" entry, so nothing in the acceptance runs and nothing is latched.
#include "ap_gate"

int StartingConditional()
{
    if (ApGateOpen("kor", 1)) return TRUE;
    ApGateMsg("Korriban", 1);
    return FALSE;
}
