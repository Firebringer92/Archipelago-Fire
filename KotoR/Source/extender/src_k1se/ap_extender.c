/*
 * KotOR Archipelago extender -- socket bridge, log-tailer, and orchestrator
 * shell-out.
 *
 * As of the K1SE merge, this is a plain C module with NO DllMain of its own
 * -- dllmain.cpp (K1SE's, extended) owns the single DLL entry point and
 * spawns ap_server_thread() (declared here, defined below) as one more
 * worker thread alongside its own hook-installation WorkerThread. This
 * used to be a fully separate proxy chained on top of a separately-
 * installed stock K1SE:
 *
 *   swkotor.exe -> binkw32.dll (this proxy) -> KSE_HOST.dll (stock K1SE,
 *                  renamed) -> binkw32_real.dll (the true original Bink DLL)
 *
 * That three-layer chain is gone. This project's own extender and K1SE's
 * dispatcher-hook code now build into ONE merged binkw32.dll, forwarding
 * directly to the true original Bink DLL (renamed binkw32_real.dll, same
 * convention K1SE itself already used) -- see src_k1se/dllmain_k1se.cpp
 * for the merged entry point, and this project's own memory notes
 * (kotor_engine_constraints.md / kotor_project_status.md) for the full
 * rationale (why merge rather than fork-as-a-separate-artifact, what was
 * evaluated and rejected).
 *
 * This module still does what it always did:
 *   1. The local TCP bridge (127.0.0.1:25586) the Python-side client talks to.
 *   2. A thread that tails the merged DLL's own kse.log (still written to
 *      %LOCALAPPDATA%\KSE\kse.log by the merged log.cpp) for lines written
 *      by a script calling KSE_Diag(code, "AP|...|..."), relaying matches
 *      over the socket as EVENT: lines.
 *   3. The orchestrator shell-out and the whole APPLY:/APPLYVALUE:/etc.
 *      socket protocol, unchanged.
 */
#define WIN32_LEAN_AND_MEAN
#define _CRT_SECURE_NO_WARNINGS
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include <stdlib.h>

#pragma comment(lib, "ws2_32.lib")

#define AP_EXTENDER_PORT 25586
#define LOG_SUBDIR "\\KotorApExtender"
#define LOG_FILE "\\extender.log"
#define AP_MARKER "AP|"

static CRITICAL_SECTION g_log_lock;
static char g_log_path[MAX_PATH];
static volatile LONG g_shutdown = 0;

static CRITICAL_SECTION g_client_lock;
static SOCKET g_client = INVALID_SOCKET;

/* Serializes ap_run_orchestrator() calls -- it's invoked from both the
 * socket-handling thread (new check queued) and the kse-log-tail thread
 * (delivery confirmed / area changed). Both read-modify-write the same
 * _pending_queue.json/_armed_state.json files with no locking of their
 * own, so two overlapping orchestrator processes could race and silently
 * drop one side's update. This forces them to run one at a time. */
static CRITICAL_SECTION g_orchestrator_lock;

static void ap_log(const char *fmt, ...) {
    EnterCriticalSection(&g_log_lock);
    FILE *f = fopen(g_log_path, "a");
    if (f) {
        SYSTEMTIME t;
        GetLocalTime(&t);
        fprintf(f, "[%02d:%02d:%02d.%03d] ", t.wHour, t.wMinute, t.wSecond, t.wMilliseconds);
        va_list args;
        va_start(args, fmt);
        vfprintf(f, fmt, args);
        va_end(args);
        fprintf(f, "\n");
        fclose(f);
    }
    LeaveCriticalSection(&g_log_lock);
}

static void ap_init_log_path(void) {
    char base[MAX_PATH];
    DWORD n = GetEnvironmentVariableA("LOCALAPPDATA", base, MAX_PATH);
    if (n == 0 || n >= MAX_PATH) {
        strcpy(base, ".");
    }
    strcpy(g_log_path, base);
    strcat(g_log_path, LOG_SUBDIR);
    CreateDirectoryA(g_log_path, NULL);
    strcat(g_log_path, LOG_FILE);
}

/* Send a line to whichever client is currently connected, if any. */
static void ap_push_to_client(const char *line) {
    EnterCriticalSection(&g_client_lock);
    if (g_client != INVALID_SOCKET) {
        char msg[700];
        _snprintf(msg, sizeof(msg) - 1, "EVENT:%s\n", line);
        msg[sizeof(msg) - 1] = '\0';
        send(g_client, msg, (int)strlen(msg), 0);
    }
    LeaveCriticalSection(&g_client_lock);
}

/* Forward declarations -- defined further down (after AP_ARM_NAMES), used
 * here by the log-tail thread to detect area-change and delivery-confirmed
 * lines and drive the arm-batch orchestrator accordingly. */
static void ap_run_orchestrator(const char *args);
static int ap_arm_id_for_name(const char *name);

static int g_last_area_idx = -1;

/* Tails K1SE's kse.log for lines containing our AP| marker (written by a
 * script calling KSE_Diag(code, "AP|...")) and relays them to the socket. */
