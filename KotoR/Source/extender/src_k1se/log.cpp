#include "log.h"
#include "version.h"

#include <windows.h>
#include <stdio.h>
#include <stdarg.h>
#include <share.h>   // _wfsopen, _SH_DENYNO -- see g_logFile's open sites below

// -----------------------------------------------------------------------------
// The log lives OUTSIDE the game directory: writing under Program Files risks
// permission failures, so we use %LOCALAPPDATA%\KSE\kse.log, falling back to
// %TEMP% then the current directory.
//
// ONE HANDLE, HELD OPEN FOR THE WHOLE SESSION (changed 2026-09-10 -- see the
// dated note below the rotation block for what this replaces and why).
// fflush() after every line is what gives crash-survival: it pushes each line
// out of the CRT's own buffer into the OS's file cache before the next line is
// written, which is what a reader needs after the GAME process dies. The OS
// keeps that data regardless of our handle's state, so nothing here needs the
// handle to be closed for the data to be durable -- only for the OS's own page
// cache to itself survive, i.e. no worse than the previous design, and for a
// vastly more common failure mode (the game process crashing) fully covered.
// -----------------------------------------------------------------------------

// -----------------------------------------------------------------------------
// ROTATION. Without this the log had no size cap and grew without bound for the
// life of an install; rotation caps it.
//
// THE CAP IS DERIVED, not arbitrary. With diagnostic tracing off the log grows at
// roughly 105 KB/hour (about 87 bytes per line, a few lines per second). An 8 MB
// cap therefore holds on the order of 76 hours of normal logging, so an ordinary
// user never rotates at all; with one backup kept the worst case on disk is 16 MB.
//
// COST OF THE CHECK: ZERO ADDED SYSCALLS ON THE HOT PATH. fprintf/vfprintf already
// RETURN the character count, so the byte total is a by-product of writing. Only
// LogInit pays a syscall, once per process, to seed the counter with the existing
// file's size.
//
// ACCURACY: THE CAP IS A SOFT BOUND, NOT AN EXACT ONE. The file is opened in TEXT
// MODE ("a"), so the CRT translates '\n' to CRLF -- two bytes on disk -- while
// fprintf returns a CHARACTER count treating it as one. The counter therefore
// under-counts by ONE BYTE PER LINE, and rotation fires late by roughly the number
// of lines written since LogInit -- on the order of a kilobyte per session against
// an 8 MB cap, and in the safe direction. It is documented rather than fixed
// because the alternatives -- binary mode, or an ftell per line -- cost either the
// CRLF line endings every tool here expects or a syscall on the hot path this
// design exists to keep clear.
//
// FILE_SHARE_WRITE additionally permits a second game instance to append
// concurrently, which would make the counter under-count further. See the
// concurrent-writer note on LogRotateNow.
//
// 2026-09-10: THE OPEN-WRITE-CLOSE-PER-LINE PATH WAS REPLACED, NOT KEPT.
//
// Found via a real tester's bug report and confirmed against their own kse.log
// timestamps (see the project history, not repeated here): the always-on
// heartbeat/poll cadence should be a steady ~5s, and 62 of 331 ticks in that
// one session ran over 6s late, several over 30s, the worst over two minutes --
// with NO area transition and NO orchestrator subprocess anywhere near the
// worst offenders, ruling out both a loading screen and Python startup as the
// cause. That leaves this file: fopen+fclose is a full CreateFile+CloseHandle
// pair, EVERY line, and a game process doing that at a steady rate through a
// live NWScript dispatcher hook is exactly the pattern real-time antivirus
// scanning tends to intercept -- and since Log() runs synchronously ON THE
// GAME'S OWN THREAD (it is called directly from the dispatcher hook, not a
// background thread), any stall in that one file operation freezes the whole
// game, including player input, for as long as it takes. That is a materially
// worse cost than the crash-log durability this design was trading for, and it
// was paid on EVERY line, not just ones near a crash.
//
// The fix keeps the SAME guarantee (every line reaches the OS before the next
// one is written) via fflush() on a handle held open for the session, instead
// of a full close+reopen. Durability is unchanged; the repeated CreateFile/
// CloseHandle pair -- the actual interception surface -- is gone. Rotation
// still needs the handle explicitly closed before MoveFileExW and reopened
// after (a move against an open handle without FILE_SHARE_DELETE can fail);
// see LogRotateNow.
// -----------------------------------------------------------------------------
static const long long KSE_LOG_CAP_BYTES = 8LL * 1024 * 1024;

