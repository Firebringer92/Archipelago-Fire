// Story gate Ko2 (Korriban): Uthar offers the final test and takes the player to Naga Sadow's tomb. Replaces the vanilla
// condition k35_uth_presfini (korr_m35aa only), the starter of node E91 of kor35_utharwynn and the only route to the
// node that runs k35_uth_finaltmb. Vanilla body: GetGlobalNumber("KOR_SITH_PRESTIGE") > 4 (the same body as the shared
// k_pkor_prestige5, which is left alone). The gate adds "holds two Korriban progression items". Without them Uthar falls back to
// his ordinary greeting starters; prestige, the academy tasks and the stage-30 declaration are untouched.
#include "ap_gate"

int StartingConditional()
{
    if (GetGlobalNumber("KOR_SITH_PRESTIGE") <= 4) return FALSE;
    if (!ApGateOpen("kor", 2))
    {
        ApGateMsg("Korriban", 2);
        // Dialog starter: say it as a one-line dialog half a second after the click ends (see sg_k_ptar_candmeet0); one line per click.
        if (KSE_GetData("ap_gate_cd") != "1")
        {
            KSE_SetData("ap_gate_cd", "1");
            DelayCommand(4.0, ApGateCooldownOff());
            SetCustomToken(901, ApGateText("Korriban", 2));
            DelayCommand(0.6, ApGateSayWhenFree(0));
        }
        return FALSE;
    }
    return TRUE;
}
