// Story gate D1 (Dantooine): becoming a Jedi. Replaces the vanilla condition k_pdan_saber01 (danm13 only), the starter
// of Dorak's class and crystal conversation. Vanilla body: if DAN_DORAK_DONE (Zhar sent the player to Dorak) is set,
// clear it and return TRUE. The gate adds "holds one Dantooine progression item" and clears the flag only when it passes, so the
// flag Zhar set survives until the conversation can actually play. Without the progression item Dorak falls back to his other
// starters and the player keeps their current class.
#include "ap_gate"

int StartingConditional()
{
    if (!GetGlobalBoolean("DAN_DORAK_DONE")) return FALSE;
    if (!ApGateOpen("dan", 1))
    {
        ApGateMsg("Dantooine", 1);
        // Dialog starter: say it as a one-line dialog half a second after the click ends (see sg_k_ptar_candmeet0); one line per click.
        if (KSE_GetData("ap_gate_cd") != "1")
        {
            KSE_SetData("ap_gate_cd", "1");
            DelayCommand(4.0, ApGateCooldownOff());
            SetCustomToken(901, ApGateText("Dantooine", 1));
            DelayCommand(0.6, ApGateSayWhenFree(0));
        }
        return FALSE;
    }
    SetGlobalBoolean("DAN_DORAK_DONE", FALSE);
    return TRUE;
}