// FOUND LIVE, SAME DAY AS THE FIX THAT NEEDED THIS: plain _wfopen_s(path, L"a")
// does NOT share the way the old per-line open+close pattern did. Holding that
// handle open for the whole session locked kse.log so tightly that not even a
// separate process (a plain `tail` from outside the game) could read it -- and,
// far more seriously, almost certainly blocked the extender's OWN log-tailer
// thread from reading the very lines Log()/LogDiag() had just written, which is
// what actually relays AP|... events to the Python client. First symptom
// reported: "no heartbeat" -- not because the heartbeat script stopped running,
// but because nothing could read the file that would prove it was.
//
// _wfsopen with _SH_DENYNO requests the same full sharing (read AND write, from
// other handles AND other processes) that LogRaw's own CreateFileW call already
// asks for explicitly via FILE_SHARE_READ|FILE_SHARE_WRITE -- this just gets
// the CRT-level equivalent for the handle Log()/LogDiag() hold open all session,
// instead of leaving the OS to pick a default that turned out to be exclusive.
static FILE* OpenLogFileShared(const wchar_t* path)
{
    return _wfsopen(path, L"a", _SH_DENYNO);
}

static CRITICAL_SECTION g_logLock;
static bool g_logReady = false;
static wchar_t g_logPath[MAX_PATH];
static wchar_t g_logPathOld[MAX_PATH];      // kse.log.1 -- the single kept backup
static long long g_logBytes = 0;            // in-memory; see "COST OF THE CHECK"
static bool g_logRotating = false;          // reentrancy guard: rotation logs
static FILE* g_logFile = nullptr;           // held open for the session -- see the
                                             // 2026-09-10 note above LogCheckRotate

// Which PART of this session the current file holds. Only ONE backup is kept, so a
// session that rotates TWICE discards its own part 1 -- and without a part number
// the survivors do not show it. The reader would find kse.log.1 whose first line
// says "CONTINUED from kse.log.1", POINTING AT ITSELF, with no record that an
// earlier part existed: a session that lost a third of itself while looking whole.
//
// Numbering the parts makes the loss VISIBLE rather than silent. A reader seeing
// PART 3 beside a surviving PART 2 knows PART 1 existed and is gone, which is the
// difference between incomplete evidence and evidence that misrepresents itself.
static unsigned g_logPart = 1;

// -----------------------------------------------------------------------------
// THE RE-EMITTED SESSION HEADER.
//
// The tester block, build id and fingerprint verdict are all written at session
// START, so they live in part 1 -- and a session that rotates more than once
// discards part 1, taking the very block a bug report needs with it.
//
// So the block is CACHED and RE-EMITTED at the top of every part. Each part is then
// self-describing, and no part can be read without knowing which build produced it.
//
// SESSION START is carried explicitly, because re-emitting stamps the ROTATION
// time. Without it every surviving part looks like the session began when that part
// began, and a reader holding a later part cannot tell it is looking at the tail of
// a long run rather than the whole of a short one.
// -----------------------------------------------------------------------------
static char         g_sessionStart[32] = {0};
static KseLoadState g_blockState       = KSE_LOAD_OK;
static char         g_blockDetail[192] = {0};
static bool         g_blockCached      = false;

const wchar_t* LogGetPath()
{
    return g_logReady ? g_logPath : L"";
}

