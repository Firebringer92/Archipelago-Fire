#include "vm.h"

#include <windows.h>
#include <intrin.h>

#include "log.h"
#include "offsets.h"
#include "routines.h"

#pragma intrinsic(_ReturnAddress)

namespace k2se {
namespace vm {
namespace {

ExecuteCommandFn g_original = nullptr;
// LONG, not LONG64: InterlockedIncrement64 is not dependably available on x86,
// and this counter only has to prove the pass-through path is exercised.
volatile LONG g_calls = 0;
bool g_installed = false;
bool g_selfValidated = false;
bool g_selfValidationFailed = false;
bool g_callerLogged = false;

// One-shot check on the first real dispatch. This is the strongest assertion
// available to us: it proves the object layout, that the table is fully
// populated, and that the ID -> handler mapping recovered statically is the one
// actually in memory.
void SelfValidate(void* self) {
    if (g_selfValidated) return;
    g_selfValidated = true;

    void** cmds = CommandTable(self);
    if (!cmds) {
        log::Write("SELF-VALIDATION FAILED: m_pCommands is NULL");
        g_selfValidationFailed = true;
        return;
    }

    struct Expect {
        int id;
        uint32_t handler;
        const char* name;
    };
    static const Expect kExpect[] = {
        {off::kRoutineRandom, off::kHandlerRandom, "Random"},
        {off::kRoutineAcos, off::kHandlerMath, "acos (shared math handler)"},
        {off::kRoutineAbs, off::kHandlerMath, "abs (shared math handler)"},
        {off::kRoutineLast, off::kHandlerRebuildParty, "RebuildPartyTable"},
    };

    bool ok = true;
    log::Writef("self-validation, table @0x%08X:", reinterpret_cast<uint32_t>(cmds));
    for (const Expect& e : kExpect) {
        const uint32_t got = reinterpret_cast<uint32_t>(cmds[e.id]);
        const bool hit = (got == e.handler);
        log::Writef("  cmds[%3d] = 0x%08X  expected 0x%08X  %-28s %s", e.id, got, e.handler,
                    e.name, hit ? "OK" : "MISMATCH");
        ok &= hit;
    }

    // No slot may be NULL: all 877 are populated by InitializeCommands plus the
    // minigame installer. A NULL here would mean we hooked too early.
    int nulls = 0;
    for (int i = 0; i < off::kVanillaRoutineCount; ++i)
        if (cmds[i] == nullptr) ++nulls;
    log::Writef("  NULL slots: %d (expected 0)", nulls);
    ok &= (nulls == 0);

    if (!ok) {
        g_selfValidationFailed = true;
        log::Write("SELF-VALIDATION FAILED -> uninstalling hook, running vanilla");
        RemoveHook();
    } else {
        log::Write("self-validation PASSED");
    }
}

int __fastcall HookExecuteCommand(void* self, void* edx, int id, int nParams) {
    InterlockedIncrement(&g_calls);

    // DESIGN.md Q3 instrumentation: record who dispatches script actions, so the
    // caller (the NCS interpreter's ACTION case) can be disassembled and checked
    // for a second bounds test that would stop routine IDs >= 877 from ever
    // reaching this dispatcher. Cheaper and far more reliable than sifting the
    // 328 candidate virtual-call sites in .text.
    if (!g_callerLogged) {
        g_callerLogged = true;
        log::Writef("CALLER of ExecuteCommand: return address 0x%08X  (first dispatch: id=%d, nParams=%d)",
                    reinterpret_cast<uint32_t>(_ReturnAddress()), id, nParams);
    }

    if (!g_selfValidated) SelfValidate(self);
    if (g_selfValidationFailed) return g_original(self, edx, id, nParams);

    // Extended IDs: served entirely by K2SE, never forwarded.
    if (id >= off::kFirstExtendedId) return routines::DispatchExtended(self, id, nParams);

    // Vanilla IDs that K2SE intercepts (currently only the abs() presence
    // sentinel). Everything else is byte-identical pass-through.
    if (routines::Intercepts(id)) {
        int result = 0;
        if (routines::DispatchVanillaOverride(self, id, nParams, &result)) return result;
    }

    return g_original(self, edx, id, nParams);
}

}  // namespace

void** CommandTable(void* self) {
    if (!self) return nullptr;
    return *reinterpret_cast<void***>(reinterpret_cast<char*>(self) + off::kCommandsFieldOffset);
}

int CallOriginal(void* self, int id, int nParams) {
    if (!g_original) return off::kErrCommandNotFound;
    return g_original(self, nullptr, id, nParams);
}

uint64_t ForwardedCallCount() {
    return static_cast<uint64_t>(static_cast<unsigned long>(g_calls));
}

bool InstallHook() {
    if (g_installed) return true;

    auto* slot = reinterpret_cast<ExecuteCommandFn*>(off::kVTableSlotExecute);

    DWORD oldProtect = 0;
    if (!VirtualProtect(slot, sizeof(void*), PAGE_READWRITE, &oldProtect)) {
        log::Writef("REFUSED TO WRITE: VirtualProtect failed on 0x%08X, error %lu",
                    off::kVTableSlotExecute, GetLastError());
        return false;
    }

    g_original = *slot;
    if (reinterpret_cast<uint32_t>(g_original) != off::kExecuteCommand) {
        log::Writef("REFUSED TO WRITE: slot 0x%08X holds 0x%08X, expected 0x%08X",
                    off::kVTableSlotExecute, reinterpret_cast<uint32_t>(g_original),
                    off::kExecuteCommand);
        VirtualProtect(slot, sizeof(void*), oldProtect, &oldProtect);
        g_original = nullptr;
        return false;
    }

    *slot = &HookExecuteCommand;

    DWORD restored = 0;
    VirtualProtect(slot, sizeof(void*), oldProtect, &restored);

    g_installed = true;
    log::Writef("hook installed: [0x%08X] 0x%08X -> 0x%08X (old protection 0x%lX)",
                off::kVTableSlotExecute, off::kExecuteCommand,
                reinterpret_cast<uint32_t>(&HookExecuteCommand), oldProtect);
    return true;
}

void RemoveHook() {
    if (!g_installed || !g_original) return;

    auto* slot = reinterpret_cast<ExecuteCommandFn*>(off::kVTableSlotExecute);
    DWORD oldProtect = 0;
    if (!VirtualProtect(slot, sizeof(void*), PAGE_READWRITE, &oldProtect)) {
        log::Write("REFUSED TO WRITE: VirtualProtect failed while removing hook");
        return;
    }
    *slot = g_original;
    DWORD restored = 0;
    VirtualProtect(slot, sizeof(void*), oldProtect, &restored);

    g_installed = false;
    log::Writef("hook removed; %lu dispatches forwarded this session",
                static_cast<unsigned long>(g_calls));
}

}  // namespace vm
}  // namespace k2se
