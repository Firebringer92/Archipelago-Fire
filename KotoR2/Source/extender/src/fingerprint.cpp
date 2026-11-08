#include "fingerprint.h"

#include <windows.h>

#include <cstdio>
#include <cwchar>

#include "log.h"
#include "offsets.h"

namespace k2se {
namespace fingerprint {
namespace {

char g_failure[256] = "no check run yet";

// Every probe read goes through these: a wrong image means an unmapped address,
// and we want "probe UNREADABLE" in the log, not an access violation.
bool SafeReadDword(uint32_t va, uint32_t* out) {
    __try {
        *out = *reinterpret_cast<volatile uint32_t*>(va);
        return true;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return false;
    }
}

bool SafeReadByte(uint32_t va, uint8_t* out) {
    __try {
        *out = *reinterpret_cast<volatile uint8_t*>(va);
        return true;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return false;
    }
}

bool ProbeDword(const char* name, uint32_t va, uint32_t expected) {
    uint32_t actual = 0;
    if (!SafeReadDword(va, &actual)) {
        log::Writef("  probe %-22s @0x%08X  UNREADABLE", name, va);
        _snprintf(g_failure, sizeof(g_failure),"%s unreadable at 0x%08X", name, va);
        return false;
    }
    const bool ok = (actual == expected);
    log::Writef("  probe %-22s @0x%08X  = 0x%08X  expected 0x%08X  %s", name, va,
                actual, expected, ok ? "OK" : "MISMATCH");
    if (!ok)
        _snprintf(g_failure, sizeof(g_failure), "%s: got 0x%08X expected 0x%08X", name, actual,
                  expected);
    return ok;
}

bool ProbeByte(const char* name, uint32_t va, uint8_t expected) {
    uint8_t actual = 0;
    if (!SafeReadByte(va, &actual)) {
        log::Writef("  probe %-22s @0x%08X  UNREADABLE", name, va);
        _snprintf(g_failure, sizeof(g_failure),"%s unreadable at 0x%08X", name, va);
        return false;
    }
    const bool ok = (actual == expected);
    log::Writef("  probe %-22s @0x%08X  = 0x%02X        expected 0x%02X        %s", name, va,
                actual, expected, ok ? "OK" : "MISMATCH");
    if (!ok)
        _snprintf(g_failure, sizeof(g_failure), "%s: got 0x%02X expected 0x%02X", name, actual,
                  expected);
    return ok;
}

}  // namespace

const char* LastFailure() { return g_failure; }

Verdict Check() {
    HMODULE exe = GetModuleHandleW(nullptr);
    if (!exe) {
        lstrcpyA(g_failure, "GetModuleHandleW(NULL) returned NULL");
        return Verdict::kNotLoaded;
    }

    // Take the base at runtime rather than hardcoding 0x00400000: correct either
    // way here (RELOCS_STRIPPED), and free.
    const uint32_t base = reinterpret_cast<uint32_t>(exe);
    log::Writef("image base: 0x%08X (expected 0x%08X)", base, off::kImageBase);
    if (base != off::kImageBase) {
        _snprintf(g_failure, sizeof(g_failure),"image base 0x%08X, expected 0x%08X", base, off::kImageBase);
        return Verdict::kWrongBuild;
    }

    const auto* dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(exe);
    const auto* nt = reinterpret_cast<const IMAGE_NT_HEADERS32*>(base + dos->e_lfanew);

    const uint32_t stamp = nt->FileHeader.TimeDateStamp;
    const uint16_t chars = nt->FileHeader.Characteristics;

    log::Writef("PE TimeDateStamp: 0x%08X (expected 0x%08X)", stamp, off::kTimeDateStamp);
    log::Writef("PE Characteristics: 0x%04X  [%s]", chars,
                chars == off::kCharacteristicsLaa       ? "4GB/LAA patched"
                : chars == off::kCharacteristicsPristine ? "pristine"
                                                         : "unrecognised");

    if (stamp != off::kTimeDateStamp) {
        _snprintf(g_failure, sizeof(g_failure),"TimeDateStamp 0x%08X, expected 0x%08X (different build)", stamp,
                  off::kTimeDateStamp);
        return Verdict::kWrongBuild;
    }

    bool ok = true;
    log::Write("code probes:");
    ok &= ProbeDword("vtable[0]", off::kVTable + 0, off::kVTableSlot0);
    ok &= ProbeDword("vtable[1] InitCommands", off::kVTable + 4, off::kInitializeCommands);
    ok &= ProbeDword("vtable[2] ExecuteCommand", off::kVTable + 8, off::kExecuteCommand);
    ok &= ProbeDword("vtable[3]", off::kVTable + 12, off::kVTableSlot3);
    ok &= ProbeDword("alloc size 877*4", off::kSiteAllocSize, off::kTableAllocBytes);
    ok &= ProbeDword("init bound 877", off::kSiteInitBound, off::kVanillaRoutineCount);
    ok &= ProbeDword("dispatch bound 877", off::kSiteDispatchBound, off::kVanillaRoutineCount);
    ok &= ProbeByte("m_pCommands (init)", off::kSiteCmdOffInit, off::kCommandsFieldOffset);
    ok &= ProbeByte("m_pCommands (dispatch)", off::kSiteCmdOffDispatch, off::kCommandsFieldOffset);
    ok &= ProbeByte("m_pInternal", off::kSiteVmInternal, off::kVmInternalOffset);
    ok &= ProbeDword("PopFloat call site", off::kSitePopFloatCall, off::kSitePopFloatRel);
    ok &= ProbeDword("PushFloat call site", off::kSitePushFloatCall, off::kSitePushFloatRel);
    ok &= ProbeDword("PopObject call site", off::kSitePopObjectCall, off::kSitePopObjectRel);
    ok &= ProbeDword("PushObject call site", off::kSitePushObjectCall, off::kSitePushObjectRel);
    ok &= ProbeDword("AurPostString prologue", off::kSiteAurPostString, off::kAurPostStringPrologue);

    if (!ok) return Verdict::kWrongBuild;

    lstrcpyA(g_failure, "");
    return Verdict::kMatch;
}

void LogEnvironment() {
    wchar_t exePath[MAX_PATH];
    if (!GetModuleFileNameW(nullptr, exePath, MAX_PATH)) return;
    log::Writef("host exe: %S", exePath);

    wchar_t dir[MAX_PATH];
    lstrcpyW(dir, exePath);
    wchar_t* slash = wcsrchr(dir, L'\\');
    if (!slash) return;
    *(slash + 1) = L'\0';

    // Other DLLs that occupy proxy slots. A conflict here is the single most
    // common cause of "K2SE does nothing" reports.
    static const wchar_t* kWatch[] = {
        L"opengl32.dll",  L"glu32.dll",     L"dinput8.dll", L"winmm.dll",
        L"binkw32.dll",   L"binkw32Hooked.dll", L"d3d9.dll", L"dxgi.dll",
    };

    log::Write("game-folder DLL census:");
    for (const wchar_t* name : kWatch) {
        wchar_t probe[MAX_PATH];
        _snwprintf(probe, MAX_PATH, L"%s%s", dir, name);
        const DWORD attr = GetFileAttributesW(probe);
        if (attr != INVALID_FILE_ATTRIBUTES) log::Writef("  present: %S", name);
    }
}

}  // namespace fingerprint
}  // namespace k2se
