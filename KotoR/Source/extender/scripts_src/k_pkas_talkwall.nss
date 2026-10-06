// Wrapper for kas_m24aa's k_pkas_talkwall (the first node of the repulsor-field
// dialogue kas24_force_01, preserved byte-exact as apo_talkwall_orig). Seats
// Jolee for the conversation when he hasn't been recruited, so the field can be
// opened under every companion_mode -- see ap_jolee_field.nss.
#include "kse"
#include "ap_jolee_field"

void main()
{
    StageJoleeForField();
    ExecuteScript("apo_talkwall_orig", OBJECT_SELF);
}
