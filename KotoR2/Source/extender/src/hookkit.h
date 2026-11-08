#pragma once
#include <cstddef>
#include <cstdint>

// Small code-patching kit for the party roster extension: verified byte patches and "detours" that
// jump to one of our functions, run it with chosen arguments, and either continue with the displaced
// original bytes or resume somewhere else. The design mirrors the 74 hooks of the Patch Manager mod
// PartyRosterLimit32K2 (MIT, by Vriff, github.com/LaneDibello/Kotor-Patch-Manager); the stubs here are
// our own implementation.
//
// Every patch is verified first: the bytes at the address must equal the expected original, or nothing
// at that address is written. Patches are confined to the executable's code range (probe::WriteCode).

namespace k2se {
namespace hookkit {

// Which value a handler argument takes at the moment the hook runs.
enum class ArgKind : uint8_t {
    kEax, kEcx, kEdx, kEbx, kEbp, kEsi, kEdi,  // the register's value
    kStackArg,                                 // address of the caller's stack argument: [esp+4] is offset 4 (function entry hooks only)
};

struct Arg {
    ArgKind kind;
    int offset;  // kStackArg only: distance from the entry stack pointer (4 = first argument)
};

// Register that receives the handler's return value (restored last, so it overrides the saved value).
enum class ResultReg : uint8_t { kNone, kEax, kEcx, kEdx };

struct Detour {
    const char* name;
    uint32_t address;            // first byte replaced
    const uint8_t* original;     // expected bytes at the address
    size_t length;               // number of bytes replaced (a whole number of instructions, at least 5)
    void* handler;               // __cdecl function; arguments are pushed as described by args
    const Arg* args;
    size_t argCount;
    bool skipOriginal;           // do not run the displaced bytes afterwards
    ResultReg result;            // where the handler's return value goes
    uint32_t consumedExit;       // if nonzero: a nonzero return value means "handled": registers are restored, the return value
                                 // stays in eax, and execution jumps to this address instead of continuing
};

// Writes `repl` over `expected` at `address` if the current bytes equal `expected`. n is 1..8.
bool PatchBytes(uint32_t address, const uint8_t* expected, const uint8_t* repl, size_t n);

// True if every byte matches (nothing is written). Used to verify a whole table before applying any of it.
bool CheckBytes(uint32_t address, const uint8_t* expected, size_t n);

// Builds the stub and redirects the site to it. False (and nothing written) on a mismatch or any failure.
bool InstallDetour(const Detour& d);

}  // namespace hookkit
}  // namespace k2se
