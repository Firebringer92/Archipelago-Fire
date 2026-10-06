// Test-only: simulates a quest completing by setting one _DONE flag
// directly, exactly as the real game's own quest scripts would. Used to
// prove the quest-detection half of ap_poll_shared without needing to
// actually complete a real quest through gameplay.
#include "kse"

void DoApply()
{
    SetGlobalBoolean("DAN_STARMAP_DONE", TRUE);
    KSE_Diag(26, "AP|APPLIED|simulate_quest_done|DAN_STARMAP_DONE=TRUE");
}

void main()
{
    DelayCommand(3.0, DoApply());
}
