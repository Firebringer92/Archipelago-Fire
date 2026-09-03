#pragma once
#include <windows.h>

// KSE_STAGE selects the detour at build time:
//   1 = pure pass-through (no observable effect at all)
//   2 = pass-through + call counter
// It is set by the build (target_compile_definitions); a build that does not
// define it is a mistake we want to catch at compile time, not at runtime.
#ifndef KSE_STAGE
#error "KSE_STAGE must be defined as 1 (pure pass-through) or 2 (pass-through + counter)"
#endif

// NOTE: the set of live stages is duplicated in several places -- CMakeLists.txt,
// build/Build-KSE.ps1, this guard, dllmain.cpp's stage epilogue, and hook.cpp's
// stage blocks. Adding a stage means touching all of them; miss this one and the
// build fails as "g_hookCount: undeclared identifier".
//
// 19 is the unified build and needs every counter below, because it carries every
// function family at once.
#if KSE_STAGE == 2 || KSE_STAGE == 4 || KSE_STAGE == 5 || KSE_STAGE == 6 || KSE_STAGE == 7 \
 || KSE_STAGE == 8 || KSE_STAGE == 9 || KSE_STAGE == 10 || KSE_STAGE == 11 || KSE_STAGE == 12 \
 || KSE_STAGE == 17 || KSE_STAGE == 18 || KSE_STAGE == 19
// Number of times the dispatcher hook fired (all routine IDs). Stage 2's observable
// effect; later stages keep it so the hook is visibly alive and transparent for
// every call they do NOT claim. Not defined in stage 1 (no observable effect).
extern volatile LONG g_hookCount;
#endif

#if KSE_STAGE == 17 || KSE_STAGE == 18 || KSE_STAGE == 19
// Writes a session-end marker at DLL_PROCESS_DETACH through LogRaw (raw Win32, no
// CRT), so a clean quit shows a clean exit and a log ending WITHOUT this marker
// means the process was killed.
void KseSt17_ShutdownFlush();
// Grant/read counters, so the worker thread can log the totals unconditionally.
extern volatile LONG g_granta;
extern volatile LONG g_areads;
#endif
#if KSE_STAGE == 18 || KSE_STAGE == 19
extern volatile LONG g_removea;   // removal counter (STAGE 18's remover)
#endif

#if KSE_STAGE == 19
// ---------------------------------------------------------------------------
// The capacity-crossing opt-in.
//
// KseCapacityCrossingAllowed() reports whether an opt-in marker file sits beside
// the DLL. It is resolved ONCE, at hook install, and cached -- never re-read per
// call, because a mode that could change mid-session would make the log ambiguous
// about which regime produced which line.
//
// The guard itself is NOT removed by this: it still evaluates and still logs; only
// the early return is bypassed, and only when the marker is present. Log first,
// bypass second, so the log is never silenced at the moment worth observing.
void KseResolveCapacityOptIn();
bool KseCapacityCrossingAllowed();
#endif

// Install the pass-through hook on the dispatcher at `target`. Returns true on
// success. Must be called only after the target's bytes match KSE_SENTINEL (i.e.
// once the code is decrypted and stable) -- see the worker thread.
bool InstallDispatcherHook(void* target);
