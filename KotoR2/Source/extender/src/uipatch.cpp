#include "uipatch.h"

#include <cstdint>

#include "log.h"
#include "probe.h"

namespace k2se {
namespace uipatch {
namespace {

struct Site {
    uint32_t address;  // the second opcode byte of an `and reg, 1` (83 /4 ib): E0 eax, E1 ecx, E2 edx
    int expected;      // the original byte
    int patched;       // the same register with /1 (or): C8 eax, C9 ecx, CA edx
};

// Slot 10 available: the hide sequence for slot 7's controls (0x1FD0, 0x21A4, 0x22EC) at 0x8A099F, 0x8A09C3, 0x8A09E6.
// Slot 11 available: the hide sequence for slot 4's controls (0x1268, 0x143C, 0x1584) at 0x8A0DE0, 0x8A0E04, 0x8A0E28.
constexpr Site kSites[] = {
    {0x008A09A0, 0xE0, 0xC8},
    {0x008A09C4, 0xE2, 0xCA},
    {0x008A09E7, 0xE1, 0xC9},
    {0x008A0DE1, 0xE1, 0xC9},
    {0x008A0E05, 0xE0, 0xC8},
    {0x008A0E29, 0xE2, 0xCA},
};

}  // namespace

int ApplyPartySelectAll() {
    if (probe::ConfigInt("partyselect_all", 1) == 0) {
        log::Write("uipatch: party selection patch disabled by config (partyselect_all=0)");
        return 0;
    }
    if (probe::ConfigInt("party32_gui", 0) != 0 && probe::ConfigInt("party32", 0) != 0) {
        log::Write("uipatch: skipped, the paged party screen (party32_gui) replaces it");
        return 0;
    }
    constexpr int kCount = static_cast<int>(sizeof(kSites) / sizeof(kSites[0]));
    for (int i = 0; i < kCount; ++i) {
        int now = 0;
        void* addr = reinterpret_cast<void*>(static_cast<uintptr_t>(kSites[i].address));
        if (!probe::ReadMem(addr, 0, 1, &now) || now != kSites[i].expected) {
            log::Writef("uipatch: party selection patch NOT applied: site %d at 0x%08X holds 0x%02X, expected 0x%02X",
                        i, kSites[i].address, now, kSites[i].expected);
            return 0;
        }
    }
    int changed = 0;
    for (int i = 0; i < kCount; ++i) {
        void* addr = reinterpret_cast<void*>(static_cast<uintptr_t>(kSites[i].address));
        if (probe::WriteCode(addr, 1, kSites[i].patched, nullptr)) ++changed;
    }
    log::Writef("uipatch: party selection shows both of each exclusive pair (%d of %d bytes changed)", changed, kCount);
    return changed;
}

}  // namespace uipatch
}  // namespace k2se