static DWORD WINAPI ap_kse_log_tail_thread(LPVOID unused) {
    (void)unused;
    char kse_log_path[MAX_PATH];
    char base[MAX_PATH];
    DWORD n = GetEnvironmentVariableA("LOCALAPPDATA", base, MAX_PATH);
    if (n == 0 || n >= MAX_PATH) strcpy(base, ".");
    strcpy(kse_log_path, base);
    strcat(kse_log_path, "\\KSE\\kse.log");

    ap_log("kse-log-tail: watching %s", kse_log_path);

    long last_pos = 0;
    int have_baseline = 0;
    static char line[2048];

    while (!g_shutdown) {
        FILE *f = fopen(kse_log_path, "r");
        if (!f) {
            Sleep(500);
            continue;
        }

        if (!have_baseline) {
            /* Don't replay K1SE's whole existing log on first attach --
             * jump straight to EOF and only watch for NEW lines from here. */
            fseek(f, 0, SEEK_END);
            last_pos = ftell(f);
            have_baseline = 1;
            fclose(f);
            Sleep(300);
            continue;
        }

        fseek(f, last_pos, SEEK_SET);
        while (fgets(line, sizeof(line), f)) {
            size_t len = strlen(line);
            while (len > 0 && (line[len - 1] == '\n' || line[len - 1] == '\r')) line[--len] = '\0';

            if (strstr(line, AP_MARKER)) {
                ap_log("KSE-LOG MATCH: %s", line);
                ap_push_to_client(line);

                /* Player entered a (possibly new) covered area -- re-center
                 * the armed set (current area + neighbors) on it. Only acts
                 * when the index actually changed, since this line repeats
                 * on every poll, not just area-enter events. */
                const char *area_marker = strstr(line, "AP|CHECK|AREA|");
                if (area_marker) {
                    int idx = atoi(area_marker + strlen("AP|CHECK|AREA|"));
                    if (idx != g_last_area_idx) {
                        g_last_area_idx = idx;
                        char args[64];
                        _snprintf(args, sizeof(args) - 1, "--area-idx=%d", idx);
                        args[sizeof(args) - 1] = '\0';
                        ap_run_orchestrator(args);
                    }
                }

                /* A trampoline batch item was confirmed applied -- clear it
                 * from the pending queue and re-derive the armed set (an
                 * area whose whole batch just fired gets regenerated back
                 * to empty so it doesn't re-apply on the next visit). */
                const char *applied_marker = strstr(line, "AP|APPLIED|");
                if (applied_marker) {
                    char applied_name[128];
                    const char *name_start = applied_marker + strlen("AP|APPLIED|");
                    const char *bar = strchr(name_start, '|');
                    size_t name_len = bar ? (size_t)(bar - name_start) : strlen(name_start);
                    if (name_len >= sizeof(applied_name)) name_len = sizeof(applied_name) - 1;
                    memcpy(applied_name, name_start, name_len);
                    applied_name[name_len] = '\0';

                    int arm_id = ap_arm_id_for_name(applied_name);
                    if (arm_id != 0) {
                        char args[64];
                        _snprintf(args, sizeof(args) - 1, "--delivered=%d", arm_id);
                        args[sizeof(args) - 1] = '\0';
                        ap_run_orchestrator(args);
                    } else if (_stricmp(applied_name, "set_xp") == 0 || _stricmp(applied_name, "set_credits") == 0) {
                        /* Parameterized exact-value actions (see
                         * generate_trampoline_batch.py) aren't in the
                         * AP_ARM_NAMES table -- they're string-keyed in the
                         * orchestrator's queue, not numeric arm IDs. */
                        char args[64];
                        _snprintf(args, sizeof(args) - 1, "--delivered=%s", applied_name);
                        args[sizeof(args) - 1] = '\0';
                        ap_run_orchestrator(args);
                    } else if (_stricmp(applied_name, "give_item") == 0) {
                        /* give_item is resref-keyed, not a single replace-
                         * semantics slot like set_xp/set_credits -- several
                         * different items can be pending at once, so the
                         * confirmation line (AP|APPLIED|give_item|resref=X|
                         * count=Y|...) has to be parsed further to know
                         * WHICH pending entry just landed. */
                        const char *resref_marker = strstr(line, "|resref=");
                        if (resref_marker) {
                            const char *resref_start = resref_marker + strlen("|resref=");
                            const char *end = strchr(resref_start, '|');
                            size_t resref_len = end ? (size_t)(end - resref_start) : strlen(resref_start);
                            char resref[32];
                            if (resref_len >= sizeof(resref)) resref_len = sizeof(resref) - 1;
                            memcpy(resref, resref_start, resref_len);
                            resref[resref_len] = '\0';

                            char args[64];
                            _snprintf(args, sizeof(args) - 1, "--delivered=give_item:%s", resref);
                            args[sizeof(args) - 1] = '\0';
                            ap_run_orchestrator(args);
                        }
                    } else if (_stricmp(applied_name, "companion_class") == 0) {
                        /* Same shape as give_item above -- confirmation line
                         * is "AP|APPLIED|companion_class|name=X|class=Y",
                         * keyed further by the specific companion name (see
                         * build_companion_class_block). */
                        const char *name_marker = strstr(line, "|name=");
                        if (name_marker) {
                            const char *name_start = name_marker + strlen("|name=");
                            const char *end = strchr(name_start, '|');
                            size_t name_len2 = end ? (size_t)(end - name_start) : strlen(name_start);
                            char cname[32];
                            if (name_len2 >= sizeof(cname)) name_len2 = sizeof(cname) - 1;
                            memcpy(cname, name_start, name_len2);
                            cname[name_len2] = '\0';

                            char args[64];
                            _snprintf(args, sizeof(args) - 1, "--delivered=companion_class:%s", cname);
                            args[sizeof(args) - 1] = '\0';
                            ap_run_orchestrator(args);
                        }
                    }
                }
            }
        }
        last_pos = ftell(f);
        fclose(f);

        Sleep(300);
    }
    return 0;
}

/* Names with a heartbeat arm-ID go through the new mechanism: staging
 * copies the tiny ap_arm_<ID>.ncs (sets the MAIN_PLOT pending-ID global,
 * self-starts the heartbeat if not already running) into k_pend_modab.
 * The persistent heartbeat (started once, ticks forever via
 * self-rescheduling DelayCommand -- confirmed reliable over 7+ minutes and
 * across area transitions this session) picks up the ID within ~5 seconds
 * from wherever the player currently is and dispatches to the real,
 * fixed apply script via ExecuteScript. Delivery is no longer tied to
 * visiting any specific module -- only ARMING still requires one visit to
 * end_m01ab, matching the one proven-reliable native staging trigger. */
static const char *AP_ARM_NAMES[] = {
    "computer_use", "demolitions", "stealth", "awareness",
    "persuade", "repair", "security", "treat_injury",
    "companion_bastila", "companion_canderous",
    /* Slot 11 RETIRED (was feat_toughness) -- feats are left entirely to
     * normal in-game level-up choices now, never touched by AP. Same
     * rename-not-remove treatment as slots 15/16 below, for the same
     * positional-stability reason. */
    "xp", "_retired_feat_toughness",
    "class_guardian", "class_consular",
    /* Slots 15/16 RETIRED (were companion_jedi/companion_jedi_xp) --
     * confirmed AddMultiClass/GiveXPToCreature have zero effect on a
     * non-PC party member. Renamed rather than removed so array positions
     * (and every arm ID after this point) don't shift; the renamed strings
     * can never be matched by a real APPLY: command. */
    "_retired_companion_jedi", "_retired_companion_jedi_xp",
    "credits", "grant_test_ability",
    "companion_carth", "companion_hk47", "companion_jolee",
    "companion_juhani", "companion_mission", "companion_t3m4",
    "companion_zaalbar", "class_sentinel",
    "ability_strength", "ability_dexterity", "ability_constitution",
    "ability_intelligence", "ability_wisdom",
    "force_death",
    "dump_statblock", /* TEMPORARY (2026-08-31): Force Powers offset research,
                        * see kotor_engine_constraints memory / PHASE14.md.
                        * Retire (leave the gap) once the research pass is done. */
    "pc_class_soldier", "pc_class_scout", "pc_class_scoundrel", /* JediStart=
                        * random_class (2026-09-02), base-class roll only --
                        * see generate_trampoline_batch.py's APPLIES table. */
};
/* IDs must match AP_ARM_NAMES position (1-indexed). scripts/generate_trampoline_batch.py's
 * APPLIES table is the single source of truth this array is kept in sync
 * with by hand (generate_arm_scripts.py, the pre-trampoline-batch
 * generator this comment used to reference, was retired and deleted --
 * see PHASE12.md). */
