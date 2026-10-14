// Story gate K1 (Kashyyyk), second entrance: Jolee's first conversation when the poachers are already gone. Replaces the
// vanilla condition k_pkas_poachover (kas_m24aa only, used once: the link from Jolee's briefing node into the node that
// says the task is already done and then continues into the same reaction and join as the player line gated by
// k_pkas_poachove2). Vanilla body is a pure test with no side effects: the poachers were killed (area plot boolean 4) or
// ran off (area plot boolean 3). The gate adds "holds one Kashyyyk progression item". Without it the briefing takes its ordinary
// route (the task is explained as if still open) and nothing is consumed.
#include "ap_gate"

int StartingConditional()
{
    object oArea = GetArea(OBJECT_SELF);
    int bRemoved = FALSE;
    if (GetLocalBoolean(oArea, 3) != 0) bRemoved = TRUE;
    if (GetLocalBoolean(oArea, 2) != 0) bRemoved = TRUE;
    if (!bRemoved) return FALSE;
    if (!ApGateOpen("kas", 1))
    {
        ApGateMsg("Kashyyyk", 1);
        ApGateSayLater("Kashyyyk", 1);
        return FALSE;
    }
    return TRUE;
}
