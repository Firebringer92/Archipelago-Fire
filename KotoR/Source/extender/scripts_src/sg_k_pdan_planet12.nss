// Story gate D3 (Dantooine): the post-ruins council scene. Replaces the vanilla condition k_pdan_planet12, the starter
// of Vandar's deliberation, the send-off to the ship and Juhani's request to join. Vanilla body: DAN_VANDARR_DONE not
// set and DAN_STARMAP_DONE set; when that holds it sets DAN_VANDARR_DONE and returns TRUE. The gate adds "holds three
// Dantooine progression items" and sets the flag only when it passes, so the scene plays whenever the progression items arrive.
#include "ap_gate"

int StartingConditional()
{
    if (GetGlobalBoolean("DAN_VANDARR_DONE")) return FALSE;
    if (!GetGlobalBoolean("DAN_STARMAP_DONE")) return FALSE;
    if (!ApGateOpen("dan", 3))
    {
        ApGateMsg("Dantooine", 3);
        // Dialog starter: say it as a one-line dialog half a second after the click ends (see sg_k_ptar_candmeet0); one line per click.
        if (KSE_GetData("ap_gate_cd") != "1")
        {
            KSE_SetData("ap_gate_cd", "1");
            DelayCommand(4.0, ApGateCooldownOff());
            SetCustomToken(901, ApGateText("Dantooine", 3));
            DelayCommand(0.6, ApGateSayWhenFree(0));
        }
        return FALSE;
    }
    SetGlobalBoolean("DAN_VANDARR_DONE", TRUE);
    return TRUE;
}