#define AP_ARM_NAME_COUNT (sizeof(AP_ARM_NAMES) / sizeof(AP_ARM_NAMES[0]))

/* Older test-only scaffolding names that still use the original mechanism:
 * the named script's OWN logic is staged directly into k_pend_modab, no
 * arm-ID/heartbeat dispatch involved. Kept for diagnostics/one-off tests
 * that don't need to be reachable from the heartbeat's fixed dispatch
 * table. */
static const char *AP_APPLY_NAMES[] = {
    "verify_state", "xp_marker",
    "verify_companion",
    "heartbeat_test", "verify_globals", "simulate_quest_done", "test_suppress_cand",
    "prep_companions", "force_mission_party", "simulate_quest_xp",
    "verify_xp", "captest", "captest_read", "singletest",
    "localtest", "localtest_read", "grant_test_items", "remove_test_item",
    "verify_ability", "stress_bulk", "stress_bulk_nodelay",
    "pending_probe", "heartbeat_retest",
    "noop"
};
#define AP_APPLY_NAME_COUNT (sizeof(AP_APPLY_NAMES) / sizeof(AP_APPLY_NAMES[0]))

/* Game dir is never hardcoded -- discovered the same way ap_apply() already
 * did further below (GetModuleFileNameA(NULL, ...) on the main EXE, then
 * strip the filename), so this works for any player's install location. */
static int ap_get_game_dir(char *out, size_t outsize) {
    char exe_path[MAX_PATH];
    DWORD n = GetModuleFileNameA(NULL, exe_path, MAX_PATH);
    if (n == 0 || n >= MAX_PATH) return 0;
    char *last_slash = strrchr(exe_path, '\\');
    if (!last_slash) return 0;
    *last_slash = '\0';
    if (strlen(exe_path) >= outsize) return 0;
    strcpy(out, exe_path);
    return 1;
}

/* Unlike GameDir, this project's own repo root (where scripts/
 * arm_orchestrator.py actually lives) has no fixed relationship to the game
 * install at all -- it's wherever a player put their checkout. install.ps1
 * writes it to a one-line text file next to the installed DLL
 * (GameDir\ap_repo_root.txt) at -Install time; read it fresh on every call
 * rather than caching, since it's cheap and this way a re-run of
 * install.ps1 against a moved checkout takes effect without a game
 * restart. */
static int ap_get_orchestrator_path(char *out, size_t outsize) {
    char game_dir[MAX_PATH];
    if (!ap_get_game_dir(game_dir, sizeof(game_dir))) return 0;

    char config_path[MAX_PATH];
    _snprintf(config_path, sizeof(config_path) - 1, "%s\\ap_repo_root.txt", game_dir);
    config_path[sizeof(config_path) - 1] = '\0';

    FILE *f = fopen(config_path, "r");
    if (!f) {
        ap_log("ap_get_orchestrator_path: %s not found -- re-run extender\\install.ps1 -Install to write it.", config_path);
        return 0;
    }
    char repo_root[MAX_PATH];
    int ok = fgets(repo_root, sizeof(repo_root), f) != NULL;
    fclose(f);
    if (!ok) {
        ap_log("ap_get_orchestrator_path: %s is empty.", config_path);
        return 0;
    }
    size_t len = strlen(repo_root);
    while (len > 0 && (repo_root[len - 1] == '\n' || repo_root[len - 1] == '\r')) {
        repo_root[--len] = '\0';
    }

    _snprintf(out, outsize - 1, "%s\\scripts\\arm_orchestrator.py", repo_root);
    out[outsize - 1] = '\0';
    return 1;
}

/* Shells out to the Python arm-batch orchestrator (scripts/arm_orchestrator.py)
 * synchronously -- it owns the connectivity graph, the pending-queue/armed-
 * state JSON files, and the actual trampoline regenerate+recompile+deploy
 * work (reusing generate_trampoline_batch.py). Recompiling a handful of
 * areas takes well under a second in practice, so a synchronous call from
 * the socket-handling thread or the log-tail thread is fine -- it does not
 * block the game itself, only this extender's own worker threads. */
static void ap_run_orchestrator(const char *args) {
    char orchestrator_path[MAX_PATH];
    char game_dir[MAX_PATH];
    if (!ap_get_orchestrator_path(orchestrator_path, sizeof(orchestrator_path)) ||
        !ap_get_game_dir(game_dir, sizeof(game_dir))) {
        ap_log("ap_run_orchestrator: could not resolve orchestrator/game paths, skipping '%s'.", args);
        return;
    }

    char cmdline[1024];
    _snprintf(cmdline, sizeof(cmdline) - 1, "python \"%s\" %s --game-dir=\"%s\"", orchestrator_path, args, game_dir);
    cmdline[sizeof(cmdline) - 1] = '\0';

    EnterCriticalSection(&g_orchestrator_lock);

    SECURITY_ATTRIBUTES sa;
    ZeroMemory(&sa, sizeof(sa));
    sa.nLength = sizeof(sa);
    sa.bInheritHandle = TRUE;

    HANDLE hReadPipe = NULL, hWritePipe = NULL;
    if (!CreatePipe(&hReadPipe, &hWritePipe, &sa, 0)) {
        ap_log("ap_run_orchestrator: CreatePipe failed, err=%lu -- running '%s' unmonitored.",
               GetLastError(), args);
        hReadPipe = hWritePipe = NULL;
    } else {
        /* our own read end must never be inherited by the child, or its
         * write end never sees EOF (the read end would stay open via the
         * child's inherited copy even after the child exits). */
        SetHandleInformation(hReadPipe, HANDLE_FLAG_INHERIT, 0);
    }

    STARTUPINFOA si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;
    if (hWritePipe) {
        si.dwFlags |= STARTF_USESTDHANDLES;
        si.hStdOutput = hWritePipe;
        si.hStdError = hWritePipe;
        si.hStdInput = NULL;
    }
    ZeroMemory(&pi, sizeof(pi));

    BOOL inheritHandles = hWritePipe ? TRUE : FALSE;
    if (!CreateProcessA(NULL, cmdline, NULL, NULL, inheritHandles, CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) {
        ap_log("ap_run_orchestrator: CreateProcess failed, err=%lu, cmdline=%s", GetLastError(), cmdline);
        if (hReadPipe) CloseHandle(hReadPipe);
        if (hWritePipe) CloseHandle(hWritePipe);
        LeaveCriticalSection(&g_orchestrator_lock);
        return;
    }

    /* our copy of the write end must close now -- otherwise ReadFile below
     * blocks forever, since the pipe never reports EOF while ANY write
     * handle (ours or the child's) is still open. */
    if (hWritePipe) CloseHandle(hWritePipe);

    char outbuf[4096];
    size_t outlen = 0;
    if (hReadPipe) {
        char chunk[512];
        DWORD nread = 0;
        while (ReadFile(hReadPipe, chunk, sizeof(chunk), &nread, NULL) && nread > 0) {
            size_t copy = nread;
            if (outlen + copy > sizeof(outbuf) - 1) copy = sizeof(outbuf) - 1 - outlen;
            if (copy > 0) {
                memcpy(outbuf + outlen, chunk, copy);
                outlen += copy;
            }
            if (outlen >= sizeof(outbuf) - 1) break; /* keep draining below so the child doesn't block on a full pipe */
        }
        /* drain and discard anything past our cap so the child can still exit */
        char discard[512];
        DWORD ndiscard = 0;
        while (ReadFile(hReadPipe, discard, sizeof(discard), &ndiscard, NULL) && ndiscard > 0) { }
    }
    outbuf[outlen] = '\0';

    WaitForSingleObject(pi.hProcess, 15000); /* generous cap -- a handful of recompiles, not 78 */
    DWORD exitCode = 0;
    GetExitCodeProcess(pi.hProcess, &exitCode);
    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);
    if (hReadPipe) CloseHandle(hReadPipe);
    LeaveCriticalSection(&g_orchestrator_lock);

    if (exitCode != 0) {
        ap_log("ap_run_orchestrator: FAILED (exit=%lu) args='%s'\n----- orchestrator output -----\n%s\n--------------------------------",
               exitCode, args, outlen ? outbuf : "(no output captured)");
    } else {
        ap_log("ap_run_orchestrator: ran '%s' (exit=0)", args);
    }
}

