// Area transitions without gathering the party (0.2.1).
//
// The game refuses an area transition while a companion stands too far from the leader ("You must gather your party before venturing forth.").
// Doors, area triggers, the map screen's travel button and the transition prompt all ask the same function:
//   CSWParty::IsPartyTogether (0x00635350, Steam swkotor.exe 1.03)   int __thiscall (party), a distance check only, no stack arguments.
// It is replaced with "return 1", so the transition always goes ahead; the game places the party around the leader on the other side.

#include <windows.h>
#include <stdint.h>
#include <string.h>

#include "log.h"

namespace {

constexpr uintptr_t kIsPartyTogetherVa = 0x00635350u;

// Expected original bytes of IsPartyTogether (verified against the decrypted image).
constexpr uint8_t kOriginal[] = {0xA1, 0xFC, 0x39, 0x7A, 0x00, 0x83, 0xEC, 0x18, 0x56, 0x57, 0x8B, 0xF9};

constexpr uint8_t kAlwaysTrue[] = {0xB8, 0x01, 0x00, 0x00, 0x00, 0xC3};   // mov eax, 1 / ret

}  // namespace

// Called once from the worker thread, after the code is decrypted. Never throws; leaves the game untouched on any mismatch.
bool PartyGatherInstall() {
    void* target = reinterpret_cast<void*>(kIsPartyTogetherVa);
    if (memcmp(target, kOriginal, sizeof(kOriginal)) != 0) {
        Log("partygather: NOT installed: the code at IsPartyTogether is not the expected original");
        return false;
    }
    DWORD old = 0;
    if (!VirtualProtect(target, sizeof(kAlwaysTrue), PAGE_EXECUTE_READWRITE, &old)) {
        Log("partygather: NOT installed: the code could not be made writable");
        return false;
    }
    memcpy(target, kAlwaysTrue, sizeof(kAlwaysTrue));
    VirtualProtect(target, sizeof(kAlwaysTrue), old, &old);
    FlushInstructionCache(GetCurrentProcess(), target, sizeof(kAlwaysTrue));
    Log("partygather: installed (area transitions no longer require the party to be gathered)");
    return true;
}
