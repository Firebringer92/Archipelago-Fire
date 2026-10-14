// Story gate 2 (Taris): Canderous's first meeting. Replaces the vanilla condition
// k_ptar_candmeet0, the first-meeting starter of both cantina dialogs (tar03_cand031 in
// tar_m02ae and tar_m03ae; the compiled script is identical in every module that has it).
// Vanilla body: GetGlobalNumber("TAR_CANDMEET") == 0. The gate adds "holds two Taris progression items".
// Without them the first-meeting conversation does not start, so the deal and the plan stay
// unavailable; nothing is consumed and Canderous can be met once the progression items arrive.
#include "ap_gate"

int StartingConditional()
{
    if (GetGlobalNumber("TAR_CANDMEET") != 0) return FALSE;
    if (!ApGateOpen("tar", 2))
    {
        ApGateMsg("Taris", 2);
        // This is a dialog starter, so a conversation cannot be started from here while the game decides which line to open with.
        // The click ends without a conversation; half a second later the player says the line (one-line dialog ap_gate_msg).
        // The condition can be evaluated several times for one click, so a short cooldown keeps it to one line.
        if (KSE_GetData("ap_gate_cd") != "1")
        {
            KSE_SetData("ap_gate_cd", "1");
            DelayCommand(4.0, ApGateCooldownOff());
            SetCustomToken(901, ApGateText("Taris", 2));
            DelayCommand(0.6, ApGateSayWhenFree(0));
        }
        return FALSE;
    }
    return TRUE;
}
