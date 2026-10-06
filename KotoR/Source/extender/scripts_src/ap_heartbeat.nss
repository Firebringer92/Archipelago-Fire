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

// Every chain carries the generation it was started in. main() bumps the
// generation, so a chain from an earlier start sees a mismatch on its next
// tick and ends. Without this, ap_poll_shared's staleness check (which
// compares the in-game clock and can read a jump as a dead heartbeat) kept
// starting a new chain while the old ones were still alive, and the poll
// ended up running several times a second.
void Tick(int nGen)
{
    if (KSE_GetData("hb_gen") != IntToString(nGen)) return;
    // Liveness stamp for ap_poll_shared's self-healing staleness check --
    // see generate_poll_shared.py. Written every tick so a dead heartbeat
    // (e.g. after a same-process Load Game silently kills the DelayCommand
    // chain) is detected within ~20s by the next area/module transition.
    int nNow = GetTimeHour() * 3600 + GetTimeMinute() * 60 + GetTimeSecond();
    KSE_SetData("hb_tick_time", IntToString(nNow));

    // Diagnostic instrumentation -- see this generator's own
    // module docstring for exactly what this is trying to localize.
    int nTickNum = 0;
    if (KSE_HasData("hb_tick_num")) nTickNum = StringToInt(KSE_GetData("hb_tick_num"));
    nTickNum = nTickNum + 1;
    KSE_SetData("hb_tick_num", IntToString(nTickNum));
    // Tick markers are logged for the first tick and then every 12th (about once a minute): the
    // per-tick pair was two log lines every 5 s. A START with no matching RESCHEDULED (the same
    // number) still localises a tick that died, and AP|POLLRUN|begin/end (every poll) shows the
    // poll itself.
    int bTickLog = (nTickNum % 12 == 1);
    if (bTickLog) KSE_Diag(153, "AP|TICK_START|" + IntToString(nTickNum));

    ExecuteScript("ap_poll_shared", OBJECT_SELF);

    if (bTickLog) KSE_Diag(154, "AP|TICK_RESCHEDULED|" + IntToString(nTickNum));
    DelayCommand(5.0, Tick(nGen));
}

// DeathLink 2-second dedicated loop. The main 5s Tick()'s own death
// detection (ap_poll_shared's CheckDeath()) misses most real deaths --
// KOTOR auto-revives a downed PC almost immediately once combat ends as
// long as a companion is alive, and if the whole die-then-revive cycle
// completes inside one 5s gap, the poll never observes GetIsDead()==true
// at all. Mod_OnPlayerDeath/Mod_OnPlayerDying were
// investigated as a real event-driven alternative but their stock scripts
// don't exist anywhere in the actual game data (confirmed via a chitin.key
// resource scan) -- likely vestigial NWN-inherited fields this engine never
// invokes, so hooking them would be an unverified assumption. This is a
// deliberate compromise instead: a SECOND, minimal DelayCommand loop doing
// ONLY the GetIsDead() check, at 2s instead of 5s (halved from an initial
// 1s proposal after a real concern about adding load on top of an already
// flaky heartbeat -- see this project's own history of silent heartbeat
// deaths). Zero added overhead in the normal (not-dead) case -- no
// diagnostic line written unless the check is actually positive. Emits the
// EXACT SAME AP|CHECK|DEATH marker (code 64) ap_poll_shared's CheckDeath()
// already produces, so kotor_reconciliation.py's existing per-cycle dedup
// (_cycle_saw_death/_was_dead, reset on the next AP|SKILLREPORT|) needs zero
// client-side changes -- whichever of the two sources sees the death first
// just sets the same flag a little earlier.
void DeathTick(int nGen)
{
    if (KSE_GetData("hb_gen") != IntToString(nGen)) return;
    object oPC = GetFirstPC();
    if (GetIsDead(oPC))
    {
        KSE_Diag(64, "AP|CHECK|DEATH");
    }
    DelayCommand(2.0, DeathTick(nGen));
}

void main()
{
    KSE_Diag(103, "AP|HEARTBEAT_STARTED");
    int nGen = 1;
    if (KSE_HasData("hb_gen")) nGen = StringToInt(KSE_GetData("hb_gen")) + 1;
    KSE_SetData("hb_gen", IntToString(nGen));
    Tick(nGen);
    DeathTick(nGen);
}