/* name -> arm ID lookup, shared by ap_apply() (queuing a new check) and the
 * kse-log-tail thread (mapping an AP|APPLIED|<name>|... confirmation line
 * back to the ID to clear from the pending queue). */
static int ap_arm_id_for_name(const char *name) {
    for (size_t i = 0; i < AP_ARM_NAME_COUNT; i++) {
        if (_stricmp(name, AP_ARM_NAMES[i]) == 0) return (int)(i + 1);
    }
    return 0;
}

static int ap_apply(const char *name, char *reply, size_t reply_size) {
    int arm_id = ap_arm_id_for_name(name); /* 1-indexed, 0 = not an arm name */

    int known = (arm_id != 0);
    if (!known) {
        for (size_t i = 0; i < AP_APPLY_NAME_COUNT; i++) {
            if (_stricmp(name, AP_APPLY_NAMES[i]) == 0) { known = 1; break; }
        }
    }
    if (!known) {
        _snprintf(reply, reply_size - 1, "ERROR:unknown item '%s'\n", name);
        return 0;
    }

    /* Real arm-ID names go entirely through the orchestrator now (regenerates
     * the player's current area + its direct neighbors -- see
     * scripts/arm_orchestrator.py -- so delivery isn't gated to end_m01ab at
     * all). The old k_pend_modab single-slot staging below is kept ONLY for
     * the legacy AP_APPLY_NAMES diagnostic scaffolding, which has no arm ID
     * and no orchestrator equivalent. Removed for arm_id != 0 after
     * confirming the two paths could race (both delivering the same item,
     * harmlessly deduped, but redundant now that the new path covers
     * end_m01ab too as area index 1). */
    if (arm_id != 0) {
        char args[64];
        _snprintf(args, sizeof(args) - 1, "--queue-add=%d", arm_id);
        args[sizeof(args) - 1] = '\0';
        ap_run_orchestrator(args);
        ap_log("ap_apply(%s): queued arm_id=%d via orchestrator.", name, arm_id);
        _snprintf(reply, reply_size - 1, "STAGED:%s\n", name);
        return 1;
    }

    char exe_path[MAX_PATH];
    DWORD n = GetModuleFileNameA(NULL, exe_path, MAX_PATH);
    if (n == 0 || n >= MAX_PATH) {
        _snprintf(reply, reply_size - 1, "ERROR:could not resolve game path\n");
        return 0;
    }
    char *last_slash = strrchr(exe_path, '\\');
    if (last_slash) *last_slash = '\0';

    char src[MAX_PATH];
    char dst[MAX_PATH];
    _snprintf(src, MAX_PATH - 1, "%s\\Override\\ap_library\\ap_apply_%s.ncs", exe_path, name);
    src[MAX_PATH - 1] = '\0';
    if (_stricmp(name, "noop") == 0) {
        _snprintf(src, MAX_PATH - 1, "%s\\Override\\ap_library\\ap_noop.ncs", exe_path);
        src[MAX_PATH - 1] = '\0';
    }
    /* k_pend_modab is end_m01ab's real Mod_OnModLoad hook -- the engine
     * re-reads it fresh on every native module-load event, including repeat
     * visits. Fine for this legacy diagnostic-only path since it's never
     * used for real gameplay delivery. */
    _snprintf(dst, MAX_PATH - 1, "%s\\Override\\k_pend_modab.ncs", exe_path);
    dst[MAX_PATH - 1] = '\0';

    if (!CopyFileA(src, dst, FALSE)) {
        DWORD err = GetLastError();
        ap_log("ap_apply(%s): CopyFile failed, err=%lu (%s -> %s)", name, err, src, dst);
        _snprintf(reply, reply_size - 1, "ERROR:copy failed (%lu)\n", err);
        return 0;
    }

    ap_log("ap_apply(%s): staged %s -> %s (legacy end_m01ab-only diagnostic path).", name, src, dst);
    _snprintf(reply, reply_size - 1, "STAGED:%s\n", name);
    return 1;
}

/* Memory scanner -- this extender runs INSIDE the game process, so it has
 * full read access to the whole address space already. Given a short exact
 * byte sequence (e.g. our 8 known skill ranks in SKILL_* index order), scans
 * committed, writable, private memory for it and dumps a hex context window
 * around each hit to a file, so we can visually identify neighboring fields
 * (class byte, XP int, etc.) without needing an external debugger at all. */
#define AP_SCAN_MAX_MATCHES 60
#define AP_SCAN_CONTEXT 128

static int ap_parse_byte_list(const char *s, unsigned char *out, int max_len) {
    int count = 0;
    const char *p = s;
    while (*p && count < max_len) {
        int val = atoi(p);
        out[count++] = (unsigned char)(val & 0xFF);
        while (*p && *p != ',') p++;
        if (*p == ',') p++;
    }
    return count;
}

