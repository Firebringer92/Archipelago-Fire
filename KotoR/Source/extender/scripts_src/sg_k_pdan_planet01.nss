// Story gate D3 (Dantooine): the council scene when the ruins were done first. Replaces the vanilla condition
// k_pdan_planet01: DAN_STARMAP_DONE set, DAN_JEDI_PLOT below 7 and DAN_VANDARM_DONE not set; when that holds it sets
// DAN_VANDARM_DONE and returns TRUE. The gate adds "holds three Dantooine progression items" and sets the flag only when it passes.
#include "ap_gate"

int StartingConditional()
{
    if (!GetGlobalBoolean("DAN_STARMAP_DONE")) return FALSE;
    if (GetGlobalNumber("DAN_JEDI_PLOT") >= 7) return FALSE;
    if (GetGlobalBoolean("DAN_VANDARM_DONE")) return FALSE;
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
    SetGlobalBoolean("DAN_VANDARM_DONE", TRUE);
    return TRUE;
}
