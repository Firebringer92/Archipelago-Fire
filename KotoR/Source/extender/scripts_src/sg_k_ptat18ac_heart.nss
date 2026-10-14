// Tatooine dead-end repair: bantha respawn. Wrapper for k_ptat18ac_heart, the area heartbeat of the Eastern Dune Sea
// (tat_m18ac only; the vanilla script is preserved as apo_sg_tat18hb). It runs the original first, then re-creates the
// banthas the dragon hunt needs when they cannot be created by Komad's briefing any more (Komad dead or hostile before
// the briefing, or the banthas killed). See sg_tat_banthas for the exact conditions.
#include "sg_tat_banthas"

void main()
{
    ExecuteScript("apo_sg_tat18hb", OBJECT_SELF);
    SgTatBanthaRepair();
}
