// Story gate T2 (Tatooine): leading the banthas to the lair. Replaces the vanilla condition k_ptat_ambushed
// (tat_m18ac only), the first starter of the bantha dialog tat18_bantha (its only user). Vanilla body: the area flag 0
// (the lure has been done) is set. The starter leads to k_ptat_banthcut2, which moves the party and banthas into
// position and sets the area flag 4 that Komad's dragon scene waits for; the same dialog also holds a second dragon
// chain after it. The gate adds "holds two Tatooine progression items". Without them the starter fails and the bantha only
// ignores the player; the lure state is kept and the step can be done once the progression items arrive.
#include "ap_gate"

int StartingConditional()
{
    if (GetLocalBoolean(GetArea(OBJECT_SELF), 0) == 0) return FALSE;
    if (!ApGateOpen("tat", 2))
    {
        ApGateMsg("Tatooine", 2);
        // Dialog starter: say it as a one-line dialog half a second after the click ends (see sg_k_ptar_candmeet0); one line per click.
        if (KSE_GetData("ap_gate_cd") != "1")
        {
            KSE_SetData("ap_gate_cd", "1");
            DelayCommand(4.0, ApGateCooldownOff());
            SetCustomToken(901, ApGateText("Tatooine", 2));
            DelayCommand(0.6, ApGateSayWhenFree(0));
        }
        return FALSE;
    }
    return TRUE;
}
