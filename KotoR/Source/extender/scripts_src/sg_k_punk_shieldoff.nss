// Story gate U3 (Unknown World): the temple computer, energy shield shutdown. Dispatcher for k_punk_shieldoff, a name
// that exists in two modules with different scripts. In unk_m44ac (node script of unk44_comp E2 and E5; preserved as
// apo_sg_shldac) it sets UNK_SHIELD_OFF and, once UNK_DISRUPT_OFF is also set, unlocks the door unk44_tpllckdoor and adds
// k_starforge 70 or 75 and unk_trapped 98 or 99: gated here behind three Unknown World progression items, with nothing changed
// while they are missing. In unk_m44aa (node script of unk_comp2 E40, the prototype droid shield; preserved as
// apo_sg_shldaa) it is unrelated to the story and always runs unchanged. Neither original starts a conversation, so
// running them through ExecuteScript is safe.
#include "ap_gate"

void main()
{
    if (GetStringLowerCase(GetModuleFileName()) == "unk_m44ac")
    {
        if (!ApGateOpen("unk", 3))
        {
            ApGateMsg("Unknown World", 3);
            return;
        }
        ExecuteScript("apo_sg_shldac", OBJECT_SELF);
        return;
    }
    ExecuteScript("apo_sg_shldaa", OBJECT_SELF);
}
