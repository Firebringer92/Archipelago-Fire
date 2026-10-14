// Story gate K3 (Kashyyyk): Chuundar's confrontation, the "Freyyr was helped" starter. Replaces the vanilla condition
// k_pkas_freyyhelp, a shared script with one compiled copy (no module copy) read by kas23_chuunda_01 (starter) and
// kas24_gorwook_01 (starter). Vanilla body: kas_HelpedFreyyr is set. The gate applies only when the conversation owner is
// Chuundar (tag kas23_chuunda_01): there it also requires three Kashyyyk progression items, so the throne-room confrontation (stages
// 110 and 120) waits for them. For every other owner the result is exactly the vanilla value. Companion scripts:
// sg_k_pkas_freydead2, sg_k_pkas_freyydead, sg_k_pkas_chuuntrig. When both globals are set the message comes from
// sg_k_pkas_freydead2, which is evaluated first, so it is not repeated here.
#include "ap_gate"

int StartingConditional()
{
    if (GetGlobalBoolean("kas_HelpedFreyyr") != TRUE) return FALSE;
    if (GetStringLowerCase(GetTag(OBJECT_SELF)) == "kas23_chuunda_01" && !ApGateOpen("kas", 3))
    {
        if (GetGlobalBoolean("kas_FreyyrDead") != TRUE)
        {
            ApGateMsg("Kashyyyk", 3);
            ApGateSayLater("Kashyyyk", 3);
        }
        return FALSE;
    }
    return TRUE;
}