static void ap_hexdump_region(FILE *out, const unsigned char *ctx_start, size_t ctx_len) {
    for (size_t j = 0; j < ctx_len; j += 16) {
        fprintf(out, "%p: ", (void *)(ctx_start + j));
        size_t line_len = (ctx_len - j < 16) ? (ctx_len - j) : 16;
        size_t k;
        for (k = 0; k < line_len; k++) fprintf(out, "%02X ", ctx_start[j + k]);
        for (; k < 16; k++) fprintf(out, "   ");
        fprintf(out, " ");
        for (k = 0; k < line_len; k++) {
            unsigned char c = ctx_start[j + k];
            fputc((c >= 32 && c < 127) ? c : '.', out);
        }
        fprintf(out, "\n");
    }
}

static int ap_scan_bytes(const unsigned char *pattern, size_t pattern_len, char *reply, size_t reply_size) {
    char dir[MAX_PATH];
    strcpy(dir, g_log_path);
    char *slash = strrchr(dir, '\\');
    if (slash) *slash = '\0';

    char report_path[MAX_PATH];
    _snprintf(report_path, MAX_PATH - 1, "%s\\scan_results.txt", dir);
    report_path[MAX_PATH - 1] = '\0';

    FILE *out = fopen(report_path, "w");
    if (!out) {
        _snprintf(reply, reply_size - 1, "ERROR:could not open %s\n", report_path);
        return 0;
    }

    fprintf(out, "Scanning for %zu-byte pattern:", pattern_len);
    for (size_t i = 0; i < pattern_len; i++) fprintf(out, " %02X", pattern[i]);
    fprintf(out, "\n\n");

    int matches = 0;
    long regions_scanned = 0;
    long regions_queried = 0;
    unsigned __int64 bytes_scanned = 0;
    SYSTEM_INFO si;
    GetSystemInfo(&si);
    unsigned char *scan_addr = (unsigned char *)si.lpMinimumApplicationAddress;
    unsigned char *max_addr = (unsigned char *)si.lpMaximumApplicationAddress;
    MEMORY_BASIC_INFORMATION mbi;

    while (scan_addr < max_addr && matches < AP_SCAN_MAX_MATCHES) {
        if (VirtualQuery(scan_addr, &mbi, sizeof(mbi)) == 0) {
            /* Don't abort the whole scan on one bad query -- skip a page and
             * keep going, so a single problem region can't hide everything
             * after it. */
            scan_addr += 0x1000;
            continue;
        }
        regions_queried++;

        /* Readable in any form -- for a string-literal search (e.g. a
         * global's NAME, as opposed to its mutable VALUE) the match is more
         * likely in a read-only data section than a writable one. */
        int readable = (mbi.Protect == PAGE_READWRITE) || (mbi.Protect == PAGE_WRITECOPY)
            || (mbi.Protect == PAGE_EXECUTE_READWRITE) || (mbi.Protect == PAGE_READONLY)
            || (mbi.Protect == PAGE_EXECUTE_READ) || (mbi.Protect == PAGE_EXECUTE_WRITECOPY);

        if (mbi.State == MEM_COMMIT && (mbi.Type == MEM_PRIVATE || mbi.Type == MEM_IMAGE || mbi.Type == MEM_MAPPED) && readable
            && mbi.RegionSize > pattern_len) {
            regions_scanned++;
            bytes_scanned += mbi.RegionSize;
            unsigned char *region_start = (unsigned char *)mbi.BaseAddress;
            SIZE_T region_size = mbi.RegionSize;

            for (SIZE_T i = 0; i + pattern_len <= region_size && matches < AP_SCAN_MAX_MATCHES; i++) {
                if (memcmp(region_start + i, pattern, pattern_len) == 0) {
                    unsigned char *match_addr = region_start + i;
                    matches++;

                    fprintf(out, "=== match %d at %p ===\n", matches, (void *)match_addr);
                    SIZE_T ctx_before = (i >= AP_SCAN_CONTEXT) ? AP_SCAN_CONTEXT : i;
                    unsigned char *ctx_start = match_addr - ctx_before;
                    SIZE_T ctx_len = ctx_before + pattern_len + AP_SCAN_CONTEXT;
                    if ((SIZE_T)(ctx_start - region_start) + ctx_len > region_size) {
                        ctx_len = region_size - (ctx_start - region_start);
                    }
                    fprintf(out, "  (pattern starts %zu bytes into this dump)\n", (size_t)ctx_before);
                    ap_hexdump_region(out, ctx_start, ctx_len);
                    fprintf(out, "\n");
                }
            }
        }

        scan_addr = (unsigned char *)mbi.BaseAddress + mbi.RegionSize;
    }

    fprintf(out, "--- coverage: %ld regions queried, %ld writable+private regions scanned, "
        "%llu bytes scanned ---\n", regions_queried, regions_scanned, bytes_scanned);
    fclose(out);
    ap_log("ap_scan_bytes: %d matches, %ld/%ld regions, %llu bytes -> %s",
        matches, regions_scanned, regions_queried, bytes_scanned, report_path);
    _snprintf(reply, reply_size - 1, "SCANNED:%d matches -> %s\n", matches, report_path);
    return matches;
}

/* Dumps every committed, writable, private memory region to a binary file:
 * repeated [address:u32][size:u32][data:size bytes], terminated by a
 * [0][0] record. This is the raw material for proper before/after diffing
 * -- much more precise than pattern search, since it finds every byte that
 * actually changed rather than guessing at a value shape. */
