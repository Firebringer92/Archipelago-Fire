#pragma once

// Minimal file logger. Writes to a writable per-user location, never the game
// directory (see LogInit). This log is how a run is judged without a debugger.
void LogInit();
void Log(const char* fmt, ...);

// Closes the handle Log()/LogDiag() have held open for the session. Call once,
// at DLL_PROCESS_DETACH, before LogRaw() writes the final [shutdown] marker.
// Deliberately lock-free -- see the comment above its definition in log.cpp.
void LogShutdown();

// Append a pre-formatted line using RAW WIN32 ONLY -- CreateFileW/WriteFile/
// CloseHandle, no CRT, no critical section, no allocation, no formatting.
//
// This exists for DLL_PROCESS_DETACH. On process exit Windows terminates every
// other thread BEFORE calling DLL_PROCESS_DETACH, so a thread killed while
// holding a CRT file lock would deadlock the `Log` path above. kernel32 takes no
// such lock and is never unloaded before us, so this is the one logging call
// that is safe during teardown. The caller supplies the whole line including its
// newline; nothing here can fault on a format string.
void LogRaw(const char* text);

// The active log's full path, for the tester header block. Never null once
// LogInit has run; empty string before that.
const wchar_t* LogGetPath();

// ---------------------------------------------------------------------------
// DIAGNOSTIC MODE
//
// LogDiag() is the PER-CALL TRACE. It is silent unless a marker file named
// KSE_DIAGNOSTIC sits beside the DLL, and it is the ONLY thing diagnostic mode
// adds. A tester must never need to enable a flag to produce the lines that
// explain their own failure.
//
// ---------------------------------------------------------------------------
// THE CLASSIFICATION RULE -- THREE CLAUSES, AND THE THIRD IS NOT OPTIONAL
//
//   1. WRITES are unconditional. Anything that mutates a character -- grants,
//      removals, skill and saving-throw writes -- is logged whatever the mode.
//      Array A in particular is PERMANENT and has no engine remover.
//
//   2. REFUSALS-TO-WRITE are unconditional. A refusal is the ABSENCE of a write,
//      so clause 1 does not cover it and the rule was WRONG until this clause was
//      added. It is the case where a modder's script silently does nothing and
//      the log is the only thing that can say why -- the exact silent-failure
//      class this error reporting exists to eliminate. Putting a REFUSING line behind a
//      flag means a modder hits the capacity guard, sees nothing happen, and has
//      no route to the reason without already knowing to create a file they have
//      never heard of. ANOMALY lines are refusals and follow this clause.
//
//   3. READS, QUERIES and STATE DUMPS are diagnostic. These are the high-volume
//      lines -- has-feat checks, data-store gets, array snapshots -- and losing
//      them costs detail, never the answer to "what did KSE do to my save".
//
// The refusals were in fact unconditional before this clause existed, but by an
// ad-hoc exclusion in the conversion, NOT because the rule demanded it. A future
// conversion following the two-clause rule could have reasoned correctly to the
// wrong answer. That is why the clause is written here rather than remembered.
// ---------------------------------------------------------------------------
//
// RESOLVED ONCE, at startup, and cached. Same rule and reason as the capacity
// opt-in: a mode that could change mid-session would make the log ambiguous about
// which regime produced which line.
//
// WHY A FILE AND NOT A SCRIPT CALL. A script-visible toggle is a WRITE to global
// state that a shipped mod could inflict on someone else's machine -- leave it on
// and every user pays the disk and syscall cost. KSE_ERRNO is safe because it is a
// READ. The script-visible surface that does exist is KSE_Diag(), which lets a
// script ANNOTATE the log; scripts annotate, they do not control. Control stays
// out of band, and a file is the one trigger a non-technical tester can be talked
// through over text ("make an empty file called this next to binkw32.dll").
//
// COST WHEN OFF: one predictable branch on a cached bool, before the varargs are
// touched. The trace call sites stay in the binary and cost effectively nothing.
// ---------------------------------------------------------------------------
void LogResolveDiagnostic();
bool LogDiagnosticEnabled();
void LogDiag(const char* fmt, ...);

// -----------------------------------------------------------------------------
// The tester header block.
//
// This is the artifact a NON-TECHNICAL PERSON PASTES INTO A BUG REPORT. It is not
// a debug aid and it is not for us: on an unsupported binary the log is the ONLY
// channel that distinguishes "KSE is unsupported here" from "KSE is not installed",
// because a script reads 0 for both. The reader of that message did not write KSE
// and is reading it because something silently did nothing.
//
// So it is bounded, self-contained, and written in words rather than addresses.
// It is ALWAYS ON. A tester must never need to enable a flag to produce the lines
// that explain their own failure -- diagnostic mode ADDS per-call tracing, it does
// not enable this.
// -----------------------------------------------------------------------------
enum KseLoadState {
    KSE_LOAD_OK,        // fingerprint passed, hook installed -- KSE is working
    KSE_LOAD_REFUSED,   // fingerprint mismatched -- KSE turned itself off
    KSE_LOAD_UNKNOWN,   // sentinel never matched: not-yet-ready OR wrong binary,
                        // which are indistinguishable at this point
    KSE_LOAD_PARTIAL    // binary recognised but KSE could not attach -- ours, not theirs
};
void LogTesterBlock(KseLoadState state, const char* detail);
