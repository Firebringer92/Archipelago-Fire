// Randomised alignment pushes (0.2.1).
//
// Every alignment change a script asks for with AdjustAlignment(...) is made random: a random direction (light or dark) and a random size.
//
// One patched call, in the Steam swkotor.exe 1.03 image (address verified against the decrypted code, see research/patchmanager_k1/SPIKE_RESULTS.md):
//   the AdjustAlignment script command's call (0x0052E0C8) to CSWSCreatureStats::ModifyAlignment (0x005AE610), void __thiscall (stats, short delta),
//   delta already signed (+ light, - dark) and clamped by the caller.
// The command goes on to build the feedback message and the on-screen alignment notice from its own copies of the direction and size (the delta in EDI and
// two locals), so all of them are rewritten together; the notice then matches what was applied.
// The other callers of ModifyAlignment (SetGoodEvilValue and two cheat console functions) are untouched. Anything that must stay exact therefore uses
// SetGoodEvilValue instead of AdjustAlignment (the Unknown World finale scripts and the Vendor's flat alignment items, installed by the player bundle).
//
// The size of a push: a random whole number from 10 to 20 whatever the original size was, for large swings. The direction is light or dark with equal chance.
// The game clamps the value to 0..100 as usual.
//
// The feature is off unless the file "ap_alignrand.txt" exists beside the game executable and its first line is 1/on/true. The file is read again at every
// push (pushes are rare), so it can be switched without restarting the game. An optional line "seed=<number>" makes the sequence repeatable.

#include <windows.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>

#include "log.h"

namespace {

constexpr uintptr_t kModifyAlignmentVa = 0x005AE610u;
constexpr uintptr_t kAdjustCallVa = 0x0052E0C8u;   // the call to ModifyAlignment inside ExecuteCommandAdjustAlignment

// Expected original bytes: push edi / mov ecx, esi / call ModifyAlignment / push 0x34 (verified against the decrypted image).
constexpr uintptr_t kAdjustSiteVa = 0x0052E0C5u;
constexpr uint8_t kAdjustSiteBytes[] = {0x57, 0x8B, 0xCE, 0xE8, 0x43, 0x05, 0x08, 0x00, 0x6A, 0x34};

// The stub's view of the stack at the patched call, in 32-bit slots.
constexpr int kSlotDelta = 1;       // the signed delta pushed as the argument
constexpr int kSlotAmount = 6;      // the command's "amount" local, used for the feedback message
constexpr int kSlotAlignment = 7;   // the command's "alignment" local, used for the feedback message
constexpr int32_t kAlignmentLight = 2;   // ALIGNMENT_LIGHT_SIDE
constexpr int32_t kAlignmentDark = 3;    // ALIGNMENT_DARK_SIDE

constexpr int kMinPush = 10;
constexpr int kMaxPush = 20;

uintptr_t gModify = kModifyAlignmentVa;

volatile LONG gEnabled = 0;
uint32_t gRng = 0x2545F491u;
bool gSeeded = false;
volatile LONG gPushes = 0;

uint32_t Next() {
    gRng ^= gRng << 13;
    gRng ^= gRng >> 17;
    gRng ^= gRng << 5;
    return gRng;
}

void ReloadConfig() {
    char path[MAX_PATH];
    DWORD n = GetModuleFileNameA(nullptr, path, MAX_PATH);
    if (!n || n >= MAX_PATH) return;
    char* slash = strrchr(path, '\\');
    if (!slash) return;
    strcpy_s(slash + 1, static_cast<size_t>(MAX_PATH - (slash + 1 - path)), "ap_alignrand.txt");
    FILE* f = nullptr;
    if (fopen_s(&f, path, "r") != 0 || !f) {
        if (InterlockedExchange(&gEnabled, 0) != 0) Log("alignrand: disabled");
        return;
    }
    char line[96];
    bool first = true;
    LONG enabled = 0;
    while (fgets(line, sizeof(line), f)) {
        char* e = line + strlen(line);
        while (e > line && (e[-1] == '\n' || e[-1] == '\r' || e[-1] == ' ')) *--e = 0;
        if (first) {
            enabled = (!_stricmp(line, "1") || !_stricmp(line, "on") || !_stricmp(line, "true")) ? 1 : 0;
            first = false;
        } else if (!_strnicmp(line, "seed=", 5) && !gSeeded) {
            const uint32_t seed = static_cast<uint32_t>(strtoul(line + 5, nullptr, 10));
            if (seed) {
                gRng = seed;
                gSeeded = true;
            }
        }
    }
    fclose(f);
    if (InterlockedExchange(&gEnabled, enabled) != enabled) Log("alignrand: %s", enabled ? "ENABLED" : "disabled");
}

void __cdecl RollPush(int32_t* frame) {
    const short delta = static_cast<short>(frame[kSlotDelta]);
    if (delta == 0) return;
    ReloadConfig();
    if (!gEnabled) return;
    const int pushed = kMinPush + static_cast<int>(Next() % static_cast<uint32_t>(kMaxPush - kMinPush + 1));
    const int signedDelta = (Next() & 1u) ? pushed : -pushed;
    const LONG k = InterlockedIncrement(&gPushes);
    Log("alignrand: #%ld alignment push %+d replaced by %+d", k, static_cast<int>(delta), signedDelta);
    frame[kSlotDelta] = signedDelta;
    frame[kSlotAmount] = pushed;
    frame[kSlotAlignment] = signedDelta > 0 ? kAlignmentLight : kAlignmentDark;
}

// Stands in for ModifyAlignment at the patched call. Entry: ECX = stats, [ESP] = return address, [ESP+4] = delta.
// EDI is reloaded from the argument slot because the command reads it again for the on-screen notice.
__declspec(naked) void AdjustCallStub() {
    __asm {
        push ecx
        lea eax, [esp + 4]
        push eax
        call RollPush
        add esp, 4
        pop ecx
        mov edi, [esp + 4]
        jmp dword ptr [gModify]
    }
}

}  // namespace

// Called once from the worker thread, after the code is decrypted and the dispatcher hook is in. Never throws; leaves the game untouched on any mismatch.
bool AlignRandInstall() {
    if (memcmp(reinterpret_cast<const void*>(kAdjustSiteVa), kAdjustSiteBytes, sizeof(kAdjustSiteBytes)) != 0) {
        Log("alignrand: NOT installed: the code in AdjustAlignment is not the expected original");
        return false;
    }
    LARGE_INTEGER t;
    QueryPerformanceCounter(&t);
    gRng ^= static_cast<uint32_t>(t.LowPart) ^ GetTickCount();
    if (!gRng) gRng = 0x2545F491u;
    uint8_t* call = reinterpret_cast<uint8_t*>(kAdjustCallVa);
    const int32_t rel = static_cast<int32_t>(reinterpret_cast<uintptr_t>(&AdjustCallStub) - (kAdjustCallVa + 5));
    DWORD old = 0;
    if (!VirtualProtect(call + 1, sizeof(rel), PAGE_EXECUTE_READWRITE, &old)) {
        Log("alignrand: NOT installed: the code could not be made writable");
        return false;
    }
    memcpy(call + 1, &rel, sizeof(rel));
    VirtualProtect(call + 1, sizeof(rel), old, &old);
    FlushInstructionCache(GetCurrentProcess(), call, 5);
    ReloadConfig();
    Log("alignrand: installed (%s)", gEnabled ? "enabled" : "off: ap_alignrand.txt is missing or its first line is not 1");
    return true;
}
