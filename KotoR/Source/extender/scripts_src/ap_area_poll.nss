// OnEnter for areas whose module ships with no OnEnter script of its own, so
// there is no original to preserve and no area-check location to report (see
// scripts/patch_area_poll_hooks.py). All it does is run the shared poll, which
// also restarts the heartbeat: the heartbeat's DelayCommand chain dies on every
// module change and an area with no hook would otherwise leave polling
// stopped until the player walks into a hooked one.
#include "kse"

void main()
{
    if (GetIsPC(GetEnteringObject()))
    {
        ExecuteScript("ap_poll_shared", OBJECT_SELF);
    }
}
