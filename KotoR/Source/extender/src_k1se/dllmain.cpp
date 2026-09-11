#include <windows.h>
#include <stdint.h>
#include <stdio.h>   // _snprintf_s, for the tester block's detail strings

#include "log.h"
#include "hook.h"
#include "offsets.h"
#include "fingerprint.h"

// KOTOR AP ADDITION (not part of upstream K1SE): ap_extender.c is a plain C
// module (the socket bridge, log-tailer, orchestrator shell-out) with no
// DllMain of its own -- this merged entry point owns DllMain and spawns its
// worker thread alongside K1SE's own WorkerThread below. extern "C" avoids
// C++ name-mangling when linking against the C-compiled definitions.
extern "C" {
    void ap_extender_start(void);
    void ap_extender_shutdown(void);
}

// -----------------------------------------------------------------------------
// DLL entry point.
//
// Goal: load into the game via the binkw32 proxy, wait until the game's code is
// decrypted and stable, install the dispatcher hook, and leave the game playing
// identically.
// -----------------------------------------------------------------------------

static const DWORD KSE_POLL_MS      = 50;      // read-only poll cadence
static const DWORD KSE_TIMEOUT_MS   = 120000;  // 2 min: generous for slow first-run startup
static const DWORD KSE_STABLE_MS    = 100;     // re-check delay to confirm bytes have settled
static const DWORD KSE_COUNT_LOG_MS = 3000;    // how often to report the hit counter

// Read-only comparison of the target's first bytes against the sentinel.
//
// `p` points into our own process image (.text), which the loader maps readable
// for the whole run: before decryption it holds ciphertext, after it holds the
// real prologue. Reads therefore never fault in normal operation -- but the read
// is wrapped in SEH anyway so that a surprise (an unexpected memory state) turns
// into "not matched yet", never a crash inside the game.
static bool MatchSentinel(const unsigned char* p)
{
    __try {
        for (size_t i = 0; i < KSE_SENTINEL_LEN; ++i) {
            if (p[i] != KSE_SENTINEL[i]) return false;
        }
        return true;
    }
    __except (EXCEPTION_EXECUTE_HANDLER) {
        return false;
    }
}

// -----------------------------------------------------------------------------
// The binary fingerprint: verify the loaded game is the one KSE's addresses were
// built for, BEFORE installing anything. The probe table is in src/fingerprint.h.
//
// WHY REFUSE TO INSTALL rather than install-and-refuse-to-dispatch: a hook that is
// present but inert would mean the log shows KSE loaded while every call returns the
// absent value. If the addresses are wrong, KSE should not be in the dispatch path
// at all.
//
// THE COST, accepted deliberately: with no hook installed, KSE_GetVersion() returns
// 0 -- byte-identical to KSE not being installed. A SCRIPT CANNOT TELL THE TWO
// APART. The log below is the only channel that distinguishes them, which is why it
// is part of the product and says in words that scripts will silently do nothing.
//
// __try: on a binary this is NOT built for, base+rva can be unmapped, and a
// fingerprint check that faults would be worse than the mismatch it was checking for.
static bool VerifyFingerprint(BYTE* base)
{
    size_t failed = 0;

    for (size_t i = 0; i < KSE_PROBE_COUNT; ++i) {
        const KseProbe* p = &KSE_PROBES[i];
        uint32_t got = 0;
        bool read = false;

        __try {
            got  = KseFnv1a32(reinterpret_cast<const unsigned char*>(base + p->rva), p->len);
            read = true;
        }
        __except (EXCEPTION_EXECUTE_HANDLER) {
            read = false;
        }

        if (!read) {
            Log("fingerprint: probe %u/%u (%s) at rva 0x%08X is UNREADABLE -- this image "
                "is not merely different, it is smaller or differently laid out",
                (unsigned)(i + 1), (unsigned)KSE_PROBE_COUNT, p->name, p->rva);
            ++failed;
        } else if (got != p->hash) {
            Log("fingerprint: probe %u/%u (%s) MISMATCH at rva 0x%08X -- expected "
                "%08X, found %08X",
                (unsigned)(i + 1), (unsigned)KSE_PROBE_COUNT, p->name, p->rva,
                p->hash, got);
            ++failed;
        }
    }

    if (failed == 0) {
        Log("fingerprint: all %u probes matched -- this is the image K1SE's addresses "
            "were built for. NOTE: this does NOT verify the struct offsets; they match "
            "no bytes and are relied on by association with a matching image.",
            (unsigned)KSE_PROBE_COUNT);
        return true;
    }

    // The per-probe MISMATCH lines above are for US. This block is for the TESTER,
    // written for the reader who actually has to act on it.
    Log("fingerprint: %u of %u probes failed; refusing to install.",
        (unsigned)failed, (unsigned)KSE_PROBE_COUNT);
    char detail[128];
    _snprintf_s(detail, sizeof(detail), _TRUNCATE,
                "%u of %u internal checks did not match.",
                (unsigned)failed, (unsigned)KSE_PROBE_COUNT);
    LogTesterBlock(KSE_LOAD_REFUSED, detail);
    return false;
}

