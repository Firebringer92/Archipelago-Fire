#pragma once
#include <cstdint>

#include "exostring.h"

// ============================================================================
// The NWScript VM operand stack.
//
// K2SE_ENABLE_STACK_ABI -- ON. DESIGN.md Q5 is resolved.
//
// The ABI was not guessed; it was read out of the engine's own handlers: the int
// pair from the abs() branch of the math handler 0x0068C4A0, the float pair from
// its trig/pow branches, the object pair from GetArea (0x0067A070) and GetFirstPC
// (0x006875E0). Every accessor is the same shape:
//
//     mov ecx, dword ptr [0xA1B4A8]    ; ECX = the CVirtualMachine singleton
//     call <accessor>                  ; EAX != 0 = success
//
// Confirmed three ways since: exercised in a live session (2026-08-27), matched
// against an independently produced address database (2026-08-28), and the whole
// 13-entry thunk family disassembled and found byte-identical apart from the
// inner rel32.
//
// ARGUMENT ORDER: arguments pop in DECLARATION order. Ground truth is the pow
// branch -- pow(fValue, fExponent) is non-commutative, and the FIRST popped float
// is what the handler feeds CRT pow() as the base. Confirmed end to end in game
// by routine 878.
//
// Errors are the engine's own: -2001 pop failed, -2000 push failed.
// ============================================================================
#define K2SE_ENABLE_STACK_ABI 1

namespace k2se {
namespace vmstack {

// The VM singleton, exactly as every engine handler obtains it. Null before the
// VM is constructed, so every accessor tolerates that.
void* VirtualMachine();

bool PopInt(int* out);
bool PushInt(int value);

bool PopFloat(float* out);
bool PushFloat(float value);

bool PopObject(uint32_t* out);
bool PushObject(uint32_t objectId);

// Confirmed 2026-08-28: pop is the standard thunk (ret 4), push takes three
// floats by value (ret 0xC). Not yet exercised in game -- the first routine
// using them needs a self-test.
bool PopVector(float out[3]);
bool PushVector(float x, float y, float z);

// `out` must already be constructed: the engine copy-assigns into it. `in` stays
// ours -- the engine allocates and copies. See exostring.h.
bool PopString(ExoString* out);
bool PushString(ExoString* in);

// Engine structures: effect / event / location / talent.
//
// The ACCESSORS are verified. The TYPE TAGS are not -- they come from a
// third-party header and no vanilla handler has been read to confirm what value
// means what on this build. Passing a wrong tag would have the engine reinterpret
// a pointer as the wrong structure type. Nothing in K2SE calls these yet; they
// exist so the plumbing is in place when a tag has been established.
bool PopEngineStructure(int type, void** out);
bool PushEngineStructure(int type, void* value);

}  // namespace vmstack
}  // namespace k2se