static long long LogFileSize(const wchar_t* path)
{
    WIN32_FILE_ATTRIBUTE_DATA fad;
    if (!GetFileAttributesExW(path, GetFileExInfoStandard, &fad)) return 0;
    return ((long long)fad.nFileSizeHigh << 32) | fad.nFileSizeLow;
}

// Move kse.log -> kse.log.1, replacing any previous .1. Caller holds g_logLock.
//
// MoveFileExW(MOVEFILE_REPLACE_EXISTING) RATHER THAN DeleteFileW + MoveFileW,
// because delete-then-move has a destructive race: with two processes crossing the
// cap together, A deletes .1 and moves log -> .1, then B DELETES THE BACKUP A JUST
// CREATED and its own move then fails -- losing a whole part of the log.
// Replace-existing removes the window in which .1 does not exist. A race can still
// cost one part (B's move may replace A's .1), but no file is ever deleted and then
// not replaced.
//
// BOUNDED, AND UNVERIFIED BY TEST: Steam does not launch a second instance of the
// same game, so two KSE-hooked processes should not arise in normal use. This is
// hardening against a case that has never been observed.
static void LogRotateNow()
{
    // The handle MUST be closed before the move: a rename/move against a file
    // with an open handle that lacks FILE_SHARE_DELETE can fail with a sharing
    // violation, and fopen's default sharing does not grant delete-sharing.
    // Closing first is also what flushes any CRT-internal buffering, though in
    // practice fflush() after every Log()/LogDiag() call already means there is
    // nothing buffered here to lose.
    if (g_logFile) {
        fclose(g_logFile);
        g_logFile = nullptr;
    }

    // Whether or not the move succeeds, the counter is reset. A failure is almost
    // certainly a file lock, and retrying a failed MoveFile on EVERY line would put
    // a syscall back on the hot path this design exists to keep clear. Growing past
    // the cap is the better failure.
    MoveFileExW(g_logPath, g_logPathOld, MOVEFILE_REPLACE_EXISTING);
    g_logBytes = 0;
    ++g_logPart;

    // Reopen against g_logPath -- MoveFileExW just vacated it (or, on a failed
    // move, this reopens the still-oversized file and appends to it, which is
    // the same "growing past the cap is the better failure" trade as above).
    g_logFile = OpenLogFileShared(g_logPath);
}

void LogInit()
{
    InitializeCriticalSection(&g_logLock);

    wchar_t base[MAX_PATH];
    if (!GetEnvironmentVariableW(L"LOCALAPPDATA", base, MAX_PATH)) {
        if (!GetEnvironmentVariableW(L"TEMP", base, MAX_PATH)) {
            wcscpy_s(base, MAX_PATH, L".");
        }
    }

    wchar_t dir[MAX_PATH];
    _snwprintf_s(dir, _countof(dir), _TRUNCATE, L"%s\\KSE", base);
    CreateDirectoryW(dir, NULL); // harmless if it already exists

    _snwprintf_s(g_logPath, _countof(g_logPath), _TRUNCATE, L"%s\\kse.log", dir);
    _snwprintf_s(g_logPathOld, _countof(g_logPathOld), _TRUNCATE, L"%s\\kse.log.1", dir);
    g_logReady = true;

    // Opened ONCE here and held for the rest of the process's life (see the
    // 2026-09-10 note above LogCheckRotate for why this replaced a per-line
    // open+close). If the byte counter below triggers a startup rotation,
    // LogRotateNow() closes this same handle, moves the file, and reopens it --
    // safe to open first because that path already handles an already-open
    // handle correctly. OpenLogFileShared, not a bare _wfopen_s -- see that
    // helper's own comment for why (a real live regression, found 2026-09-11).
    g_logFile = OpenLogFileShared(g_logPath);

    SYSTEMTIME st0;
    GetLocalTime(&st0);
    _snprintf_s(g_sessionStart, sizeof(g_sessionStart), _TRUNCATE,
                "%04d-%02d-%02d %02d:%02d:%02d",
                st0.wYear, st0.wMonth, st0.wDay, st0.wHour, st0.wMinute, st0.wSecond);

    // Seed the counter -- the ONE syscall this whole mechanism costs per process.
    g_logBytes = LogFileSize(g_logPath);

    // ROTATE AT SESSION START, WHICH IS WHY A SESSION IS NEVER SPLIT.
    //
    // Rotating HERE -- before the session has written a single line -- means the
    // rotation boundary falls BETWEEN sessions, so no session is ever split across
    // two files. With diagnostic tracing off a session writes ~105 KB/hour, so this
    // is the only rotation path a normal user will ever take.
    //
    // The mid-session path in Log() exists only for heavy diagnostic runs, and it
    // announces itself in BOTH files precisely because it does split a session.
    if (g_logBytes >= KSE_LOG_CAP_BYTES) {
        long long was = g_logBytes;
        LogRotateNow();
        Log("[rotate] previous log reached %lld bytes (cap %lld) and was moved to "
            "kse.log.1 BEFORE this session started. No session is split by this "
            "rotation. The previous kse.log.1, if any, was discarded.",
            was, KSE_LOG_CAP_BYTES);
    }
}