static DWORD WINAPI WorkerThread(LPVOID)
{
    BYTE* base = reinterpret_cast<BYTE*>(GetModuleHandleW(NULL));
    unsigned char* target = base + KSE_DISPATCHER_RVA;

    Log("worker: module base=%p, dispatcher target=%p", base, target);
    Log("worker: polling for decrypted dispatcher (every %u ms, timeout %u ms)",
        KSE_POLL_MS, KSE_TIMEOUT_MS);

    // Deferred hooking -- the whole reason this runs on a thread and not in
    // DllMain. A proxy DLL's DllMain executes during loader initialization, BEFORE
    // the game's .text is decrypted. Hooking then would patch bytes that are later
    // overwritten -- the classic "too early" failure. So we poll, read-only, until
    // the dispatcher's bytes equal the known prologue (the sentinel), which is the
    // observable "code is ready" signal.
    DWORD elapsed = 0;
    bool matched = false;
    while (elapsed < KSE_TIMEOUT_MS) {
        if (MatchSentinel(target)) {
            // Confirm stability: re-read after a short delay so we never install
            // during a partial in-place write of the region.
            Sleep(KSE_STABLE_MS);
            if (MatchSentinel(target)) { matched = true; break; }
        }
        Sleep(KSE_POLL_MS);
        elapsed += KSE_POLL_MS;
    }

    if (!matched) {
        // Clean give-up: the design requirement is that "bytes never stabilize"
        // does nothing at all rather than hooking garbage.
        Log("worker: TIMED OUT after ~%u ms; dispatcher bytes never matched the "
            "sentinel. Installing NO hook. Game left untouched.", elapsed);

        // The sentinel poll is the same check as fingerprint probe 1, at the same
        // address. So a binary whose dispatcher differs never reaches VerifyFingerprint
        // -- it times out here instead, and "wrong binary" and "still not ready" are the
        // SAME OBSERVATION at this point. This message must carry both, and it is the
        // ONLY output a user on an unsupported build ever sees.
        char detail[128];
        _snprintf_s(detail, sizeof(detail), _TRUNCATE,
                    "gave up after %u seconds waiting for the game to be ready.",
                    (unsigned)(elapsed / 1000));
        LogTesterBlock(KSE_LOAD_UNKNOWN, detail);
        return 0;
    }

    Log("worker: dispatcher bytes stabilized after ~%u ms", elapsed);

    // Verify this is the image the addresses were built for BEFORE installing
    // anything. Runs HERE and not earlier because .text is not decrypted until the
    // poll above succeeds; probing sooner compares against bytes that are not yet the
    // real code and always fails.
    if (!VerifyFingerprint(base)) {
        return 0;   // refuse to INSTALL. See VerifyFingerprint for why, and the cost.
    }

    Log("worker: installing byte-exact pass-through hook (STAGE %d)", KSE_STAGE);

    if (!InstallDispatcherHook(target)) {
        Log("worker: hook installation FAILED; game left running unhooked");
        // Binary was RECOGNISED and we still could not attach -- so this is our
        // fault, not the tester's setup, and the block says so rather than sending
        // them to check their game version.
        LogTesterBlock(KSE_LOAD_PARTIAL, "the code hook could not be installed.");
        return 0;
    }

// The worker/banner arms for the early stages have been removed; the epilogue chain
// below covers the stages that remain.
#if KSE_STAGE == 17
    // STAGE 17: the array-A grant plus GetFeatAcquired. Totals are logged
    // UNCONDITIONALLY every tick (not only when they change), so the last pre-exit
    // tick is at most one interval stale.
    Log("worker: STAGE 17 hook installed at %p. GrantFeatArrayA on routine %d (void), "
        "GetFeatAcquired on routine %d; all other calls forward unchanged. Persistence "
        "is observed from the saved FILE, not from a hook.", target, KSE_GRANTA_ID, KSE_FEAT_ID);
    // The tester block is emitted by EVERY built configuration, not only the shipping
    // one: stages 17/18 are a compile-time canary on the code shared with 19, and a
    // canary is only meaningful if the configurations AGREE on the always-on path.
    // They are frozen legacy and will never gain a host, so their counts cannot go
    // stale the way STAGE 19's could.
    LogTesterBlock(KSE_LOAD_OK, "2 functions are available (STAGE 17, legacy).");
    for (;;) {
        Sleep(KSE_COUNT_LOG_MS);
        Log("worker: STAGE 17 totals grants=%ld reads=%ld dispatcher-fired=%ld",
            (long)g_granta, (long)g_areads, (long)g_hookCount);
    }
#elif KSE_STAGE == 18
    // STAGE 18: STAGE 17's grant and read, plus RemoveFeatArrayA. One build carries
    // the whole protocol so a grant-then-remove test never requires a DLL swap
    // mid-test -- a swap would put two artifacts in one result.
    Log("worker: STAGE 18 hook installed at %p. GrantFeatArrayA on routine %d (void), "
        "RemoveFeatArrayA on routine %d (void, drain-and-rebuild), GetFeatAcquired on "
        "routine %d; all other calls forward unchanged. Removal persistence is observed "
        "from the saved FILE, not from a hook.",
        target, KSE_GRANTA_ID, KSE_REMOVEA_ID, KSE_FEAT_ID);
    LogTesterBlock(KSE_LOAD_OK, "3 functions are available (STAGE 18, legacy).");
    for (;;) {
        Sleep(KSE_COUNT_LOG_MS);
        Log("worker: STAGE 18 totals grants=%ld removes=%ld reads=%ld dispatcher-fired=%ld",
            (long)g_granta, (long)g_removea, (long)g_areads, (long)g_hookCount);
    }
#elif KSE_STAGE == 19
    // STAGE 19 -- THE UNIFIED BUILD. Every shipping function live at once, on
    // fourteen hosts with no duplicate claims.
    //
    // The banner names every claimed host explicitly, and that is deliberate: it is
    // the log line a tester's report will carry, and it confirms WHICH build produced
    // the run. A banner that said only "STAGE 19" would make a stale DLL
    // indistinguishable from a current one.
    Log("worker: STAGE 19 (UNIFIED, KOTOR AP fork) hook installed at %p. 15 hosts: "
        "int-suite push/eval %d/%d, string push/eval %d/%d, "
        "data store %d/%d/%d/%d, GetFeatAcquired %d, AdjustCreatureSkills %d, "
        "saving throws %d/%d, GrantFeatArrayA %d (void), RemoveFeatArrayA %d (void), "
        "SetCreatureField %d (void, KOTOR AP addition). "
        "All other calls forward unchanged.",
        target,
        KSE_PUSH_ID, KSE_EVAL_ID, KSE_PUSHSTR_ID, KSE_STROUT_ID,
        KSE_DS_PUSHS_ID, KSE_DS_PUSHI_ID, KSE_DS_EVALI_ID, KSE_DS_GETDATA_ID,
        KSE_FEAT_ID, KSE_SKILL_ID, KSE_SAVE_WRITE_ID, KSE_SAVE_READ_ID,
        KSE_GRANTA_ID, KSE_REMOVEA_ID, KSE_FIELD_ID);
    // The capacity-crossing mode goes in the banner on EVERY run, armed or not, so
    // the log is never ambiguous about which regime produced a given line.
    Log("worker: STAGE 19 capacity opt-in: %s. %s",
        KseCapacityCrossingAllowed() ? "ARMED" : "DISARMED",
        KseCapacityCrossingAllowed()
            ? "The opt-in marker KSE_LAB_MODE is present beside the DLL; a grant at "
              "count==cap will grow the feat array. This is a laboratory state."
            : "Guard active: a grant at count==cap is refused. This is the shipping state.");
    // THE COUNT IS COMPUTED FROM THIS LIST, NOT TYPED. A hardcoded count goes stale
    // the first time a host is added, and a wrong number inside the block a tester
    // PASTES INTO A BUG REPORT is exactly the kind of small false fact that costs a
    // support conversation to unpick. Adding a host means adding it here, and the
    // block follows automatically.
    static const int KSE_HOSTS[] = {
        KSE_PUSH_ID,     KSE_EVAL_ID,      KSE_PUSHSTR_ID,    KSE_STROUT_ID,
        KSE_DS_PUSHS_ID, KSE_DS_PUSHI_ID,  KSE_DS_EVALI_ID,   KSE_DS_GETDATA_ID,
        KSE_FEAT_ID,     KSE_SKILL_ID,     KSE_SAVE_WRITE_ID, KSE_SAVE_READ_ID,
        KSE_GRANTA_ID,   KSE_REMOVEA_ID,   KSE_FIELD_ID
    };
    char okDetail[192];
    _snprintf_s(okDetail, sizeof(okDetail), _TRUNCATE,
                "%u functions are available.%s",
                (unsigned)(sizeof(KSE_HOSTS) / sizeof(KSE_HOSTS[0])),
                KseCapacityCrossingAllowed()
                    ? " NOTE: the capacity opt-in is ARMED -- this is a testing "
                      "setting, not the normal one."
                    : "");
    LogTesterBlock(KSE_LOAD_OK, okDetail);
    for (;;) {
        Sleep(KSE_COUNT_LOG_MS);
        Log("worker: STAGE 19 totals grants=%ld removes=%ld reads=%ld dispatcher-fired=%ld",
            (long)g_granta, (long)g_removea, (long)g_areads, (long)g_hookCount);
    }
#else
    // No stage-specific epilogue. Reaching here means a stage was added to the
    // CMake/build-script allow-lists but not to this chain: the hook IS installed,
    // but there is no banner and no dispatcher counter, so the log cannot confirm
    // which build is running. Fail loudly at compile time instead.
    #error "KSE_STAGE has no WorkerThread epilogue -- add one (banner + counter loop)"
#endif
}

