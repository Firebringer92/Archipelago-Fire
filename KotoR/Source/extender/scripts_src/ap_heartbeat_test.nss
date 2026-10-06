// Tests whether a self-rescheduling DelayCommand chain survives a
// save/reload. Ticks every 5 seconds, logging an incrementing counter
// (persisted in a global, so we can tell "did ticking resume" from "did
// ticking restart from zero" after a reload).
#include "kse"

void Tick()
{
    int nCount = GetGlobalNumber("AP_HEARTBEAT_COUNT") + 1;
    SetGlobalNumber("AP_HEARTBEAT_COUNT", nCount);
    KSE_Diag(13, "AP|HEARTBEAT|tick=" + IntToString(nCount));
    DelayCommand(5.0, Tick());
}

void main()
{
    SetGlobalNumber("AP_HEARTBEAT_COUNT", 0);
    DelayCommand(3.0, Tick());
}
