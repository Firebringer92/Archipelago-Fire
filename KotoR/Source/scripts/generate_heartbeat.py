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
lines.append('    ExecuteScript("ap_poll_shared", OBJECT_SELF);')
lines.append("")
lines.append("    DelayCommand(5.0, Tick());")
lines.append("}")
lines.append("")
lines.append("void main()")
lines.append("{")
lines.append('    KSE_Diag(103, "AP|HEARTBEAT_STARTED");')
lines.append("    Tick();")
lines.append("}")

import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out_path = os.path.join(REPO_ROOT, "extender", "scripts_src", "ap_heartbeat.nss")
with open(out_path, "w") as f:
    f.write("\n".join(lines) + "\n")

print(f"Wrote {out_path} ({len(lines)} lines)")
