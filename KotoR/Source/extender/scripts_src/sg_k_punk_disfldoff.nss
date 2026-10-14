// Story gate U3 (Unknown World): the temple computer, planetary disruptor field shutdown. Wrapper for k_punk_disfldoff
// (node script of unk44_comp E3 and E4, unk_m44ac only; the vanilla script is preserved as apo_sg_disfld). The vanilla
// script sets UNK_DISRUPT_OFF and, once UNK_SHIELD_OFF is also set, unlocks the door unk44_tpllckdoor and adds
// k_starforge 70 or 75 and unk_trapped 98 or 99. With three Unknown World progression items it runs unchanged; without them it
// changes nothing, so a later pass still finds both flags unset. The conversation itself is already refused by the
// starter ap_unk_u3 in unk44_comp; this is the backstop for any other caller. It starts no conversation, so running the
// original through ExecuteScript is safe.
#include "ap_gate"

void main()
{
    if (!ApGateOpen("unk", 3))
    {
        ApGateMsg("Unknown World", 3);
        return;
    }
    ExecuteScript("apo_sg_disfld", OBJECT_SELF);
}
