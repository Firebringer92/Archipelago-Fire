// Companion event: heartbeat. A follower joins a fight the party is in; with no fight it goes back to the leader. See ap_hen_follow.nss.
#include "ap_hen_follow"

void main()
{
    ExecuteScript("k_ai_master", OBJECT_SELF, 2001);
    if (ApHenLimited()) ApHenIdle();
}
