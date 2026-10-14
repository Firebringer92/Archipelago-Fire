// Gate Ko1 "not yet" starter (Korriban, Dreshdae): placed FIRST in the starting list of Yuthura Ban's dialog kor33_yuthura by
// scripts/story_gate_dialogs_korriban.py. TRUE while the player has not been accepted into the academy (journal kor33_enteracademy
// below 50) and the gate ap_kor_ko1 would still refuse, i.e. the player lacks the Korriban progression item (or the earlier
// families). Yuthura then says one "not yet" line and the conversation ends before any choice, so no persuade roll,
// medallion line or alignment shift is used up. With the item the dialog is the vanilla one. The six links into her acceptance keep
// their own gate as a backstop.
#include "ap_gate"

int StartingConditional()
{
    if (GetJournalEntry("kor33_enteracademy") >= 50) return FALSE;
    if (ApGateOpen("kor", 1)) return FALSE;
    ApGateMsg("Korriban", 1);
    return TRUE;
}
