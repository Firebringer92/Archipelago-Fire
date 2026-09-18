"""
Generates ap_heartbeat.nss -- the persistent, self-rescheduling tick that
keeps ap_poll_shared's periodic reporting alive independent of area
transitions.

REMOVED (this session): the old MAIN_PLOT-based Dispatch block that used to
inline every apply's logic directly into Tick() and run it when
GetGlobalNumber("MAIN_PLOT") was nonzero. Confirmed dead -- the current
delivery pipeline (arm_orchestrator.py / generate_trampoline_batch.py)
queues everything through the player's current-area-and-neighbors
trampolines instead, and dllmain.c's ap_apply() explicitly documents that
every real arm_id bypasses MAIN_PLOT/k_pend_modab staging entirely and goes
straight to the orchestrator. Nothing has set MAIN_PLOT in the current
architecture, so this Dispatch branch could never fire. Removed along with
its 41 now-fully-dead ap_arm_*.nss / ap_apply_*.nss standalone scripts and
their generator (generate_arm_scripts.py) -- see project cleanup notes.

What's left is genuinely live: (1) a liveness stamp ap_poll_shared's
self-healing staleness check reads, (2) the ExecuteScript("ap_poll_shared")
call that's the actual periodic 5s report, (3) the DelayCommand
self-reschedule that keeps this ticking forever.

DIAGNOSTIC INSTRUMENTATION: added to localize the recurring
silent-heartbeat-death bug (root cause still open -- see
docs/MODE_DEPENDENCIES.md's "Recurring silent-heartbeat-death bug" open
item). Two markers per tick, deliberately kept to two (not three+) to
avoid meaningfully adding to log/relay volume: "TICK_START|<n>" right
when Tick() begins (before the ExecuteScript call), and
"TICK_RESCHEDULED|<n>" right before the DelayCommand(5.0, Tick())
self-reschedule call at the end. If a future death shows a TICK_START
with no matching TICK_RESCHEDULED for the SAME tick number, the failure
is localized to somewhere inside that tick's ExecuteScript
("ap_poll_shared") call; if TICK_RESCHEDULED for the last tick IS
present but Tick() never runs again, the failure is in DelayCommand's
own mechanism instead, a completely different root cause. Also lets a
real collision theory be checked directly: a BONUS_ITEM milestone grant
(LootMode=bonus, see patch_item_suppression.py, which ALSO has matching
before/after markers around its own CreateItemOnObject/KSE_SetData
block) was once observed in the same burst as a heartbeat death -- if
TICK_START/TICK_RESCHEDULED timestamps ever interleave with a
BONUS_MILESTONE_START/_END pair from the SAME game tick, that's real
evidence of two scripts genuinely competing for the same per-frame
instruction budget, not just a timing coincidence.

DEATHLINK 2s LOOP: a second, independent self-rescheduling
DelayCommand chain (DeathTick(), started from main() alongside Tick()) that
does nothing but check GetIsDead() every 2 seconds -- see its own comment
below for the full root-cause writeup (the main 5s poll misses most real
deaths to KOTOR's own auto-revive). Deliberately a
SEPARATE chain rather than folding into Tick() itself, so a failure in one
doesn't necessarily take down the other, though both share this script's
lifecycle (started together, both die together on a same-process Load
Game per the staleness note above).
"""

