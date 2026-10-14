// Story gate K1 (Kashyyyk): Jolee's ending dialogue. Replaces the vanilla condition k_pkas_poachove2 (kas_m24aa only),
// the link condition on the player line "I have made certain the poachers are gone" in kas24_jolee_02. That line is the
// way into Jolee's reaction to the poachers and from there into his barrier offer and the join (kas22_starmap 50,
// k_pkas_joleejoin). Vanilla body is a pure test with no side effects: the poachers were killed (area plot boolean 4) or
// ran off (area plot boolean 3) in kas_m24aa, and Jolee has been talked to (plot boolean 10 on Jolee). The gate adds
// "holds one Kashyyyk progression item". Without it the line is hidden and Jolee falls back to his other lines; nothing is consumed
// and the line returns once the progression item arrives. The poacher kill and the emitter shutdown still record their own journal
// stage. Companion script sg_k_pkas_poachover closes the second way into the same reaction.
#include "ap_gate"

int StartingConditional()
{
    object oArea = GetArea(OBJECT_SELF);
    int bRemoved = FALSE;
    if (GetLocalBoolean(oArea, 3) != 0) bRemoved = TRUE;
    if (GetLocalBoolean(oArea, 2) != 0) bRemoved = TRUE;
    if (!bRemoved) return FALSE;
    if (GetLocalBoolean(OBJECT_SELF, 10) == 0) return FALSE;
    if (!ApGateOpen("kas", 1))
    {
        ApGateMsg("Kashyyyk", 1);
        ApGateSayLater("Kashyyyk", 1);
        return FALSE;
    }
    return TRUE;
}
