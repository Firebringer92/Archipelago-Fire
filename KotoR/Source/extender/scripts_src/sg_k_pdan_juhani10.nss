// Story gate D2 backstop (Dantooine): Zhar's Padawan scene. Replaces the vanilla condition k_pdan_juhani10, the starter
// that plays the robe ceremony and sets DAN_JEDI_PLOT to 7. Vanilla body: DAN_JUHANI_PLOT == 2 and DAN_ZHARJ_DONE not
// set; when that holds it sets DAN_ZHARJ_DONE and returns TRUE. The gate adds "holds two Dantooine progression items" and sets the
// flag only when it passes, so meeting Juhani early cannot finish the trials without the progression items.
#include "ap_gate"

int StartingConditional()
{
    if (GetGlobalNumber("DAN_JUHANI_PLOT") != 2) return FALSE;
    if (GetGlobalBoolean("DAN_ZHARJ_DONE")) return FALSE;
    if (!ApGateOpen("dan", 2))
    {
        ApGateMsg("Dantooine", 2);
        // Dialog starter: say it as a one-line dialog half a second after the click ends (see sg_k_ptar_candmeet0); one line per click.
        if (KSE_GetData("ap_gate_cd") != "1")
        {
            KSE_SetData("ap_gate_cd", "1");
            DelayCommand(4.0, ApGateCooldownOff());
            SetCustomToken(901, ApGateText("Dantooine", 2));
            DelayCommand(0.6, ApGateSayWhenFree(0));
        }
        return FALSE;
    }
    SetGlobalBoolean("DAN_ZHARJ_DONE", TRUE);
    return TRUE;
}