static void LogCheckRotate();   // defined below; caller must hold g_logLock

void Log(const char* fmt, ...)
{
    if (!g_logReady) return;

    SYSTEMTIME st;
    GetLocalTime(&st);

    EnterCriticalSection(&g_logLock);
    if (g_logFile) {
        // n accumulates the RETURN VALUES of the formatting calls. This is the whole
        // cost of size tracking: no ftell, no GetFileSize, no syscall of any kind.
        int n = fprintf(g_logFile, "[%04d-%02d-%02d %02d:%02d:%02d.%03d] ",
                        st.wYear, st.wMonth, st.wDay,
                        st.wHour, st.wMinute, st.wSecond, st.wMilliseconds);
        va_list ap;
        va_start(ap, fmt);
        int m = vfprintf(g_logFile, fmt, ap);
        va_end(ap);
        fputc('\n', g_logFile);
        // fflush(), not fclose()+reopen: this is the whole fix. It pushes the line
        // to the OS before the next one is written -- the same durability the old
        // close-per-line design gave -- without the repeated CreateFile/CloseHandle
        // pair that turned out to be the actual freeze risk. See the 2026-09-10
        // note above LogCheckRotate.
        fflush(g_logFile);

        if (n > 0) g_logBytes += n;
        if (m > 0) g_logBytes += m;
        g_logBytes += 1;                       // the newline
    }

    LogCheckRotate();
    LeaveCriticalSection(&g_logLock);
}

