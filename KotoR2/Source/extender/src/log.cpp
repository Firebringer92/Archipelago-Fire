#include "log.h"

#include <windows.h>
#include <cstdarg>
#include <cstdio>
#include <cwchar>

// Formatting goes through the STATIC CRT, not wsprintf/wvsprintf: those live in
// user32.dll, and pulling them in would break the "imports only KERNEL32"
// property the shipped DLL is supposed to have. The reason this file avoids the
// CRT for FILE I/O still stands -- that is about lock ownership at
// DLL_PROCESS_DETACH, not about formatting into a stack buffer.

namespace k2se {
namespace log {
namespace {

HANDLE g_file = INVALID_HANDLE_VALUE;
bool g_diagnostic = false;
DWORD g_initTick = 0;
wchar_t g_dllDir[MAX_PATH] = {0};

extern "C" IMAGE_DOS_HEADER __ImageBase;

void ResolveDllDir() {
    GetModuleFileNameW(reinterpret_cast<HMODULE>(&__ImageBase), g_dllDir, MAX_PATH);
    wchar_t* slash = wcsrchr(g_dllDir, L'\\');
    if (slash) *(slash + 1) = L'\0';
}

void RawWrite(const char* text, size_t len) {
    if (g_file == INVALID_HANDLE_VALUE) return;
    DWORD written = 0;
    WriteFile(g_file, text, static_cast<DWORD>(len), &written, nullptr);
}

}  // namespace

bool DiagnosticEnabled() { return g_diagnostic; }

// GetTickCount, not QPC: this is for ordering log lines, where millisecond
// resolution is ample and a counter that cannot fail is worth more than one
// that is precise. Unsigned subtraction gives the right answer across the
// 49-day wrap.
uint32_t MillisSinceInit() {
    return static_cast<uint32_t>(GetTickCount() - g_initTick);
}

void Init() {
    g_initTick = GetTickCount();
    ResolveDllDir();

    wchar_t marker[MAX_PATH];
    _snwprintf(marker, MAX_PATH, L"%sK2SE_DIAGNOSTIC", g_dllDir);
    g_diagnostic = (GetFileAttributesW(marker) != INVALID_FILE_ATTRIBUTES);

    wchar_t dir[MAX_PATH];
    DWORD n = GetEnvironmentVariableW(L"LOCALAPPDATA", dir, MAX_PATH);
    if (n == 0 || n >= MAX_PATH) return;

    wchar_t path[MAX_PATH];
    _snwprintf(path, MAX_PATH, L"%s\\K2SE", dir);
    CreateDirectoryW(path, nullptr);
    _snwprintf(path, MAX_PATH, L"%s\\K2SE\\k2se.log", dir);

    g_file = CreateFileW(path, FILE_APPEND_DATA, FILE_SHARE_READ, nullptr,
                         OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (g_file == INVALID_HANDLE_VALUE) return;

    SetFilePointer(g_file, 0, nullptr, FILE_END);

    SYSTEMTIME st;
    GetLocalTime(&st);
    Writef("\r\n==================================================================");
    Writef("K2SE %d.%d.%d  session start  %04d-%02d-%02d %02d:%02d:%02d",
           K2SE_VERSION_MAJOR, K2SE_VERSION_MINOR, K2SE_VERSION_PATCH,
           st.wYear, st.wMonth, st.wDay, st.wHour, st.wMinute, st.wSecond);
    Writef("diagnostic marker: %s", g_diagnostic ? "PRESENT (verbose)" : "absent");
}

void Shutdown() {
    if (g_file != INVALID_HANDLE_VALUE) {
        Write("session end");
        CloseHandle(g_file);
        g_file = INVALID_HANDLE_VALUE;
    }
}

void Write(const char* line) {
    char buf[1200];
    int len = _snprintf(buf, sizeof(buf), "%s\r\n", line);
    if (len < 0) len = static_cast<int>(sizeof(buf)) - 1;  // truncated
    RawWrite(buf, static_cast<size_t>(len));
}

void Writef(const char* fmt, ...) {
    char body[1024];
    va_list args;
    va_start(args, fmt);
    _vsnprintf(body, sizeof(body), fmt, args);
    va_end(args);
    body[sizeof(body) - 1] = '\0';
    Write(body);
}

void Trace(const char* fmt, ...) {
    if (!g_diagnostic) return;
    char body[1024];
    va_list args;
    va_start(args, fmt);
    _vsnprintf(body, sizeof(body), fmt, args);
    va_end(args);
    body[sizeof(body) - 1] = '\0';
    char buf[1200];
    int len = _snprintf(buf, sizeof(buf), "  [trace] %s\r\n", body);
    if (len < 0) len = static_cast<int>(sizeof(buf)) - 1;
    RawWrite(buf, static_cast<size_t>(len));
}

}  // namespace log
}  // namespace k2se
