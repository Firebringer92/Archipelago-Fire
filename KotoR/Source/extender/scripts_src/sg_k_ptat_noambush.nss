// Story gate T1 (Tatooine): the bantha lure. Replaces the vanilla condition k_ptat_noambush (tat_m18ac only), the lure
// starter of the bantha dialog tat18_bantha (its only user). Vanilla body: the player holds the bantha fodder
// (tat20_banthafod) and the area flag 0 (set by k_ptat_banthcut1, the lure) is not yet set. The lure node E2 writes
// tat18ac_dragonhunt 50 and runs the Sand People ambush. The gate adds "holds one Tatooine progression item". Without it the dialog
// falls back to its last starter ("completely disinterested"), nothing is consumed, and the lure can be done later.
#include "ap_gate"

int StartingConditional()
{
    if (!GetIsObjectValid(GetItemPossessedBy(GetFirstPC(), "tat20_banthafod"))) return FALSE;
    if (GetLocalBoolean(GetArea(OBJECT_SELF), 0) != 0) return FALSE;
    if (!ApGateOpen("tat", 1))
    {
        ApGateMsg("Tatooine", 1);
        // Dialog starter: say it as a one-line dialog half a second after the click ends (see sg_k_ptar_candmeet0); one line per click.
        if (KSE_GetData("ap_gate_cd") != "1")
        {
            KSE_SetData("ap_gate_cd", "1");
            DelayCommand(4.0, ApGateCooldownOff());
            SetCustomToken(901, ApGateText("Tatooine", 1));
            DelayCommand(0.6, ApGateSayWhenFree(0));
        }
        return FALSE;
    }
    return TRUE;
}