static int ap_snapshot(const char *name, char *reply, size_t reply_size) {
    char dir[MAX_PATH];
    strcpy(dir, g_log_path);
    char *slash = strrchr(dir, '\\');
    if (slash) *slash = '\0';

    char snap_path[MAX_PATH];
    _snprintf(snap_path, MAX_PATH - 1, "%s\\snap_%s.bin", dir, name);
    snap_path[MAX_PATH - 1] = '\0';

    FILE *out = fopen(snap_path, "wb");
    if (!out) {
        _snprintf(reply, reply_size - 1, "ERROR:could not open %s\n", snap_path);
        return 0;
    }

    long region_count = 0;
    unsigned __int64 bytes_written = 0;
    SYSTEM_INFO si;
    GetSystemInfo(&si);
    unsigned char *scan_addr = (unsigned char *)si.lpMinimumApplicationAddress;
    unsigned char *max_addr = (unsigned char *)si.lpMaximumApplicationAddress;
    MEMORY_BASIC_INFORMATION mbi;

    while (scan_addr < max_addr) {
        if (VirtualQuery(scan_addr, &mbi, sizeof(mbi)) == 0) {
            scan_addr += 0x1000;
            continue;
        }

        int writable = (mbi.Protect == PAGE_READWRITE) || (mbi.Protect == PAGE_WRITECOPY)
            || (mbi.Protect == PAGE_EXECUTE_READWRITE);

        if (mbi.State == MEM_COMMIT && (mbi.Type == MEM_PRIVATE || mbi.Type == MEM_IMAGE) && writable) {
            unsigned __int32 addr32 = (unsigned __int32)(UINT_PTR)mbi.BaseAddress;
            unsigned __int32 size32 = (unsigned __int32)mbi.RegionSize;
            fwrite(&addr32, sizeof(addr32), 1, out);
            fwrite(&size32, sizeof(size32), 1, out);
            fwrite(mbi.BaseAddress, 1, mbi.RegionSize, out);
            region_count++;
            bytes_written += mbi.RegionSize;
        }

        scan_addr = (unsigned char *)mbi.BaseAddress + mbi.RegionSize;
    }

    unsigned __int32 zero = 0;
    fwrite(&zero, sizeof(zero), 1, out);
    fwrite(&zero, sizeof(zero), 1, out);
    fclose(out);

    ap_log("ap_snapshot(%s): %ld regions, %llu bytes -> %s", name, region_count, bytes_written, snap_path);
    _snprintf(reply, reply_size - 1, "SNAPSHOT:%s %ld regions, %llu bytes\n", name, region_count, bytes_written);
    return 1;
}

/* WRITEBYTE:<addr_hex>:<value> -- pokes a single byte directly into the
 * game's own process memory (we're already loaded in-process, so this is
 * just a pointer write, no cross-process API needed). Used to test/confirm
 * a candidate address found via SNAPSHOT diffing actually IS a given
 * NWScript global's storage before relying on it for real. Re-validates the
 * page is still committed+writable+private via VirtualQuery immediately
 * before writing, since the candidate address was found in an earlier
 * snapshot and the underlying allocation could have changed since. */
static int ap_write_byte(unsigned __int32 addr, unsigned char value, char *reply, size_t reply_size) {
    unsigned char *p = (unsigned char *)(UINT_PTR)addr;
    MEMORY_BASIC_INFORMATION mbi;
    if (VirtualQuery(p, &mbi, sizeof(mbi)) == 0) {
        _snprintf(reply, reply_size - 1, "ERROR:VirtualQuery failed at 0x%08X\n", addr);
        reply[reply_size - 1] = '\0';
        return 0;
    }
    int writable = (mbi.Protect == PAGE_READWRITE) || (mbi.Protect == PAGE_WRITECOPY)
        || (mbi.Protect == PAGE_EXECUTE_READWRITE);
    if (mbi.State != MEM_COMMIT || mbi.Type != MEM_PRIVATE || !writable) {
        _snprintf(reply, reply_size - 1, "ERROR:0x%08X not committed+writable+private (state=%lu type=%lu protect=%lu)\n",
            addr, mbi.State, mbi.Type, mbi.Protect);
        reply[reply_size - 1] = '\0';
        return 0;
    }
    unsigned char before = *p;
    *p = value;
    ap_log("ap_write_byte: 0x%08X %02X -> %02X", addr, before, value);
    _snprintf(reply, reply_size - 1, "WROTE:0x%08X %02X->%02X\n", addr, before, value);
    reply[reply_size - 1] = '\0';
    return 1;
}

static int ap_read_byte(unsigned __int32 addr, char *reply, size_t reply_size) {
    unsigned char *p = (unsigned char *)(UINT_PTR)addr;
    MEMORY_BASIC_INFORMATION mbi;
    if (VirtualQuery(p, &mbi, sizeof(mbi)) == 0) {
        _snprintf(reply, reply_size - 1, "ERROR:VirtualQuery failed at 0x%08X\n", addr);
        reply[reply_size - 1] = '\0';
        return 0;
    }
    if (mbi.State != MEM_COMMIT) {
        _snprintf(reply, reply_size - 1, "ERROR:0x%08X not committed\n", addr);
        reply[reply_size - 1] = '\0';
        return 0;
    }
    _snprintf(reply, reply_size - 1, "READ:0x%08X=%02X\n", addr, *p);
    reply[reply_size - 1] = '\0';
    return 1;
}

/* DUMPMEM:<addr_hex>:<size> -- raw hex dump of an arbitrary memory range to
 * a file, no filtering by region type/protection (VirtualQuery only used to
 * cap the dump at the containing region's end so we don't read into an
 * unmapped page). Used to inspect the full structure around a location
 * found via SCANBYTES, beyond that command's +-128 byte context window. */
static int ap_dump_mem(unsigned __int32 addr, unsigned int size, char *reply, size_t reply_size) {
    unsigned char *p = (unsigned char *)(UINT_PTR)addr;
    MEMORY_BASIC_INFORMATION mbi;
    if (VirtualQuery(p, &mbi, sizeof(mbi)) == 0 || mbi.State != MEM_COMMIT) {
        _snprintf(reply, reply_size - 1, "ERROR:0x%08X not committed\n", addr);
        reply[reply_size - 1] = '\0';
        return 0;
    }
    unsigned char *region_end = (unsigned char *)mbi.BaseAddress + mbi.RegionSize;
    if (p + size > region_end) size = (unsigned int)(region_end - p);

    char dir[MAX_PATH];
    strcpy(dir, g_log_path);
    char *slash = strrchr(dir, '\\');
    if (slash) *slash = '\0';
    char dump_path[MAX_PATH];
    _snprintf(dump_path, MAX_PATH - 1, "%s\\dump_%08X.txt", dir, addr);
    dump_path[MAX_PATH - 1] = '\0';

    FILE *out = fopen(dump_path, "w");
    if (!out) {
        _snprintf(reply, reply_size - 1, "ERROR:could not open %s\n", dump_path);
        reply[reply_size - 1] = '\0';
        return 0;
    }
    for (unsigned int j = 0; j < size; j += 16) {
        fprintf(out, "%p: ", (void *)(p + j));
        unsigned int line_len = (size - j < 16) ? (size - j) : 16;
        unsigned int k;
        for (k = 0; k < line_len; k++) fprintf(out, "%02X ", p[j + k]);
        for (; k < 16; k++) fprintf(out, "   ");
        fprintf(out, " ");
        for (k = 0; k < line_len; k++) {
            unsigned char c = p[j + k];
            fputc((c >= 32 && c < 127) ? c : '.', out);
        }
        fprintf(out, "\n");
    }
    fclose(out);
    _snprintf(reply, reply_size - 1, "DUMPED:%u bytes -> %s\n", size, dump_path);
    reply[reply_size - 1] = '\0';
    return 1;
}

