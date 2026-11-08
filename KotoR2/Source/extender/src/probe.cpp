#include "probe.h"

#include <windows.h>

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "log.h"

namespace k2se {
namespace probe {
namespace {

bool K2seDir(wchar_t* out, size_t cap) {
    wchar_t dir[MAX_PATH];
    DWORD n = GetEnvironmentVariableW(L"LOCALAPPDATA", dir, MAX_PATH);
    if (n == 0 || n >= MAX_PATH) return false;
    _snwprintf(out, cap, L"%s\\K2SE", dir);
    out[cap - 1] = L'\0';
    CreateDirectoryW(out, nullptr);
    return true;
}

// One bounded, fault-tolerant memcpy. No C++ objects in scope, so __try is legal.
bool GuardedCopy(void* dst, const void* src, size_t n) {
    __try {
        memcpy(dst, src, n);
        return true;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return false;
    }
}

bool IsWritableProtect(DWORD protect) {
    return (protect & (PAGE_READWRITE | PAGE_WRITECOPY | PAGE_EXECUTE_READWRITE |
                       PAGE_EXECUTE_WRITECOPY)) != 0;
}

}  // namespace

size_t SafeCopy(void* dst, const void* src, size_t n) {
    size_t done = 0;
    while (done < n) {
        const char* cur = static_cast<const char*>(src) + done;
        MEMORY_BASIC_INFORMATION mbi;
        if (VirtualQuery(cur, &mbi, sizeof(mbi)) == 0) break;
        if (mbi.State != MEM_COMMIT) break;
        if (mbi.Protect & (PAGE_NOACCESS | PAGE_GUARD)) break;
        const size_t regionEnd =
            reinterpret_cast<size_t>(mbi.BaseAddress) + static_cast<size_t>(mbi.RegionSize);
        size_t chunk = regionEnd - reinterpret_cast<size_t>(cur);
        if (chunk > n - done) chunk = n - done;
        if (!GuardedCopy(static_cast<char*>(dst) + done, cur, chunk)) break;
        done += chunk;
    }
    return done;
}

bool ReadMem(const void* base, int offset, int width, int* out) {
    if (!base || !out) return false;
    if (width != 1 && width != 2 && width != 4) return false;
    if (offset < 0 || offset > 0x100000) return false;
    unsigned char buf[4] = {0, 0, 0, 0};
    const char* src = static_cast<const char*>(base) + offset;
    if (SafeCopy(buf, src, static_cast<size_t>(width)) != static_cast<size_t>(width)) return false;
    int v = 0;
    for (int i = 0; i < width; ++i) v |= static_cast<int>(buf[i]) << (8 * i);
    *out = v;
    return true;
}

bool WriteMem(void* base, int offset, int width, int value, int* oldValue) {
    if (!base) return false;
    if (width != 1 && width != 2 && width != 4) return false;
    if (offset < 0 || offset > 0x3000) return false;  // creature and stats blocks only
    char* dst = static_cast<char*>(base) + offset;

    MEMORY_BASIC_INFORMATION mbi;
    if (VirtualQuery(dst, &mbi, sizeof(mbi)) == 0) return false;
    if (mbi.State != MEM_COMMIT || !IsWritableProtect(mbi.Protect)) return false;
    // The whole value must sit inside this one region.
    const size_t regionEnd =
        reinterpret_cast<size_t>(mbi.BaseAddress) + static_cast<size_t>(mbi.RegionSize);
    if (reinterpret_cast<size_t>(dst) + static_cast<size_t>(width) > regionEnd) return false;

    int previous = 0;
    if (!ReadMem(base, offset, width, &previous)) return false;
    if (oldValue) *oldValue = previous;

    unsigned char buf[4];
    for (int i = 0; i < width; ++i) buf[i] = static_cast<unsigned char>((value >> (8 * i)) & 0xFF);
    return GuardedCopy(dst, buf, static_cast<size_t>(width));
}

bool WriteAbs(void* addr, int width, int value, int* oldValue) {
    if (!addr) return false;
    if (width != 1 && width != 2 && width != 4) return false;
    MEMORY_BASIC_INFORMATION mbi;
    if (VirtualQuery(addr, &mbi, sizeof(mbi)) == 0) return false;
    if (mbi.State != MEM_COMMIT || !IsWritableProtect(mbi.Protect)) return false;
    const size_t regionEnd =
        reinterpret_cast<size_t>(mbi.BaseAddress) + static_cast<size_t>(mbi.RegionSize);
    if (reinterpret_cast<size_t>(addr) + static_cast<size_t>(width) > regionEnd) return false;

    int previous = 0;
    if (!ReadMem(addr, 0, width, &previous)) return false;
    if (oldValue) *oldValue = previous;

    unsigned char buf[4];
    for (int i = 0; i < width; ++i) buf[i] = static_cast<unsigned char>((value >> (8 * i)) & 0xFF);
    return GuardedCopy(addr, buf, static_cast<size_t>(width));
}

bool WriteCode(void* addr, int width, int value, int* oldValue) {
    // Research only (K2SE_WriteMem area 3): patches game code in place, restoring the page protection after.
    // Confined to the executable's own code range so a wrong address cannot touch anything else.
    const uintptr_t a = reinterpret_cast<uintptr_t>(addr);
    if (a < 0x00401000u || a + static_cast<uintptr_t>(width) > 0x00986000u) return false;
    if (width != 1 && width != 2 && width != 4) return false;
    int previous = 0;
    if (!ReadMem(addr, 0, width, &previous)) return false;
    if (oldValue) *oldValue = previous;
    DWORD oldProtect = 0;
    if (!VirtualProtect(addr, static_cast<SIZE_T>(width), PAGE_EXECUTE_READWRITE, &oldProtect)) return false;
    unsigned char buf[4];
    for (int i = 0; i < width; ++i) buf[i] = static_cast<unsigned char>((value >> (8 * i)) & 0xFF);
    const bool ok = GuardedCopy(addr, buf, static_cast<size_t>(width));
    DWORD ignored = 0;
    VirtualProtect(addr, static_cast<SIZE_T>(width), oldProtect, &ignored);
    FlushInstructionCache(GetCurrentProcess(), addr, static_cast<SIZE_T>(width));
    return ok;
}

int ConfigInt(const char* key, int fallback) {
    wchar_t dir[MAX_PATH];
    if (!K2seDir(dir, MAX_PATH)) return fallback;
    wchar_t path[MAX_PATH];
    _snwprintf(path, MAX_PATH, L"%s\\config.txt", dir);
    path[MAX_PATH - 1] = L'\0';

    HANDLE h = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr,
                           OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (h == INVALID_HANDLE_VALUE) return fallback;
    char text[8192];
    DWORD got = 0;
    BOOL ok = ReadFile(h, text, sizeof(text) - 1, &got, nullptr);
    CloseHandle(h);
    if (!ok) return fallback;
    text[got] = '\0';

    const size_t keyLen = strlen(key);
    int result = fallback;
    char* line = text;
    while (*line) {
        char* next = line;
        while (*next && *next != '\n') ++next;
        const bool more = (*next == '\n');
        *next = '\0';

        char* p = line;
        while (*p == ' ' || *p == '\t' || *p == '\r') ++p;
        if (*p != '#' && *p != '\0') {
            if (_strnicmp(p, key, keyLen) == 0) {
                char* q = p + keyLen;
                while (*q == ' ' || *q == '\t') ++q;
                if (*q == '=') {
                    ++q;
                    while (*q == ' ' || *q == '\t') ++q;
                    result = static_cast<int>(strtol(q, nullptr, 0));  // last match wins
                }
            }
        }
        if (!more) break;
        line = next + 1;
    }
    return result;
}

int DumpMem(const void* base, int size, const char* label) {
    if (!base || size <= 0) return -1;
    if (size > 0x100000) size = 0x100000;

    wchar_t dir[MAX_PATH];
    if (!K2seDir(dir, MAX_PATH)) return -1;
    wchar_t dumps[MAX_PATH];
    _snwprintf(dumps, MAX_PATH, L"%s\\dumps", dir);
    dumps[MAX_PATH - 1] = L'\0';
    CreateDirectoryW(dumps, nullptr);

    wchar_t name[96];
    size_t n = 0;
    for (const char* c = label; c && *c && n < 90; ++c) {
        const char ch = *c;
        const bool okc = (ch >= '0' && ch <= '9') || (ch >= 'a' && ch <= 'z') ||
                         (ch >= 'A' && ch <= 'Z') || ch == '_' || ch == '-';
        name[n++] = okc ? static_cast<wchar_t>(ch) : L'_';
    }
    if (n == 0) name[n++] = L'x';
    name[n] = L'\0';

    wchar_t path[MAX_PATH];
    _snwprintf(path, MAX_PATH, L"%s\\%s.bin", dumps, name);
    path[MAX_PATH - 1] = L'\0';

    // Copy in pieces so one unreadable page ends the dump instead of failing it.
    static unsigned char buf[0x100000];
    const size_t got = SafeCopy(buf, base, static_cast<size_t>(size));

    HANDLE h = CreateFileW(path, GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL,
                           nullptr);
    if (h == INVALID_HANDLE_VALUE) return -1;
    DWORD written = 0;
    WriteFile(h, buf, static_cast<DWORD>(got), &written, nullptr);
    CloseHandle(h);
    return static_cast<int>(written);
}

}  // namespace probe
}  // namespace k2se