// Caller MUST hold g_logLock. Shared by Log() and LogDiag(): LogDiag is the path
// that makes rotation reachable in normal use, so it has to run this check too. The
// check itself is an integer compare -- leaving it out of the diagnostic path would
// defer rotation to the 3-second totals tick and overshoot by ~57 KB at diagnostic
// rates, for no saving.
static void LogCheckRotate()
{
    // MID-SESSION ROTATION -- the last resort, and the one that DOES split evidence.
    //
    // Only reachable when a SINGLE session exceeds the cap, which at the always-on
    // rate (~105 KB/hour) would take ~76 hours and in practice means a heavy
    // diagnostic run. Because it splits a session across two files, it is keyed to
    // the PID -- which already appears in the DllMain attach line and is therefore
    // already this project's de-facto session id -- and it says so in BOTH files.
    //
    // Someone slicing a session out afterwards greps the pid, finds these markers,
    // and knows to look in kse.log.1 as well. Without them a split session looks
    // exactly like a truncated one, i.e. like a crash -- which is precisely the
    // inference the [shutdown] marker exists to support, so an unmarked rotation
    // would corrupt a distinction the project already depends on.
    if (!g_logRotating && g_logBytes >= KSE_LOG_CAP_BYTES) {
        g_logRotating = true;
        unsigned long pid = GetCurrentProcessId();

        unsigned part = g_logPart;
        Log("[rotate] session pid=%lu CONTINUES in kse.log -- this file holds PART %u "
            "of that session. Evidence for pid=%lu is SPLIT ACROSS FILES. Cap %lld "
            "bytes reached mid-session.", pid, part, pid, KSE_LOG_CAP_BYTES);
        if (part >= 2) {
            Log("[rotate] WARNING: only ONE backup is kept, so moving this file to "
                "kse.log.1 DISCARDS PART %u of session pid=%lu PERMANENTLY. Parts 1..%u "
                "of this session no longer exist anywhere.", part - 1, pid, part - 1);
        }
        LogRotateNow();
        Log("[rotate] session pid=%lu CONTINUED from kse.log.1 -- this file holds "
            "PART %u. PART %u is in kse.log.1. This is NOT a new session and NOT a "
            "crash: look for pid=%lu in both files.%s",
            pid, g_logPart, g_logPart - 1, pid,
            g_logPart >= 3 ? " EARLIER PARTS OF THIS SESSION HAVE BEEN DISCARDED --"
                             " only the last two parts are kept." : "");

        // RE-EMIT THE SESSION HEADER so this part is self-describing.
        //
        // REENTRANCY: this runs with g_logRotating STILL TRUE. LogTesterBlock issues
        // ~15 nested Log() calls, each of which ends in LogCheckRotate() -- and every
        // one of those returns immediately on the g_logRotating guard. The flag is
        // cleared only AFTER the block is complete, so the header can never trigger a
        // rotation while it is being written. Placing this after the clear would be a
        // real recursion hazard; placing it here is safe by the SAME guard that
        // already protects the two marker lines above.
        //
        // It is also bounded: the block is ~1 KB against an 8 MB cap, so a header can
        // never itself approach the threshold.
        if (g_blockCached) LogTesterBlock(g_blockState, g_blockDetail);

        g_logRotating = false;
    }
}

// -----------------------------------------------------------------------------
// DIAGNOSTIC MODE. Contract and rationale in log.h.
//
// The marker-file resolution mirrors the capacity opt-in deliberately, including
// looking beside the DLL rather than beside the EXE: the marker travels with the
// thing it arms. Two triggers with the same shape are two triggers a tester can be
// talked through with the same sentence.
// -----------------------------------------------------------------------------
static bool g_diagOn       = false;
static bool g_diagResolved = false;

bool LogDiagnosticEnabled() { return g_diagOn; }

void LogResolveDiagnostic()
{
    if (g_diagResolved) return;
    g_diagResolved = true;
    g_diagOn       = false;

    wchar_t path[MAX_PATH];
    HMODULE self = nullptr;
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                            GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                            reinterpret_cast<LPCWSTR>(&LogResolveDiagnostic), &self))
        return;
    DWORD n = GetModuleFileNameW(self, path, MAX_PATH);
    if (n == 0 || n >= MAX_PATH) return;
    wchar_t* slash = path;
    for (wchar_t* p = path; *p; ++p) if (*p == L'\\' || *p == L'/') slash = p;
    static const wchar_t kName[] = L"\\KSE_DIAGNOSTIC";
    if ((size_t)(slash - path) + sizeof(kName) / sizeof(wchar_t) >= MAX_PATH) return;
    lstrcpyW(slash, kName);

    DWORD attr = GetFileAttributesW(path);
    g_diagOn = (attr != INVALID_FILE_ATTRIBUTES) &&
               !(attr & FILE_ATTRIBUTE_DIRECTORY);
}

