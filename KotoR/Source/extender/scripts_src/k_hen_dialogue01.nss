// Companion event: talked to, or heard a shout. Only a shout (a call to join a fight) is limited. See ap_hen_follow.nss.
#include "ap_hen_follow"

void main()
{
    if (GetListenPatternNumber() == -1) ExecuteScript("k_ai_master", OBJECT_SELF, 2004);
    else ApHenCombatEvent(2004);
}