lines = []
lines.append("// The real, persistent heartbeat. Started once (staged via k_pend_modab,")
lines.append("// same as any other apply), then self-reschedules forever via DelayCommand")
lines.append("// -- confirmed reliable over 7+ minutes and across area transitions.")
lines.append("//")
lines.append("// Each tick just reports via ExecuteScript(\"ap_poll_shared\") -- safe, that")
lines.append("// resref's content only ever changes together with a full restart, so it")
lines.append("// doesn't hit the ExecuteScript content-staleness issue found elsewhere")
lines.append("// this session. Real AP grants are NOT dispatched from here -- see")
lines.append("// arm_orchestrator.py / generate_trampoline_batch.py for the actual")
lines.append("// delivery pipeline (current-area-and-neighbors trampolines).")
lines.append("#include \"kse\"")
lines.append("")
lines.append("void Tick()")
lines.append("{")
lines.append("    // Liveness stamp for ap_poll_shared's self-healing staleness check --")
lines.append("    // see generate_poll_shared.py. Written every tick so a dead heartbeat")
lines.append("    // (e.g. after a same-process Load Game silently kills the DelayCommand")
lines.append("    // chain) is detected within ~20s by the next area/module transition.")
lines.append("    int nNow = GetTimeHour() * 3600 + GetTimeMinute() * 60 + GetTimeSecond();")
lines.append('    KSE_SetData("hb_tick_time", IntToString(nNow));')
lines.append("")
lines.append("    // Diagnostic instrumentation -- see this generator's own")
lines.append("    // module docstring for exactly what this is trying to localize.")
lines.append("    int nTickNum = 0;")
lines.append('    if (KSE_HasData("hb_tick_num")) nTickNum = StringToInt(KSE_GetData("hb_tick_num"));')
lines.append("    nTickNum = nTickNum + 1;")
lines.append('    KSE_SetData("hb_tick_num", IntToString(nTickNum));')
lines.append('    KSE_Diag(153, "AP|TICK_START|" + IntToString(nTickNum));')
lines.append("")
lines.append('    ExecuteScript("ap_poll_shared", OBJECT_SELF);')
lines.append("")
lines.append('    KSE_Diag(154, "AP|TICK_RESCHEDULED|" + IntToString(nTickNum));')
lines.append("    DelayCommand(5.0, Tick());")
lines.append("}")
lines.append("")
lines.append("// DeathLink 2-second dedicated loop. The main 5s Tick()'s own death")
lines.append("// detection (ap_poll_shared's CheckDeath()) misses most real deaths --")
lines.append("// KOTOR auto-revives a downed PC almost immediately once combat ends as")
lines.append("// long as a companion is alive, and if the whole die-then-revive cycle")
lines.append("// completes inside one 5s gap, the poll never observes GetIsDead()==true")
lines.append("// at all. Mod_OnPlayerDeath/Mod_OnPlayerDying were")
lines.append("// investigated as a real event-driven alternative but their stock scripts")
lines.append("// don't exist anywhere in the actual game data (confirmed via a chitin.key")
lines.append("// resource scan) -- likely vestigial NWN-inherited fields this engine never")
lines.append("// invokes, so hooking them would be an unverified assumption. This is a")
lines.append("// deliberate compromise instead: a SECOND, minimal DelayCommand loop doing")
lines.append("// ONLY the GetIsDead() check, at 2s instead of 5s (halved from an initial")
lines.append("// 1s proposal after a real concern about adding load on top of an already")
lines.append("// flaky heartbeat -- see this project's own history of silent heartbeat")
lines.append("// deaths). Zero added overhead in the normal (not-dead) case -- no")
lines.append("// diagnostic line written unless the check is actually positive. Emits the")
lines.append("// EXACT SAME AP|CHECK|DEATH marker (code 64) ap_poll_shared's CheckDeath()")
lines.append("// already produces, so kotor_reconciliation.py's existing per-cycle dedup")
lines.append("// (_cycle_saw_death/_was_dead, reset on the next AP|SKILLREPORT|) needs zero")
lines.append("// client-side changes -- whichever of the two sources sees the death first")
lines.append("// just sets the same flag a little earlier.")
lines.append("void DeathTick()")
lines.append("{")
lines.append("    object oPC = GetFirstPC();")
lines.append("    if (GetIsDead(oPC))")
lines.append("    {")
lines.append('        KSE_Diag(64, "AP|CHECK|DEATH");')
lines.append("    }")
lines.append("    DelayCommand(2.0, DeathTick());")
lines.append("}")
lines.append("")
lines.append("void main()")
lines.append("{")
lines.append('    KSE_Diag(103, "AP|HEARTBEAT_STARTED");')
lines.append("    Tick();")
lines.append("    DeathTick();")
lines.append("}")

import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out_path = os.path.join(REPO_ROOT, "extender", "scripts_src", "ap_heartbeat.nss")
with open(out_path, "w") as f:
    f.write("\n".join(lines) + "\n")

print(f"Wrote {out_path} ({len(lines)} lines)")
