// Story gate M1 (Manaan): Roland Wann's briefing, second setter. Replaces the vanilla node script k_pman_planet95, which
// only runs on E66 of the dialog man26_repdip ("Good. I'm glad that you have come to accept the inevitable") and whose
// entire body is SetGlobalNumber("MAN_PLANET_PLOT", 2), the same as k_pman_planet25. The node is reached from Roland's
// returning-visitor starter, which already requires the value to be 2, so this is a backstop for saves made before the
// gate existed. The gate sets the value only with one Manaan progression item.
#include "ap_gate"

void main()
{
    if (!ApGateOpen("man", 1))
    {
        ApGateMsg("Manaan", 1);
        ApGateSayLater("Manaan", 1);
        return;
    }
    SetGlobalNumber("MAN_PLANET_PLOT", 2);
}
