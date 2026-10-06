// TEMPORARY diagnostic-only heartbeat, used once for a memory-address hunt:
// same self-rescheduling shape as the real ap_heartbeat.nss, but Tick() never
// resets MAIN_PLOT and never dispatches/applies anything -- it just reports.
// This lets a marker value sit in MAIN_PLOT indefinitely (instead of being
// reset within 5s by the real heartbeat) so a SNAPSHOT can be taken without
// racing the clock. Deploy over ap_heartbeat.ncs temporarily, then restore
// the real one afterward -- see generate_heartbeat.py for the real version.
#include "kse"

void Tick()
{
    int nNow = GetTimeHour() * 3600 + GetTimeMinute() * 60 + GetTimeSecond();
    KSE_SetData("hb_tick_time", IntToString(nNow));

    ExecuteScript("ap_poll_shared", OBJECT_SELF);

    DelayCommand(5.0, Tick());
}

void main()
{
    KSE_Diag(103, "AP|HEARTBEAT_STARTED_DIAG");
    Tick();
}