BOOL APIENTRY DllMain(HMODULE hModule, DWORD reason, LPVOID)
{
    if (reason == DLL_PROCESS_ATTACH) {
        // We only ever get resident here; we do not hook here (see WorkerThread).
        DisableThreadLibraryCalls(hModule);
        LogInit();
        // Diagnostic mode is resolved HERE -- before the first line is written -- so
        // no line in the session is ambiguous about which regime produced it. Same
        // rule and reason as the capacity opt-in.
        LogResolveDiagnostic();
        Log("DllMain: diagnostic mode %s%s",
            LogDiagnosticEnabled() ? "ON" : "OFF",
            LogDiagnosticEnabled()
                ? " -- sentinel KSE_DIAGNOSTIC is present beside the DLL. Per-call "
                  "tracing is being written; the log will grow FAST and will rotate."
                : " (normal). Per-call tracing is silent; everything that explains a "
                  "failure is logged regardless.");
        Log("DllMain: K1SE proxy attached to pid %lu. Deferring hook to a worker "
            "thread -- must not hook before the SteamStub decrypts .text.",
            GetCurrentProcessId());

        HANDLE h = CreateThread(NULL, 0, WorkerThread, NULL, 0, NULL);
        if (h) {
            CloseHandle(h);
        } else {
            Log("DllMain: CreateThread FAILED; no hook will be installed");
        }

        // KOTOR AP ADDITION (not part of upstream K1SE): the socket bridge and
        // log-tailer start unconditionally, independent of hook installation --
        // they never touch game code, only sockets/files/subprocesses, so they
        // have no reason to wait on the sentinel poll the way hook installation
        // must. If the hook install above ever fails or refuses (unrecognised
        // build), this project's own extender functionality (item delivery,
        // etc.) still needs the rest of KSE's existing surface to work, so
        // there's no independent reason to gate it further than KSE itself does.
        Log("DllMain: starting KOTOR AP extender (socket bridge + log-tailer).");
        ap_extender_start();
    }
#if KSE_STAGE == 17 || KSE_STAGE == 18 || KSE_STAGE == 19
    else if (reason == DLL_PROCESS_DETACH) {
        ap_extender_shutdown();
        // Handlers log synchronously, so nothing is lost mid-session; this writes the
        // clean-exit marker (totals) via the raw-Win32 path, so a run whose log ends
        // WITHOUT it was killed rather than exited cleanly, and its result is suspect.
        // __try/__except: a teardown fault must not turn a clean exit into a crash.
        //
        // ⚠ Any new stage that runs a save/quit protocol MUST be added to this guard.
        // A stage missing here installs and dispatches fine, but its log simply ends on
        // a routine worker tick with no [shutdown] line, so every save-then-quit result
        // ends ambiguously.
        //
        // LogShutdown() first, closing the session-long handle Log()/LogDiag() have
        // held open (2026-09-10) -- lock-free by design, see its own comment in
        // log.cpp, same reason KseSt17_ShutdownFlush's marker line goes through the
        // separate lock-free LogRaw() path rather than Log() itself.
        __try { LogShutdown(); } __except (EXCEPTION_EXECUTE_HANDLER) { }
        __try { KseSt17_ShutdownFlush(); } __except (EXCEPTION_EXECUTE_HANDLER) { }
    }
#endif
    return TRUE;
}
