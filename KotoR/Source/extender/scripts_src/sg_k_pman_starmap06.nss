// Story gate M3 backstop (Manaan): the star map hologram. Wrapper for k_pman_starmap06, the node script on the last
// reply of the dialog man28_starmap in manm28ad (the vanilla script is preserved as apo_sg_mmap06). The vanilla script
// gives man_starmap, raises K_STAR_MAP and sets K_STAR_MAP_MANAAN. The conversation is started by the trigger
// script demo_trig03, which carries the same gate; this keeps the star map shut if the conversation is reached another way.
#include "ap_gate"

void main()
{
    if (!ApGateOpen("man", 3))
    {
        ApGateMsg("Manaan", 3);
        ApGateSayLater("Manaan", 3);
        return;
    }
    ExecuteScript("apo_sg_mmap06", OBJECT_SELF);
}
