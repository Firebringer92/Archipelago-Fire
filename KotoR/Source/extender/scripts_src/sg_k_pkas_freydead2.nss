// Story gate K3 (Kashyyyk): Chuundar's confrontation, the "Freyyr was helped and then died" ending. Replaces the vanilla
// condition k_pkas_freydead2 (kas_m23ad only, used only in kas23_chuunda_01: the first starter plus two links inside the
// dialog that are reached only after it has started). Vanilla body: kas_FreyyrDead and kas_HelpedFreyyr are both set; the
// starter then plays Chuundar's closing scene (kas23_mainwookplot 140). The gate adds "holds three Kashyyyk progression items".
// Without them Chuundar does not speak and the scene waits; nothing is consumed. Sibling gates cover the other two ways
// into the same conversation: sg_k_pkas_freyyhelp, sg_k_pkas_freyydead and the trigger wrapper sg_k_pkas_chuuntrig.
// This is evaluated first, so it is the one that shows the message when both globals are set.
#include "ap_gate"

int StartingConditional()
{
    if (GetGlobalBoolean("kas_FreyyrDead") != TRUE) return FALSE;
    if (GetGlobalBoolean("kas_HelpedFreyyr") != TRUE) return FALSE;
    if (!ApGateOpen("kas", 3))
    {
        ApGateMsg("Kashyyyk", 3);
        ApGateSayLater("Kashyyyk", 3);
        return FALSE;
    }
    return TRUE;
}
