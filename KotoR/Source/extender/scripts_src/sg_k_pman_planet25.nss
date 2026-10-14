// Story gate M1 (Manaan): Roland Wann's briefing, first setter. Replaces the vanilla node script k_pman_planet25, which
// only runs on E17 of the dialog man26_repdip ("We were using a submersible reconnaissance droid...") and whose entire
// body is SetGlobalNumber("MAN_PLANET_PLOT", 2). That value is what lets Roland ask for the stolen data recording and
// later hold the debrief. The gate sets it only with one Manaan progression item; the rest of the briefing text still plays.
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
