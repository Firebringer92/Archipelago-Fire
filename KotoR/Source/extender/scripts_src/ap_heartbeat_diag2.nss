// TEMPORARY diagnostic: self-changes MAIN_PLOT once, purely via its own
// tick counter, with NO reload/module-load involved -- isolates whether
// relocation is specifically tied to Load Game, or happens even within one
// continuous session. Tick 1-3: leaves MAIN_PLOT alone (whatever k_pend_modab
// set it to, e.g. 89). Tick 4+: sets it to 55 once and stops changing it.
#include "kse"

void Tick()
{
    int nNow = GetTimeHour() * 3600 + GetTimeMinute() * 60 + GetTimeSecond();
    KSE_SetData("hb_tick_time", IntToString(nNow));

    ExecuteScript("ap_poll_shared", OBJECT_SELF);

    int nCount = KSE_HasData("diag2_count") ? StringToInt(KSE_GetData("diag2_count")) : 0;
    nCount = nCount + 1;
    KSE_SetData("diag2_count", IntToString(nCount));

    if (nCount == 4)
    {
        SetGlobalNumber("MAIN_PLOT", 55);
        KSE_Diag(107, "AP|DIAG2_CHANGED|55");
    }

    DelayCommand(5.0, Tick());
}

void main()
{
    KSE_Diag(103, "AP|HEARTBEAT_STARTED_DIAG2");
    Tick();
}
