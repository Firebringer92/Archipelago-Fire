// Retest of self-rescheduling DelayCommand, WITHOUT any custom-global-based
// tick counter -- the earlier "fires once" conclusion relied on reading
// back a custom global to display tick=N, and we've since confirmed custom
// globals silently fail to persist. If THAT counter was the broken part,
// not the rescheduling itself, this would have looked identical to a
// genuine one-shot failure. This version logs via KSE_Diag on every single
// fire (no global read/write at all) so repeated firing is directly
// visible as repeated log lines, regardless of any counter value.
//
// DelayCommand here schedules a continuation of THIS script's own already-
// loaded bytecode -- no ExecuteScript/resref re-resolution involved at all,
// so it should be unaffected by the ExecuteScript content-staleness issue
// found elsewhere this session.
#include "kse"

void Tick()
{
    KSE_Diag(100, "AP|HEARTBEAT2|tick");
    DelayCommand(5.0, Tick());
}

void main()
{
    Tick();
}
