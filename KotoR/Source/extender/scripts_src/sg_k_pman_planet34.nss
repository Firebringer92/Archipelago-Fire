// Story gate M2 (Manaan): Roland Wann's debrief. Replaces the vanilla condition k_pman_planet34, the starter of the dialog
// man26_repdip that asks for the stolen data recording. Vanilla body: MAN_PLANET_PLOT == 2. That starter is the only way
// into the debrief nodes that advance man_planet to 30 and man26_starmap to 30 and hand over the submarine key W_REPKEY2.
// The gate adds "holds two Manaan progression items", but only once the player carries the recording (W_DDATA), so a player still
// looking for it keeps Roland's ordinary reminder. The condition has no side effects.
#include "ap_gate"

int StartingConditional()
{
    if (GetGlobalNumber("MAN_PLANET_PLOT") != 2) return FALSE;
    if (!GetIsObjectValid(GetItemPossessedBy(GetFirstPC(), "W_DDATA"))) return TRUE;
    if (!ApGateOpen("man", 2))
    {
        ApGateMsg("Manaan", 2);
        // Dialog starter: say it as a one-line dialog half a second after the click ends (see sg_k_ptar_candmeet0); one line per click.
        if (KSE_GetData("ap_gate_cd") != "1")
        {
            KSE_SetData("ap_gate_cd", "1");
            DelayCommand(4.0, ApGateCooldownOff());
            SetCustomToken(901, ApGateText("Manaan", 2));
            DelayCommand(0.6, ApGateSayWhenFree(0));
        }
        return FALSE;
    }
    return TRUE;
}
