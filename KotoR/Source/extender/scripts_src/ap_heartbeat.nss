// The real, persistent heartbeat. Started once (staged via k_pend_modab,
// same as any other apply), then self-reschedules forever via DelayCommand
// -- confirmed reliable over 7+ minutes and across area transitions.
//
// Each tick just reports via ExecuteScript("ap_poll_shared") -- safe, that
// resref's content only ever changes together with a full restart, so it
// doesn't hit the ExecuteScript content-staleness issue found elsewhere
// this session. Real AP grants are NOT dispatched from here -- see
// arm_orchestrator.py / generate_trampoline_batch.py for the actual
// delivery pipeline (current-area-and-neighbors trampolines).
#include "kse"

void Tick()
{
    // Liveness stamp for ap_poll_shared's self-healing staleness check --
    // see generate_poll_shared.py. Written every tick so a dead heartbeat
    // (e.g. after a same-process Load Game silently kills the DelayCommand
    // chain) is detected within ~20s by the next area/module transition.
    int nNow = GetTimeHour() * 3600 + GetTimeMinute() * 60 + GetTimeSecond();
    KSE_SetData("hb_tick_time", IntToString(nNow));

    ExecuteScript("ap_poll_shared", OBJECT_SELF);

    DelayCommand(5.0, Tick());
}

void main()
{
    KSE_Diag(103, "AP|HEARTBEAT_STARTED");
    Tick();
}
