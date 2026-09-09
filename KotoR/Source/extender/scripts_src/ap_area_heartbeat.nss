// Native engine OnHeartbeat script -- the engine itself calls this
// repeatedly (roughly every few seconds) for as long as this area is
// loaded, with NO self-rescheduling DelayCommand needed (that approach was
// tested and confirmed broken -- see ap_heartbeat_test.nss history).
#include "kse"

void main()
{
    int nCount = GetGlobalNumber("AP_HEARTBEAT_COUNT") + 1;
    SetGlobalNumber("AP_HEARTBEAT_COUNT", nCount);
    KSE_Diag(14, "AP|AREAHEARTBEAT|tick=" + IntToString(nCount));
}
