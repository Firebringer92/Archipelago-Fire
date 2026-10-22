// Fast goal watcher for the Star Forge room (sta_m45ad). Started from the room's area-entry hook. Malak's death handler sets
// STA_MALAK_DEAD, then the conversation and the ending cutscene follow within seconds and leave the module, so the ordinary
// five-second poll can miss it entirely. This checks the flag four times a second while the party is in the room and reports
// the same goal line the poll reports (the client treats a repeat as a no-op). It stops once the flag is reported or the
// player is no longer in the room.
#include "kse"

void main()
{
    if (GetTag(GetArea(GetFirstPC())) != "sta_m45ad") return;
    if (GetGlobalBoolean("STA_MALAK_DEAD"))
    {
        KSE_Diag(84, "AP|CHECK|GOAL|MALAK_DEAD");
        return;
    }
    DelayCommand(0.25, ExecuteScript("ap_goal_watch", OBJECT_SELF));
}
