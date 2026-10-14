// Story gate D2 backstop (Dantooine): Vandar's ruins mission offer. Replaces the vanilla condition k_pdan_planet03:
// DAN_JEDI_PLOT == 7 and neither DAN_STARMAP_DONE nor DAN_VANDARR_DONE set, no side effect. The gate adds "holds two
// Dantooine progression items", which covers the rare routes that reach DAN_JEDI_PLOT 7 without the Padawan scene.
#include "ap_gate"

int StartingConditional()
{
    if (GetGlobalNumber("DAN_JEDI_PLOT") != 7) return FALSE;
    if (GetGlobalBoolean("DAN_STARMAP_DONE")) return FALSE;
    if (GetGlobalBoolean("DAN_VANDARR_DONE")) return FALSE;
    if (!ApGateOpen("dan", 2))
    {
        ApGateMsg("Dantooine", 2);
        return FALSE;
    }
    return TRUE;
}
