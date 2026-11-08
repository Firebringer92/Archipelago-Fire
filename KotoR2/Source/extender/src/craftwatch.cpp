#include "craftwatch.h"

#include <windows.h>

#include "gameobj.h"
#include "log.h"
#include "offsets.h"
#include "probe.h"

namespace k2se {
namespace craftwatch {
namespace {

constexpr int kPollMs = 50;
constexpr int kConfigEvery = 40;                 // polls between config reads
constexpr int kPurseOffset = 0x1F0B4 + 0x170;    // from [server+4]; same chain as SetPartyCredits (cwrite.cpp)

bool ReadPurse(int* gold, int* components, int* chemicals) {
    int appManager = 0;
    if (!probe::ReadMem(reinterpret_cast<const void*>(off::kAppManagerGlobal), 0, 4, &appManager)) return false;
    if (!gameobj::LooksLikePointer(reinterpret_cast<void*>(static_cast<uintptr_t>(appManager)))) return false;
    int server = 0;
    if (!probe::ReadMem(reinterpret_cast<const void*>(static_cast<uintptr_t>(appManager)), off::kAppManagerOffServer, 4, &server)) return false;
    if (!gameobj::LooksLikePointer(reinterpret_cast<void*>(static_cast<uintptr_t>(server)))) return false;
    int holder = 0;
    if (!probe::ReadMem(reinterpret_cast<const void*>(static_cast<uintptr_t>(server)), 4, 4, &holder)) return false;
    if (!gameobj::LooksLikePointer(reinterpret_cast<void*>(static_cast<uintptr_t>(holder)))) return false;
    const char* purse = reinterpret_cast<const char*>(static_cast<uintptr_t>(holder)) + kPurseOffset;
    return probe::ReadMem(purse, 0, 4, gold) && probe::ReadMem(purse, 4, 4, components) && probe::ReadMem(purse, 8, 4, chemicals);
}

DWORD WINAPI Run(LPVOID) {
    bool enabled = false;
    int untilConfig = 0;
    bool have = false;
    int lastGold = 0, lastComp = 0, lastChem = 0;
    for (;;) {
        Sleep(kPollMs);
        if (untilConfig-- <= 0) {
            enabled = probe::ConfigInt("craftwatch", 0) == 1;
            untilConfig = kConfigEvery;
        }
        if (!enabled) { have = false; continue; }
        int gold = 0, comp = 0, chem = 0;
        if (!ReadPurse(&gold, &comp, &chem)) { have = false; continue; }
        if (!have) {
            log::Writef("K2SE CRAFTWATCH start: gold=%d components=%d chemicals=%d", gold, comp, chem);
            have = true;
        } else if (gold != lastGold || comp != lastComp || chem != lastChem) {
            log::Writef("K2SE CRAFTWATCH gold=%d (%+d) components=%d (%+d) chemicals=%d (%+d)",
                        gold, gold - lastGold, comp, comp - lastComp, chem, chem - lastChem);
        }
        lastGold = gold; lastComp = comp; lastChem = chem;
    }
}

}  // namespace

void Start() {
    HANDLE h = CreateThread(nullptr, 0, &Run, nullptr, 0, nullptr);
    if (h) CloseHandle(h);
}

}  // namespace craftwatch
}  // namespace k2se
