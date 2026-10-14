// Story gate K2 (Kashyyyk): the star-map terminal conversation. Replaces the vanilla condition k_pkas_compudown (kas_m25aa
// only, used once: the second starter of kas25_comp_01). Vanilla body: the global kas_ComputerDown, set only by the
// terminal's own final node (k_pkas_openmap), is true; the starter then shows "[The computer no longer responds.]" and the
// conversation ends. The gate also returns TRUE while the player holds fewer than two Kashyyyk progression items, so the terminal (and
// the star map placeable, which opens the same conversation until the terminal is done) plays that one line and ends. It
// does not set kas_ComputerDown, so the full conversation, the test, the fight and the star map are all still ahead once
// the progression items arrive. The conversation can only be left by passing or failing the test, so the gate must sit in the starter
// list; hiding the reply lines that begin the test would trap the player in the side-question loop. The journal stage
// kas22_starmap 70 is only written inside this dialog.
#include "ap_gate"

int StartingConditional()
{
    if (GetGlobalBoolean("kas_ComputerDown")) return TRUE;
    if (!ApGateOpen("kas", 2))
    {
        ApGateMsg("Kashyyyk", 2);
        // Dialog starter: say it as a one-line dialog half a second after the click ends (see sg_k_ptar_candmeet0); one line per click.
        if (KSE_GetData("ap_gate_cd") != "1")
        {
            KSE_SetData("ap_gate_cd", "1");
            DelayCommand(4.0, ApGateCooldownOff());
            SetCustomToken(901, ApGateText("Kashyyyk", 2));
            DelayCommand(0.6, ApGateSayWhenFree(0));
        }
        return TRUE;
    }
    return FALSE;
}
