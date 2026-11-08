#include "apfiles.h"

#include <windows.h>

#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "log.h"

namespace k2se {
namespace apfiles {
namespace {

constexpr size_t kInboxMax = 64 * 1024;

bool ApDir(wchar_t* out, size_t cap) {
    wchar_t base[MAX_PATH];
    const DWORD n = GetEnvironmentVariableW(L"LOCALAPPDATA", base, MAX_PATH);
    if (n == 0 || n >= MAX_PATH) return false;
    wchar_t k2[MAX_PATH];
    _snwprintf(k2, MAX_PATH, L"%s\\K2SE", base);
    k2[MAX_PATH - 1] = L'\0';
    CreateDirectoryW(k2, nullptr);
    _snwprintf(out, cap, L"%s\\ap", k2);
    out[cap - 1] = L'\0';
    CreateDirectoryW(out, nullptr);
    return true;
}

// One-entry cache keyed by write time and size, so a script that asks for ten keys in a row reads the file once.
char gInbox[kInboxMax + 1];
FILETIME gInboxTime = {};
DWORD gInboxSize = 0xFFFFFFFF;
bool gInboxValid = false;

void LoadInbox() {
    wchar_t dir[MAX_PATH];
    if (!ApDir(dir, MAX_PATH)) { gInboxValid = false; gInbox[0] = '\0'; return; }
    wchar_t path[MAX_PATH];
    _snwprintf(path, MAX_PATH, L"%s\\inbox.txt", dir);
    path[MAX_PATH - 1] = L'\0';
    HANDLE h = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, nullptr, OPEN_EXISTING,
                           FILE_ATTRIBUTE_NORMAL, nullptr);
    if (h == INVALID_HANDLE_VALUE) { gInboxValid = false; gInbox[0] = '\0'; return; }
    FILETIME ft = {};
    const DWORD size = GetFileSize(h, nullptr);
    GetFileTime(h, nullptr, nullptr, &ft);
    if (gInboxValid && size == gInboxSize && ft.dwLowDateTime == gInboxTime.dwLowDateTime && ft.dwHighDateTime == gInboxTime.dwHighDateTime) {
        CloseHandle(h);
        return;
    }
    DWORD got = 0;
    const BOOL ok = ReadFile(h, gInbox, static_cast<DWORD>(kInboxMax), &got, nullptr);
    CloseHandle(h);
    if (!ok) { gInboxValid = false; gInbox[0] = '\0'; return; }
    gInbox[got] = '\0';
    gInboxSize = size;
    gInboxTime = ft;
    gInboxValid = true;
}

// Finds "key=" at the start of a line; returns the value text and its length (line end and trailing blanks excluded). Last match wins.
const char* FindValue(const char* key, size_t* len) {
    const size_t keyLen = std::strlen(key);
    const char* result = nullptr;
    const char* line = gInbox;
    while (*line) {
        const char* end = line;
        while (*end && *end != '\n') ++end;
        const char* p = line;
        while (p < end && (*p == ' ' || *p == '\t' || *p == '\r')) ++p;
        if (p < end && *p != '#' && static_cast<size_t>(end - p) > keyLen && _strnicmp(p, key, keyLen) == 0) {
            const char* q = p + keyLen;
            while (q < end && (*q == ' ' || *q == '\t')) ++q;
            if (q < end && *q == '=') {
                ++q;
                while (q < end && (*q == ' ' || *q == '\t')) ++q;
                const char* e = end;
                while (e > q && (e[-1] == '\r' || e[-1] == ' ' || e[-1] == '\t')) --e;
                result = q;
                *len = static_cast<size_t>(e - q);
            }
        }
        if (!*end) break;
        line = end + 1;
    }
    return result;
}

DWORD gOutSeq = 0;

struct Entry { char key[64]; char value[512]; bool used; };
Entry gStore[256];

}  // namespace

int InboxInt(const char* key, int fallback) {
    LoadInbox();
    size_t len = 0;
    const char* v = FindValue(key, &len);
    if (!v || len == 0) return fallback;
    char tmp[32];
    if (len >= sizeof(tmp)) return fallback;
    std::memcpy(tmp, v, len);
    tmp[len] = '\0';
    return static_cast<int>(std::strtol(tmp, nullptr, 0));
}

bool InboxStr(const char* key, char* out, size_t cap) {
    if (cap == 0) return false;
    out[0] = '\0';
    LoadInbox();
    size_t len = 0;
    const char* v = FindValue(key, &len);
    if (!v) return false;
    if (len > cap - 1) len = cap - 1;
    std::memcpy(out, v, len);
    out[len] = '\0';
    return true;
}

bool OutboxPut(const char* line) {
    wchar_t dir[MAX_PATH];
    if (!ApDir(dir, MAX_PATH)) return false;
    wchar_t path[MAX_PATH];
    _snwprintf(path, MAX_PATH, L"%s\\outbox.txt", dir);
    path[MAX_PATH - 1] = L'\0';
    HANDLE h = CreateFileW(path, FILE_APPEND_DATA, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, nullptr, OPEN_ALWAYS,
                           FILE_ATTRIBUTE_NORMAL, nullptr);
    if (h == INVALID_HANDLE_VALUE) return false;
    char buf[600];
    const int n = _snprintf(buf, sizeof(buf) - 2, "%lu|%s", static_cast<unsigned long>(++gOutSeq), line ? line : "");
    int total = n < 0 ? static_cast<int>(sizeof(buf)) - 2 : n;
    buf[total++] = '\r';
    buf[total++] = '\n';
    DWORD wrote = 0;
    const BOOL ok = WriteFile(h, buf, static_cast<DWORD>(total), &wrote, nullptr);
    CloseHandle(h);
    return ok && wrote == static_cast<DWORD>(total);
}

bool MemSet(const char* key, const char* value) {
    const char* v = value ? value : "";
    if (!key || !*key || std::strlen(key) >= sizeof(Entry::key) || std::strlen(v) >= sizeof(Entry::value)) return false;
    Entry* freeSlot = nullptr;
    for (Entry& e : gStore) {
        if (e.used && _stricmp(e.key, key) == 0) { std::strcpy(e.value, v); return true; }
        if (!e.used && !freeSlot) freeSlot = &e;
    }
    if (!freeSlot) return false;
    std::strcpy(freeSlot->key, key);
    std::strcpy(freeSlot->value, v);
    freeSlot->used = true;
    return true;
}

const char* MemGet(const char* key) {
    for (const Entry& e : gStore) if (e.used && _stricmp(e.key, key) == 0) return e.value;
    return "";
}

}  // namespace apfiles
}  // namespace k2se