/* Dispatches one already-delimited command line (no trailing \r\n) and
 * writes the reply into reply[reply_size]. Split out of ap_handle_client so
 * the line-framing loop there can call it once per complete line, however
 * many recv() calls it took to arrive -- see the comment on g_linebuf in
 * ap_handle_client for why that split matters. */
static void ap_dispatch_command(char *buf, char *reply, size_t reply_size) {
    if (_strnicmp(buf, "APPLY:", 6) == 0) {
        ap_apply(buf + 6, reply, reply_size);
    } else if (_strnicmp(buf, "APPLYVALUE:", 11) == 0) {
        /* APPLYVALUE:<action>:<...> -- parameterized actions, distinct
         * from APPLY:'s fixed-increment arm names. See
         * generate_trampoline_batch.py. Two shapes: set_xp/set_credits
         * take a single int (APPLYVALUE:set_xp:<value>); give_item takes
         * a resref and a count (APPLYVALUE:give_item:<resref>:<count>) --
         * parsed separately since the two shapes differ. */
        const char *rest = buf + 11;
        const char *colon = strchr(rest, ':');
        char action[32];
        int matched = 0;
        if (colon && (size_t)(colon - rest) < sizeof(action)) {
            size_t action_len = (size_t)(colon - rest);
            memcpy(action, rest, action_len);
            action[action_len] = '\0';
            const char *after_action = colon + 1;

            if (_stricmp(action, "give_item") == 0) {
                char resref[32];
                int count = 0;
                if (sscanf(after_action, "%31[^:]:%d", resref, &count) == 2 && count > 0) {
                    matched = 1;
                    char args[80];
                    _snprintf(args, sizeof(args) - 1, "--queue-give-item=%s:%d", resref, count);
                    args[sizeof(args) - 1] = '\0';
                    ap_run_orchestrator(args);
                    ap_log("APPLYVALUE: queued give_item %s x%d via orchestrator.", resref, count);
                    _snprintf(reply, reply_size - 1, "STAGED:give_item:%s:%d\n", resref, count);
                    reply[reply_size - 1] = '\0';
                }
            } else if (_stricmp(action, "companion_class") == 0) {
                /* companion_class:<name>:<class_name> -- RandomizeClass
                 * (Options.py). Both fields are short fixed vocab (companion
                 * keys / class names, see generate_trampoline_batch.py's
                 * _COMPANION_TAGS / _CLASS_NAME_TO_CONST), so a generous
                 * bound is plenty and this doesn't need count-style numeric
                 * parsing like give_item. */
                char name[32];
                char class_name[16];
                if (sscanf(after_action, "%31[^:]:%15s", name, class_name) == 2) {
                    matched = 1;
                    char args[80];
                    _snprintf(args, sizeof(args) - 1, "--queue-companion-class=%s:%s", name, class_name);
                    args[sizeof(args) - 1] = '\0';
                    ap_run_orchestrator(args);
                    ap_log("APPLYVALUE: queued companion_class %s:%s via orchestrator.", name, class_name);
                    _snprintf(reply, reply_size - 1, "STAGED:companion_class:%s:%s\n", name, class_name);
                    reply[reply_size - 1] = '\0';
                }
            } else if (_stricmp(action, "set_xp") == 0 || _stricmp(action, "set_credits") == 0) {
                int value = atoi(after_action);
                matched = 1;
                /* Orchestrator flags are hyphenated (--queue-set-xp=,
                 * --queue-set-credits=), not the underscored action name
                 * directly -- build the exact flag rather than substituting. */
                char args[64];
                if (_stricmp(action, "set_xp") == 0) {
                    _snprintf(args, sizeof(args) - 1, "--queue-set-xp=%d", value);
                } else {
                    _snprintf(args, sizeof(args) - 1, "--queue-set-credits=%d", value);
                }
                args[sizeof(args) - 1] = '\0';
                ap_run_orchestrator(args);
                ap_log("APPLYVALUE: queued %s=%d via orchestrator.", action, value);
                _snprintf(reply, reply_size - 1, "STAGED:%s:%d\n", action, value);
                reply[reply_size - 1] = '\0';
            }
        }
        if (!matched) {
            _snprintf(reply, reply_size - 1, "ERROR:expected APPLYVALUE:set_xp|set_credits:<value> or give_item:<resref>:<count>\n");
            reply[reply_size - 1] = '\0';
        }
    } else if (_strnicmp(buf, "SHOPSTOCK:", 10) == 0) {
        /* SHOPSTOCK:<resref1>,<resref2>,... -- one-time, set-once-at-Connect
         * universal shop catalog (see Options.py's ShopItemCount and
         * __init__.py's fill_slot_data "shop_stock"). Not a queued grant --
         * forwarded straight through to the orchestrator, which persists it
         * to _shop_stock.json and force-regenerates the current armed scope
         * so it takes effect without waiting for the next area transition. */
        const char *resrefs = buf + 10;
        char args[700];
        _snprintf(args, sizeof(args) - 1, "--set-shop-stock=%s", resrefs);
        args[sizeof(args) - 1] = '\0';
        ap_run_orchestrator(args);
        ap_log("SHOPSTOCK: set shop catalog via orchestrator.");
        _snprintf(reply, reply_size - 1, "STAGED:shopstock\n");
        reply[reply_size - 1] = '\0';
    } else if (_strnicmp(buf, "NOTIFY:", 7) == 0) {
        /* NOTIFY:<text> -- one-shot on-screen message (check found / item
         * received), baked into whatever area is currently armed via
         * --queue-notify=. Not a queued grant like APPLY:/APPLYVALUE: --
         * purely cosmetic, nothing to reconcile if it's ever lost, so no
         * delivery confirmation path exists for it (see
         * arm_orchestrator.py's _pending_notify.json for how repeats
         * across multiple area regenerates before the next real
         * transition are avoided). */
        const char *text = buf + 7;
        char args[512];
        _snprintf(args, sizeof(args) - 1, "--queue-notify=%s", text);
        args[sizeof(args) - 1] = '\0';
        ap_run_orchestrator(args);
        ap_log("NOTIFY: queued on-screen message via orchestrator.");
        _snprintf(reply, reply_size - 1, "STAGED:notify\n");
        reply[reply_size - 1] = '\0';
    } else if (_strnicmp(buf, "SCANBYTES:", 10) == 0) {
        unsigned char pattern[64];
        int len = ap_parse_byte_list(buf + 10, pattern, sizeof(pattern));
        if (len < 2) {
            _snprintf(reply, reply_size - 1, "ERROR:need at least 2 bytes\n");
            reply[reply_size - 1] = '\0';
        } else {
            ap_scan_bytes(pattern, (size_t)len, reply, reply_size);
        }
    } else if (_strnicmp(buf, "SNAPSHOT:", 9) == 0) {
        ap_snapshot(buf + 9, reply, reply_size);
    } else if (_strnicmp(buf, "WRITEBYTE:", 10) == 0) {
        unsigned __int32 addr = 0;
        unsigned int value = 0;
        if (sscanf(buf + 10, "%x:%u", &addr, &value) == 2) {
            ap_write_byte(addr, (unsigned char)(value & 0xFF), reply, reply_size);
        } else {
            _snprintf(reply, reply_size - 1, "ERROR:expected WRITEBYTE:<hexaddr>:<value>\n");
            reply[reply_size - 1] = '\0';
        }
    } else if (_strnicmp(buf, "DUMPMEM:", 8) == 0) {
        unsigned __int32 addr = 0;
        unsigned int size = 0;
        if (sscanf(buf + 8, "%x:%u", &addr, &size) == 2) {
            ap_dump_mem(addr, size, reply, reply_size);
        } else {
            _snprintf(reply, reply_size - 1, "ERROR:expected DUMPMEM:<hexaddr>:<size>\n");
            reply[reply_size - 1] = '\0';
        }
    } else if (_strnicmp(buf, "READBYTE:", 9) == 0) {
        unsigned __int32 addr = 0;
        if (sscanf(buf + 9, "%x", &addr) == 1) {
            ap_read_byte(addr, reply, reply_size);
        } else {
            _snprintf(reply, reply_size - 1, "ERROR:expected READBYTE:<hexaddr>\n");
            reply[reply_size - 1] = '\0';
        }
    } else {
        _snprintf(reply, reply_size - 1, "ACK:%s\n", buf);
        reply[reply_size - 1] = '\0';
    }
}

