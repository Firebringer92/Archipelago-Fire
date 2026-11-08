#include "hookkit.h"

#include <windows.h>

#include <cstring>

#include "log.h"
#include "probe.h"

namespace k2se {
namespace hookkit {
namespace {

// Executable memory for the stubs: one block, filled front to back, never freed (the hooks live as long as the process).
uint8_t* gPool = nullptr;
size_t gUsed = 0;
constexpr size_t kPoolSize = 64 * 1024;

uint8_t* Reserve(size_t n) {
    if (!gPool) {
        gPool = static_cast<uint8_t*>(VirtualAlloc(nullptr, kPoolSize, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE));
        if (!gPool) return nullptr;
    }
    if (gUsed + n > kPoolSize) return nullptr;
    uint8_t* p = gPool + gUsed;
    gUsed += (n + 15) & ~static_cast<size_t>(15);
    return p;
}

// Offset of a register's saved value inside the frame made by pushad (edi is at the lowest address).
int PushadSlot(ArgKind k) {
    switch (k) {
        case ArgKind::kEdi: return 0;
        case ArgKind::kEsi: return 4;
        case ArgKind::kEbp: return 8;
        case ArgKind::kEbx: return 16;
        case ArgKind::kEdx: return 20;
        case ArgKind::kEcx: return 24;
        case ArgKind::kEax: return 28;
        default: return -1;
    }
}

struct Emitter {
    uint8_t* base;
    size_t size = 0;
    explicit Emitter(uint8_t* b) : base(b) {}
    void B(uint8_t v) { base[size++] = v; }
    void Bytes(const void* p, size_t n) { std::memcpy(base + size, p, n); size += n; }
    void U32(uint32_t v) { Bytes(&v, 4); }
    void JmpAbs(uint32_t target) {  // jmp rel32
        B(0xE9);
        const int32_t rel = static_cast<int32_t>(target - (reinterpret_cast<uint32_t>(base) + static_cast<uint32_t>(size) + 4));
        U32(static_cast<uint32_t>(rel));
    }
};

}  // namespace

bool CheckBytes(uint32_t address, const uint8_t* expected, size_t n) {
    for (size_t i = 0; i < n; ++i) {
        int v = 0;
        if (!probe::ReadMem(reinterpret_cast<void*>(static_cast<uintptr_t>(address + i)), 0, 1, &v)) return false;
        if (static_cast<uint8_t>(v) != expected[i]) return false;
    }
    return true;
}

bool PatchBytes(uint32_t address, const uint8_t* expected, const uint8_t* repl, size_t n) {
    if (n == 0 || n > 8) return false;
    if (!CheckBytes(address, expected, n)) return false;
    for (size_t i = 0; i < n; ++i) {
        if (!probe::WriteCode(reinterpret_cast<void*>(static_cast<uintptr_t>(address + i)), 1, repl[i], nullptr)) return false;
    }
    return true;
}

bool InstallDetour(const Detour& d) {
    if (d.length < 5 || d.length > 32) {
        log::Writef("hookkit: %s refused: bad length %u", d.name, static_cast<unsigned>(d.length));
        return false;
    }
    if (!CheckBytes(d.address, d.original, d.length)) {
        log::Writef("hookkit: %s refused: bytes at 0x%08X are not the expected original", d.name, d.address);
        return false;
    }
    uint8_t* mem = Reserve(256);
    if (!mem) {
        log::Writef("hookkit: %s refused: out of stub memory", d.name);
        return false;
    }
    Emitter e(mem);
    const uint32_t returnTo = d.address + static_cast<uint32_t>(d.length);

    e.B(0x9C);  // pushfd
    e.B(0x60);  // pushad
    // arguments, right to left. After pushfd+pushad the entry stack pointer is esp+36; each pushed argument moves esp by 4.
    int pushed = 0;
    for (size_t i = d.argCount; i-- > 0;) {
        const Arg& a = d.args[i];
        if (a.kind == ArgKind::kStackArg) {
            const int disp = 36 + a.offset + 4 * pushed;      // lea eax,[esp+disp]
            e.B(0x8D); e.B(0x84); e.B(0x24); e.U32(static_cast<uint32_t>(disp));
        } else {
            const int disp = PushadSlot(a.kind) + 4 * pushed;  // mov eax,[esp+disp]
            e.B(0x8B); e.B(0x84); e.B(0x24); e.U32(static_cast<uint32_t>(disp));
        }
        e.B(0x50);  // push eax
        ++pushed;
    }
    e.B(0xB8); e.U32(reinterpret_cast<uint32_t>(d.handler));  // mov eax, handler
    e.B(0xFF); e.B(0xD0);                                      // call eax
    if (pushed) { e.B(0x83); e.B(0xC4); e.B(static_cast<uint8_t>(4 * pushed)); }  // add esp, 4*argc

    auto storeResult = [&](ResultReg r) {
        int slot = -1;
        if (r == ResultReg::kEax) slot = 28;
        else if (r == ResultReg::kEcx) slot = 24;
        else if (r == ResultReg::kEdx) slot = 20;
        if (slot >= 0) { e.B(0x89); e.B(0x44); e.B(0x24); e.B(static_cast<uint8_t>(slot)); }  // mov [esp+slot], eax
    };

    if (d.consumedExit != 0) {
        e.B(0x85); e.B(0xC0);                 // test eax, eax
        e.B(0x74);                            // jz notConsumed
        const size_t jzFix = e.size++;
        storeResult(ResultReg::kEax);
        e.B(0x61); e.B(0x9D);                 // popad, popfd
        e.JmpAbs(d.consumedExit);
        e.base[jzFix] = static_cast<uint8_t>(e.size - (jzFix + 1));
        e.B(0x61); e.B(0x9D);
    } else {
        storeResult(d.result);
        e.B(0x61); e.B(0x9D);
    }
    if (!d.skipOriginal) e.Bytes(d.original, d.length);
    e.JmpAbs(returnTo);

    // redirect the site: jmp stub, then nops for the rest of the replaced bytes
    uint8_t patch[32];
    std::memset(patch, 0x90, sizeof(patch));
    patch[0] = 0xE9;
    const int32_t rel = static_cast<int32_t>(reinterpret_cast<uint32_t>(mem) - (d.address + 5));
    std::memcpy(patch + 1, &rel, 4);
    for (size_t i = 0; i < d.length; ++i) {
        if (!probe::WriteCode(reinterpret_cast<void*>(static_cast<uintptr_t>(d.address + i)), 1, patch[i], nullptr)) {
            log::Writef("hookkit: %s FAILED while writing at 0x%08X (site may be half patched)", d.name, d.address + static_cast<uint32_t>(i));
            return false;
        }
    }
    FlushInstructionCache(GetCurrentProcess(), mem, e.size);
    return true;
}

}  // namespace hookkit
}  // namespace k2se
