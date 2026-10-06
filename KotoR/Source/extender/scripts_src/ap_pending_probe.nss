// Minimal diagnostic: does ExecuteScript("ap_pending_target", ...) reach the
// target's first line at all? No grant logic, no DelayCommand -- just one
// immediate log call, to isolate whether the problem is "the call never
// reaches the target" vs "something inside the target's real logic fails
// silently partway through."
#include "kse"

void main()
{
    KSE_Diag(97, "AP|PENDING_PROBE|reached");
}