/* recv() has no concept of message boundaries -- it can return anywhere
 * from a partial line to several lines' worth of bytes in one call
 * (confirmed live: 6 rapid-fire APPLY:/APPLYVALUE: commands sent by the
 * client within the same asyncio tick coalesced into a single recv(),
 * silently losing 5 of the 6 items when the old code treated the whole
 * blob as one command name). Accumulate into linebuf across calls and
 * dispatch exactly once per complete '\n'-terminated line, carrying any
 * trailing partial line over to the next recv(). */
static void ap_handle_client(SOCKET client) {
    char linebuf[2048];
    size_t linelen = 0;
    char chunk[512];

    EnterCriticalSection(&g_client_lock);
    g_client = client;
    LeaveCriticalSection(&g_client_lock);

    ap_log("Client connected.");
    while (!g_shutdown) {
        int n = recv(client, chunk, sizeof(chunk), 0);
        if (n <= 0) break;

        for (int i = 0; i < n; i++) {
            char c = chunk[i];
            if (c == '\n') {
                if (linelen > 0 && linebuf[linelen - 1] == '\r') linelen--;
                linebuf[linelen] = '\0';
                if (linelen > 0) {
                    ap_log("RECV: %s", linebuf);
                    char reply[600];
                    reply[0] = '\0';
                    ap_dispatch_command(linebuf, reply, sizeof(reply));
                    send(client, reply, (int)strlen(reply), 0);
                    ap_log("SENT: %s", reply);
                }
                linelen = 0;
            } else if (linelen < sizeof(linebuf) - 1) {
                linebuf[linelen++] = c;
            } else {
                /* Line too long for the buffer -- drop it rather than
                 * silently truncating into something that looks valid. */
                ap_log("RECV: line exceeded %zu bytes, dropping.", sizeof(linebuf) - 1);
                linelen = 0;
            }
        }
    }

    EnterCriticalSection(&g_client_lock);
    if (g_client == client) g_client = INVALID_SOCKET;
    LeaveCriticalSection(&g_client_lock);

    ap_log("Client disconnected.");
    closesocket(client);
}

static DWORD WINAPI ap_server_thread(LPVOID unused) {
    (void)unused;
    ap_init_log_path();
    InitializeCriticalSection(&g_log_lock);
    InitializeCriticalSection(&g_client_lock);
    InitializeCriticalSection(&g_orchestrator_lock);
    ap_log("=== KotOR AP test extender starting (PID %lu) ===", GetCurrentProcessId());

    WSADATA wsa;
    if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0) {
        ap_log("WSAStartup failed: %d", WSAGetLastError());
        return 1;
    }

    SOCKET listener = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (listener == INVALID_SOCKET) {
        ap_log("socket() failed: %d", WSAGetLastError());
        WSACleanup();
        return 1;
    }

    int reuse = 1;
    setsockopt(listener, SOL_SOCKET, SO_REUSEADDR, (const char *)&reuse, sizeof(reuse));

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = inet_addr("127.0.0.1");
    addr.sin_port = htons(AP_EXTENDER_PORT);

    if (bind(listener, (struct sockaddr *)&addr, sizeof(addr)) == SOCKET_ERROR) {
        ap_log("bind() failed: %d", WSAGetLastError());
        closesocket(listener);
        WSACleanup();
        return 1;
    }

    if (listen(listener, 4) == SOCKET_ERROR) {
        ap_log("listen() failed: %d", WSAGetLastError());
        closesocket(listener);
        WSACleanup();
        return 1;
    }

    ap_log("Listening on 127.0.0.1:%d", AP_EXTENDER_PORT);

    /* Log-tailer runs on its own thread so it isn't blocked by accept(). */
    CreateThread(NULL, 0, ap_kse_log_tail_thread, NULL, 0, NULL);

    while (!g_shutdown) {
        struct sockaddr_in client_addr;
        int client_addr_len = sizeof(client_addr);
        SOCKET client = accept(listener, (struct sockaddr *)&client_addr, &client_addr_len);
        if (client == INVALID_SOCKET) {
            if (g_shutdown) break;
            ap_log("accept() failed: %d", WSAGetLastError());
            continue;
        }
        ap_handle_client(client);
    }

    closesocket(listener);
    WSACleanup();
    ap_log("=== extender thread exiting ===");
    return 0;
}

/* Entry points called from the merged dllmain.cpp (K1SE's, extended) --
 * this module no longer has its own DllMain. ap_extender_start() is called
 * from DLL_PROCESS_ATTACH (spawns ap_server_thread, same as the old DllMain
 * did directly); ap_extender_shutdown() is called from DLL_PROCESS_DETACH
 * (same InterlockedExchange the old DllMain did directly). Both declared
 * extern "C" here so the C++ side can call them without name mangling. */
void ap_extender_start(void) {
    CreateThread(NULL, 0, ap_server_thread, NULL, 0, NULL);
}

void ap_extender_shutdown(void) {
    InterlockedExchange(&g_shutdown, 1);
}