// The branch is FIRST, before GetLocalTime and before the varargs are touched, so
// the off case costs one predictable test on a cached bool.
void LogDiag(const char* fmt, ...)
{
    if (!g_diagOn || !g_logReady) return;

    SYSTEMTIME st;
    GetLocalTime(&st);

    EnterCriticalSection(&g_logLock);
    if (g_logFile) {
        int n = fprintf(g_logFile, "[%04d-%02d-%02d %02d:%02d:%02d.%03d] ",
                        st.wYear, st.wMonth, st.wDay,
                        st.wHour, st.wMinute, st.wSecond, st.wMilliseconds);
        va_list ap;
        va_start(ap, fmt);
        int m = vfprintf(g_logFile, fmt, ap);
        va_end(ap);
        fputc('\n', g_logFile);
        fflush(g_logFile);   // see the matching comment in Log() above
        if (n > 0) g_logBytes += n;
        if (m > 0) g_logBytes += m;
        g_logBytes += 1;
    }
    LogCheckRotate();
    LeaveCriticalSection(&g_logLock);

    // LogDiag shares Log()'s rotation check rather than deferring to the 3-second totals
    // tick. At diagnostic rates the cap is crossed every few minutes, so this IS the
    // path that makes rotation routine, and deferring would overshoot by ~57 KB per
    // tick for no saving -- the check is an integer compare.


}

// -----------------------------------------------------------------------------
// LogTesterBlock -- see log.h for what this is FOR. Written for someone who did
// not write KSE, pasting it into a bug report.
//
// RULES IT FOLLOWS, because the reader is not us:
//   * no RVAs, no hashes, no opcode numbers -- those go in the detail lines above
//     it, which are for us; this block is for them;
//   * it says what happened to THEIR GAME first, not what happened inside KSE;
//   * in every not-working case it says the game is fine, because the reader's
//     first question is whether they have broken something;
//   * it always states the SILENT-FAILURE consequence, because a script cannot
//     distinguish unsupported from absent -- both read 0 -- so nothing else will
//     ever tell them why their mod did nothing.
// -----------------------------------------------------------------------------
void LogTesterBlock(KseLoadState state, const char* detail)
{
    // Cache for re-emission at each rotation. Re-entrant by design: the rotation
    // path calls this again with the cached values, which simply rewrites them.
    g_blockState  = state;
    g_blockCached = true;
    if (detail != g_blockDetail) {
        _snprintf_s(g_blockDetail, sizeof(g_blockDetail), _TRUNCATE, "%s",
                    detail ? detail : "");
    }

    // The heading carries PART and SESSION START, so three blocks in one session's
    // files are visibly different where it matters and identical where it matters.
    Log("======== K1SE ========   [PART %u | session began %s | pid %lu]",
        g_logPart, g_sessionStart[0] ? g_sessionStart : "unknown",
        (unsigned long)GetCurrentProcessId());
    Log("%s", KSE_BUILD_ID);

    switch (state) {
    case KSE_LOAD_OK:
        Log("Game:   recognised -- all checks passed.");
        Log("Status: LOADED. K1SE is working. %s", detail ? detail : "");
        // Diagnostic mode changes what a log CONTAINS, so a report pasted from a
        // diagnostic session must say so -- otherwise the reader cannot tell a
        // huge trace-filled log from a normal one, or know that rotation may have
        // discarded earlier parts of the very session being reported.
        if (LogDiagnosticEnabled()) {
            Log("        DIAGNOSTIC MODE IS ON (the file KSE_DIAGNOSTIC is next to");
            Log("        binkw32.dll). The log grows fast and older parts may already");
            Log("        have been discarded. Delete that file to return to normal.");
        }
        break;

    case KSE_LOAD_REFUSED:
        Log("Game:   NOT RECOGNISED -- %s", detail ? detail : "a check failed");
        Log("Status: NOT LOADED. K1SE switched itself off on purpose.");
        Log("        Your game is fine and will play normally.");
        Log("What this means: mods that use K1SE will do NOTHING AT ALL. They will");
        Log("        not show an error and they will not crash -- they just will not");
        Log("        work. If a mod seems to do nothing, this is why.");
        Log("What to do: K1SE supports KOTOR 1 on Steam. If you have the GOG version,");
        Log("        a disc copy, or a modified swkotor.exe, K1SE does not support it");
        Log("        yet. Please report this and paste this whole block.");
        break;

    case KSE_LOAD_UNKNOWN:
        Log("Game:   COULD NOT BE CHECKED -- %s", detail ? detail : "startup timed out");
        Log("Status: NOT LOADED. Your game is fine and will play normally.");
        Log("        Either the game had not finished starting, or this is not a");
        Log("        version K1SE recognises. These cannot be told apart here.");
        Log("What this means: mods that use K1SE will do NOTHING AT ALL, silently.");
        Log("What to do: try launching once more. If this block appears again, K1SE");
        Log("        does not support your copy of the game -- please report it and");
        Log("        paste this whole block.");
        break;

    case KSE_LOAD_PARTIAL:
        Log("Game:   recognised -- all checks passed.");
        Log("Status: NOT LOADED. K1SE recognised your game but FAILED TO START.");
        Log("        Your game is fine and will play normally.");
        Log("        This one is a fault in K1SE, not in your setup.");
        Log("What this means: mods that use K1SE will do NOTHING AT ALL, silently.");
        Log("Reason: %s", detail ? detail : "hook installation failed");
        Log("What to do: please report this and paste this whole block.");
        break;
    }

    Log("Log:    %ls", LogGetPath());
    // WHICH BLOCK TO PASTE MUST NOT BE A DECISION. From part 2 onward a reader is
    // holding two files each opening with a block, and the blocks differ only in
    // PART and the rotation timestamp -- build id, verdict and session start are
    // identical by construction, because they are re-emitted from one cache. So the
    // instruction is "any one", which makes a wrong choice impossible rather than
    // merely unlikely.
    if (g_logPart > 1) {
        Log("Note:   this block repeats at the top of EVERY part of this session's log.");
        Log("        All parts describe the SAME session -- paste ANY one of them.");
        Log("        Only the PART number and the time in the heading differ.");
        Log("        Parts before PART %u have been discarded (only two are kept).",
            g_logPart > 1 ? g_logPart - 1 : 1);
    }
    Log("=====================");
}

