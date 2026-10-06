// TEMPORARY diagnostic: cycles MAIN_PLOT through several distinct values
// over time, purely via its own tick counter (no reload needed), so
// multiple clean within-session before/after snapshot pairs can be taken
// to triangulate the real address via intersection.
#include "kse"

void Tick()
{
    int nNow = GetTimeHour() * 3600 + GetTimeMinute() * 60 + GetTimeSecond();
    KSE_SetData("hb_tick_time", IntToString(nNow));

    ExecuteScript("ap_poll_shared", OBJECT_SELF);

    int nCount = KSE_HasData("diag3_count") ? StringToInt(KSE_GetData("diag3_count")) : 0;
    nCount = nCount + 1;
    KSE_SetData("diag3_count", IntToString(nCount));

    if (nCount == 3) { SetGlobalNumber("MAIN_PLOT", 55); KSE_Diag(107, "AP|DIAG3_CHANGED|55"); }
    else if (nCount == 6) { SetGlobalNumber("MAIN_PLOT", 77); KSE_Diag(107, "AP|DIAG3_CHANGED|77"); }
    else if (nCount == 9) { SetGlobalNumber("MAIN_PLOT", 33); KSE_Diag(107, "AP|DIAG3_CHANGED|33"); }
    else if (nCount == 12) { SetGlobalNumber("MAIN_PLOT", 91); KSE_Diag(107, "AP|DIAG3_CHANGED|91"); }
    else if (nCount == 15) { SetGlobalNumber("MAIN_PLOT", 12); KSE_Diag(107, "AP|DIAG3_CHANGED|12"); }

    DelayCommand(5.0, Tick());
}

void main()
{
    KSE_Diag(103, "AP|HEARTBEAT_STARTED_DIAG3");
    Tick();
}
