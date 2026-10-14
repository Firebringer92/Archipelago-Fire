// Story gate K3 (Kashyyyk): Chuundar's reward scene after Freyyr was killed. Replaces the vanilla condition
// k_pkas_freyydead, a shared script with one compiled copy (no module copy) read by kas23_chuunda_01 (last starter),
// kas23_postzaa_01 (starter), kas23_wookfem_01 (two links), kas24_gorwook_01 (starter) and kas25_comp_01 (two links).
// Vanilla body: kas_FreyyrDead is set. The gate applies only when the conversation owner is Chuundar (tag
// kas23_chuunda_01): there it also requires three Kashyyyk progression items, so the reward scene (kas23_mainwookplot 130) waits for
// them. For every other owner the result is exactly the vanilla value. Companion scripts: sg_k_pkas_freydead2,
// sg_k_pkas_freyyhelp, sg_k_pkas_chuuntrig. When Freyyr was also helped, the message comes from the earlier-evaluated
// starters and is not repeated here.
#include "ap_gate"

int StartingConditional()
{
    if (GetGlobalBoolean("kas_FreyyrDead") != TRUE) return FALSE;
    if (GetStringLowerCase(GetTag(OBJECT_SELF)) == "kas23_chuunda_01" && !ApGateOpen("kas", 3))
    {
        if (GetGlobalBoolean("kas_HelpedFreyyr") != TRUE)
        {
            ApGateMsg("Kashyyyk", 3);
            ApGateSayLater("Kashyyyk", 3);
        }
        return FALSE;
    }
    return TRUE;
}