// -----------------------------------------------------------------------------
// LogShutdown -- closes the session-long handle before LogRaw writes the final
// [shutdown] marker through its own, separate handle.
//
// Deliberately does NOT take g_logLock, same reasoning as LogRaw immediately
// below: by DLL_PROCESS_DETACH, Windows has already terminated every other
// thread, so nothing can be concurrently inside Log()/LogDiag() to race with
// this close -- but a thread killed WHILE holding the lock would never release
// it, and EnterCriticalSection here would hang forever, turning a clean exit
// into the exact hang this teardown path exists to avoid. Not strictly required
// for data safety (every line is already fflush()'d as it's written -- this is
// about releasing the handle cleanly, not about not losing anything), but cheap
// and correct to do anyway.
// -----------------------------------------------------------------------------
void LogShutdown()
{
    if (g_logFile) {
        fclose(g_logFile);
        g_logFile = nullptr;
    }
}

// -----------------------------------------------------------------------------
// LogRaw -- see log.h. Win32 only, for DLL_PROCESS_DETACH.
//
// Deliberately does NOT take g_logLock: during teardown the owning thread may
// already have been terminated, and blocking on a lock nobody will release turns
// a clean exit into a hang. FILE_APPEND_DATA with share-read/write makes the
// unsynchronised append safe enough for the one or two lines written here.
// -----------------------------------------------------------------------------
void LogRaw(const char* text)
{
    if (!g_logReady || !text) return;

    DWORD len = 0;
    while (text[len]) ++len;
    if (!len) return;

    HANDLE h = CreateFileW(g_logPath, FILE_APPEND_DATA,
                           FILE_SHARE_READ | FILE_SHARE_WRITE, NULL,
                           OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h == INVALID_HANDLE_VALUE) return;
    DWORD written = 0;
    WriteFile(h, text, len, &written, NULL);
    CloseHandle(h);
}
