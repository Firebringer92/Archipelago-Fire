#pragma once
#include <cstdint>

#include "offsets_generated.h"

// =============================================================================
// Addresses for swkotor2.exe -- Aspyr/Steam build, FileVersion 1.0.2.0,
// TimeDateStamp 0x5603005D, ImageBase 0x00400000, RELOCS_STRIPPED (no ASLR).
//
// Provenance of every value in this file: read directly out of the binary.
// tools/verify_offsets.py re-checks all of them and must pass before any
// hook code is trusted. See DESIGN.md section 2.
//
// This file holds the constants K2SE derived by hand, each with the reasoning
// that produced it. The much larger imported table lives in the generated
// offsets_generated.h under `off::game::`, and the two are deliberately kept
// apart: where they overlap, the static_assert block at the bottom of this file
// compares them, so a disagreement between two independent derivations of the
// same address becomes a build failure rather than a runtime mystery.
// =============================================================================

namespace k2se {
namespace off {

constexpr uint32_t kImageBase = 0x00400000;
constexpr uint32_t kTimeDateStamp = 0x5603005D;

// PE Characteristics: 0x0103 pristine, 0x0123 once the 4GB/LAA patch is applied.
// Both are accepted -- many users run the LAA-patched exe. Never hash the whole
// file: that would reject the user's own working install.
constexpr uint16_t kCharacteristicsPristine = 0x0103;
constexpr uint16_t kCharacteristicsLaa = 0x0123;

// --- CSWVirtualMachineCommands ----------------------------------------------
// Found via the MSVC RTTI class-name string ".?AVCSWVirtualMachineCommands@@"
// at 0x00A0F4F8 -> type descriptor -> COL -> vtable.
constexpr uint32_t kRttiClassName = 0x00A0F4F8;
constexpr uint32_t kVTable = 0x009940D0;

constexpr uint32_t kVTableSlot0 = 0x00536BE0;         // ctor/dtor helper
constexpr uint32_t kInitializeCommands = 0x00665F50;  // vtable slot[1]
constexpr uint32_t kExecuteCommand = 0x00668FD0;      // vtable slot[2]  <-- hook target
constexpr uint32_t kVTableSlot3 = 0x00669020;

// The slot we overwrite. &vtable[2].
constexpr uint32_t kVTableSlotExecute = kVTable + 2 * 4;  // 0x009940D8

// Object layout, derived from the instructions that use these offsets.
constexpr uint32_t kCommandsFieldOffset = 0x0C;  // CSWVirtualMachineCommands::m_pCommands
constexpr uint32_t kVmInternalOffset = 0x1C;     // CVirtualMachine::m_pInternal

// --- the routine table ------------------------------------------------------
// InitializeCommands does: push 0DB4h ; new[] ; mov [this+0Ch], eax
// 0x0DB4 == 3508 == 877 * 4, i.e. a flat array of 877 function pointers,
// heap-allocated at runtime (which is why no static scan of .rdata/.data
// ever finds it).
constexpr int kVanillaRoutineCount = 877;  // 0x36D
constexpr uint32_t kTableAllocBytes = 0x0DB4;

// First routine ID K2SE may claim. See DESIGN.md Q3 -- whether IDs >= 877
// actually reach the dispatcher is the project's gating unknown.
constexpr int kFirstExtendedId = kVanillaRoutineCount;  // 877

// --- fingerprint probe sites ------------------------------------------------
constexpr uint32_t kSiteAllocSize = 0x00665F5A;      // dword == 0x0DB4
constexpr uint32_t kSiteInitBound = 0x00665F87;      // dword == 0x36D
constexpr uint32_t kSiteDispatchBound = 0x00668FDC;  // dword == 0x36D
constexpr uint32_t kSiteCmdOffInit = 0x00665F71;     // byte  == 0x0C  (mov [eax+0Ch],ecx)
constexpr uint32_t kSiteCmdOffDispatch = 0x00668FE7; // byte  == 0x0C  (mov ecx,[eax+0Ch])
constexpr uint32_t kSiteVmInternal = 0x006FD9B0;     // byte  == 0x1C  (mov ecx,[ecx+1Ch])

// --- known table entries, for runtime self-validation -----------------------
// Confirmed by tools/extract_routine_table.py against InitializeCommands.
// IDs 67..77 (fabs,cos,sin,tan,acos,asin,atan,log,pow,sqrt,abs) all share one
// handler -- that shared-handler pattern, cross-checked against xoreos-tools'
// independent name list, is what proves this really is the routine table.
constexpr int kRoutineAbs = 77;
constexpr int kRoutineAcos = 71;
constexpr int kRoutineRandom = 0;
constexpr int kRoutineLast = 876;

constexpr uint32_t kHandlerMath = 0x0068C4A0;         // cmds[67..77]
constexpr uint32_t kHandlerRandom = 0x0068F5D0;       // cmds[0]
constexpr uint32_t kHandlerRebuildParty = 0x0069C460; // cmds[876]

// --- engine helpers ---------------------------------------------------------
// void __cdecl AurPostString(const char* text, int x, int y, float fLife)
// On-screen debug text. VERIFIED by disassembly: plain `ret` (cdecl), four
// stack args with the float passed by value; allocates a 0x434-byte text
// object and constructs it via 0x004744D0. Engine call site 0x0040820A passes
// a raw .rdata char* literal (">") and 5.0f -- so `text` is a C string, not a
// CExoString. Used for the K2SE banner and to make a refused install visible
// instead of silently inert.
constexpr uint32_t kAurPostString = 0x00474C00;

// The CVirtualMachine singleton. RESOLVED (DESIGN.md Q5): engine routine
// handlers do NOT derive the VM from their own `this`. They load it from this
// global, e.g. inside the math handler at 0x0068C4A0:
//     mov ecx, dword ptr [0x00A1B4A8]
//     call 0x006FD9A0                  ; StackPopInteger
// The earlier design assumed `self + 0x1C`; that was wrong. 0x1C is used one
// level deeper, INSIDE the accessor (`mov ecx,[ecx+1Ch]`), not by the caller.
constexpr uint32_t kVirtualMachineGlobal = 0x00A1B4A8;

// VM stack accessors -- VERIFIED by disassembly (DESIGN.md Q5 + session of
// 2026-08-26: float pair read out of the shared math handler 0x0068C4A0,
// object pair read out of GetArea 0x0067A070 / GetFirstPC 0x006875E0).
//   int __thiscall StackPopInteger (void* vm, int*   out);   ret 4
//   int __thiscall StackPushInteger(void* vm, int    value); ret 4
//   int __thiscall StackPopFloat   (void* vm, float* out);   ret 4
//   int __thiscall StackPushFloat  (void* vm, float  value); ret 4
//   int __thiscall StackPopObject  (void* vm, uint32_t* out);   ret 4
//   int __thiscall StackPushObject (void* vm, uint32_t objId);  ret 4
// All take the VM in ECX and return EAX != 0 on success; each forwards to
// *(vm + 0x1C) internally. Arguments pop in DECLARATION order (Q6, settled by
// the pow branch: the first pop feeds CRT pow() as the base, i.e. fValue).
constexpr uint32_t kStackPopInteger = 0x006FD9A0;
constexpr uint32_t kStackPushInteger = 0x006FD9C0;
constexpr uint32_t kStackPopFloat = 0x006FD9E0;
constexpr uint32_t kStackPushFloat = 0x006FDA00;
constexpr uint32_t kStackPopObject = 0x006FDAF0;
constexpr uint32_t kStackPushObject = 0x006FDB10;

// Vector pair -- CONFIRMED 2026-08-28. Two things landed at once: the imported
// table names them (CVirtualMachine::StackPopVector / StackPushVector), and
// disassembly shows the predicted shapes exactly -- pop is the same thunk as
// StackPopInteger with `ret 4`, push takes three floats by value with `ret 0xC`.
// The earlier "do not wrap" warning is therefore lifted; still unexercised in
// game, so the first routine to use them needs a self-test.
constexpr uint32_t kStackPopVector = 0x006FDA20;   // (void* vm, float out[3])  ret 4
constexpr uint32_t kStackPushVector = 0x006FDA40;  // (void* vm, float x,y,z)   ret 0xC

// --- strings and engine structures (DESIGN.md Q11, resolved 2026-08-28) -----
// Named by the imported table, then confirmed here by disassembly: both are
// byte-identical thunks to StackPopInteger apart from the inner rel32, so they
// share the ABI K2SE has already exercised in game.
//   int __thiscall StackPopString (void* vm, CExoString* out);  ret 4
//   int __thiscall StackPushString(void* vm, CExoString* in);   ret 4
constexpr uint32_t kStackPopString = 0x006FDA70;
constexpr uint32_t kStackPushString = 0x006FDA90;

// Two arguments, not one (ret 8). Argument order read from the thunk: it pushes
// [ebp+0Ch] then [ebp+8], so the inner call receives ([ebp+8], [ebp+0Ch]).
//   int __thiscall StackPopEngineStructure (void* vm, int type, void** out); ret 8
//   int __thiscall StackPushEngineStructure(void* vm, int type, void* value); ret 8
//
// WARNING: the *type tag* values (effect/event/location/talent) are NOT verified
// on this binary. They come from a third-party header and are a hypothesis, not
// a fact. No K2SE routine may expose these until a consuming vanilla handler has
// been read. The accessors are wrapped so the plumbing exists; the tags are not
// yet trusted.
constexpr uint32_t kStackPopEngineStructure = 0x006FDAB0;
constexpr uint32_t kStackPushEngineStructure = 0x006FDAD0;

// --- CExoString --------------------------------------------------------------
// Layout: { char* CStr; uint32_t BufferLength; } -- 8 bytes.
//
// The size is not taken on trust from a table (the imported database's `classes`
// table is empty for KOTOR 2). It was read out of the engine twice:
//   * the default constructor writes exactly two dwords, at +0x00 and +0x04,
//     and nothing else;
//   * StackPushString's callee does `push 8; call operator new` before invoking
//     CStrConstructor on the result.
constexpr uint32_t kExoStringSize = 8;
constexpr uint32_t kExoStringOffCStr = 0x00;

// The second field is a CAPACITY, not a character count -- it is the size of the
// malloc'd buffer, INCLUDING the terminator, and 0 for an empty string. It was
// called Length here until a live session printed "K2SE-880-abc" (twelve
// characters) as length 13, which is this field telling the exact truth about a
// thirteen-byte allocation.
//
//   ctor(char*)      @0x00733570:  call strlen; add eax,1; mov [this+4],eax;
//                                  malloc(that); strcpy
//   ctor(char*, int) @0x00733680:  [this+4] = len+1; malloc; memcpy; dst[len]=0
//
// Subtracting one is NOT a fix. operator= @0x007337C0 reuses the existing buffer
// whenever strlen(src)+1 fits in it -- `cmp eax,[edx+4]; jbe 0x733829` jumps
// clean past the field update -- so after assigning a short string into a shell
// that once held a long one, this field still reports the OLD capacity. The gap
// between capacity and length is therefore unbounded, not a constant.
//
// The engine settles what "length" means: NWScript GetStringLength (routine 59,
// handler 0x00688DE0) ignores this field entirely and calls strlen on CStr
// (0x00688E56), answering 0 when CStr is null. Anything K2SE reports as a length
// has to match that, or a mod will watch GetStringLength and K2SE disagree about
// one string.
constexpr uint32_t kExoStringOffBufferLength = 0x04;

//   CExoString* __thiscall CExoString::CExoString()                  -- zeroes both fields
//   CExoString* __thiscall CExoString::CExoString(char* src)
//   CExoString* __thiscall CExoString::CExoString(char* src, int len)
//   CExoString* __thiscall CExoString::~CExoString()                 -- frees CStr, nulls it
constexpr uint32_t kExoStringCtorDefault = 0x00733540;
constexpr uint32_t kExoStringCtorCStr = 0x00733570;
constexpr uint32_t kExoStringCtorCStrLen = 0x00733680;
constexpr uint32_t kExoStringDtor = 0x00733780;

// OWNERSHIP, settled by disassembling both callees rather than assumed:
//   StackPushString ALLOCATES ITS OWN 8-byte CExoString and constructs it from
//   our buffer -- it copies. We keep ownership of ours and must destroy it.
//   StackPopString COPY-ASSIGNS into the CExoString we hand it, so that object
//   must already be validly constructed (a zeroed one is fine, a garbage one is
//   a free() of a wild pointer).
// Getting this backwards in either direction is a heap corruption, which is why
// it was read out of the engine instead of inferred from convention.

// --- resolving a script OBJECT id to a live pointer (Track C) ---------------
// DESIGN.md 7 noted that [0x00A1B4A4] is "a second singleton (app/server)"
// without identifying it. It is CAppManager: +0x04 is the client, +0x08 the
// server.
//
//     *(void**)0x00A1B4A4          CAppManager
//       +0x08                      CServerExoApp
//       GetCreatureByGameObjectID  id -> CSWSCreature*, or null
//
// EVERY signature below was verified here by disassembly -- the epilogue's
// `ret imm16` gives the argument size, and all ten agreed with the imported
// table. That check is not optional: __thiscall is callee-cleaned, so calling
// with the wrong argument count silently unbalances the stack rather than
// failing loudly.
constexpr uint32_t kAppManagerGlobal = 0x00A1B4A4;
constexpr uint32_t kAppManagerOffServer = 0x08;

constexpr uint32_t kGetObjectArray = 0x0051C080;               // () ret 0
constexpr uint32_t kGetCreatureByGameObjectID = 0x0051C100;    // (uint32 id) ret 4
constexpr uint32_t kGetPlayerCreatureId = 0x0051C8F0;          // () ret 0
constexpr uint32_t kGameObjectArrayGetGameObject = 0x0053DFB0; // (id, void** out) ret 8

// CSWSCreature -> CSWSCreatureStats. STRUCT OFFSET, not verifiable from the file:
// it is a claim about an object's runtime layout, imported and unconfirmed. Every
// read through it is bounds-checked and guarded, and a wrong value shows up as a
// refused call rather than a crash.
constexpr uint32_t kCreatureOffStats = 0x1198;

// Ability bases are single bytes, two apart: STR 0xED, DEX 0xEF, CON 0xF1,
// INT 0xF3, WIS 0xF5, CHA 0xF7 -- matching NWScript's ABILITY_* ordering.
constexpr uint32_t kStatsOffAbilityBase = 0x00ED;
constexpr uint32_t kStatsAbilityStride = 2;
constexpr int kAbilityCount = 6;

constexpr uint32_t kStatsGetSkillRank = 0x006B7BB0;  // (uint8 skill, void*, int) ret 12
constexpr uint32_t kStatsHasFeat = 0x006B83F0;       // (uint16 feat) ret 4
constexpr uint32_t kStatsHasSpell = 0x006BD9C0;      // (uint8, uint32, int) ret 12

// The engine's own object-id sentinel, seen as the default/failure value in
// GetFirstPC (mov [ebp-4], 0x7F000000) -- matches community OBJECT_INVALID.
constexpr uint32_t kObjectInvalid = 0x7F000000;

// --- accessor call-site probe values ----------------------------------------
// Each is the rel32 of a verified E8 call to the accessor, read from a handler
// that provably uses it. Checking the call site (not the callee's first bytes)
// also re-derives the accessor address at fingerprint time.
constexpr uint32_t kSitePopFloatCall = 0x0068C514;   // dword == 0x000714C8
constexpr uint32_t kSitePopFloatRel = 0x000714C8;    // -> 0x006FD9E0 (math handler)
constexpr uint32_t kSitePushFloatCall = 0x0068C774;  // dword == 0x00071288
constexpr uint32_t kSitePushFloatRel = 0x00071288;   // -> 0x006FDA00 (math handler)
constexpr uint32_t kSitePopObjectCall = 0x0067A0BA;  // dword == 0x00083A32
constexpr uint32_t kSitePopObjectRel = 0x00083A32;   // -> 0x006FDAF0 (GetArea)
constexpr uint32_t kSitePushObjectCall = 0x00687692; // dword == 0x0007647A
constexpr uint32_t kSitePushObjectRel = 0x0007647A;  // -> 0x006FDB10 (GetFirstPC)
// AurPostString prologue: 55 8B EC 6A (push ebp; mov ebp,esp; push -1 ...)
constexpr uint32_t kSiteAurPostString = 0x00474C00;  // dword == 0x6AEC8B55
constexpr uint32_t kAurPostStringPrologue = 0x6AEC8B55;

// --- dispatcher / handler return codes --------------------------------------
// Read straight out of the engine's own error paths:
//   ExecuteCommand out-of-range / NULL slot -> mov eax, 0FFFFF82Eh  (-2002)
//   handler, pop failed                     -> mov eax, 0FFFFF82Fh  (-2001)
//   handler, push failed                    -> mov eax, 0FFFFF830h  (-2000)
// Opaque internal codes; NOT dialog.tlk strrefs.
constexpr int kErrCommandNotFound = -2002;
constexpr int kErrParam = -2001;
constexpr int kErrPushFailed = -2000;

// =============================================================================
// Cross-validation: two independent derivations of the same addresses.
//
// The constants above were obtained by disassembling this executable by hand.
// The `game::` ones were imported from Kotor-Patch-Manager's address database,
// which was produced by someone else, from their own Ghidra work, without
// reference to this project.
//
// Two independent sources agreeing is far stronger evidence than either alone,
// and this is the cheapest possible place to enforce it: if a future import ever
// contradicts a hand-derived value, the build stops. That is the correct
// outcome -- one of the two is wrong, and silently preferring either would be
// guessing.
//
// (The imported database's own description says its Steam rows were auto-ported
// from the GOG build, which is exactly why it does not get to win an argument
// with disassembly.)
// =============================================================================
#define K2SE_CROSSCHECK(ours, theirs)                                              \
    static_assert((ours) == (theirs),                                              \
                  "address disagreement: " #ours " (disassembled here) != " #theirs \
                  " (imported). One of the two is wrong -- resolve it by reading "  \
                  "the binary; do not just pick one. See DESIGN.md 2.")

K2SE_CROSSCHECK(kStackPopInteger, game::kCVirtualMachine_StackPopInteger);
K2SE_CROSSCHECK(kStackPushInteger, game::kCVirtualMachine_StackPushInteger);
K2SE_CROSSCHECK(kStackPopFloat, game::kCVirtualMachine_StackPopFloat);
K2SE_CROSSCHECK(kStackPushFloat, game::kCVirtualMachine_StackPushFloat);
K2SE_CROSSCHECK(kStackPopVector, game::kCVirtualMachine_StackPopVector);
K2SE_CROSSCHECK(kStackPushVector, game::kCVirtualMachine_StackPushVector);
K2SE_CROSSCHECK(kStackPopObject, game::kCVirtualMachine_StackPopObject);
K2SE_CROSSCHECK(kStackPushObject, game::kCVirtualMachine_StackPushObject);
K2SE_CROSSCHECK(kAurPostString, game::kOther_AurPostString);
K2SE_CROSSCHECK(kVirtualMachineGlobal, game::kGlobal_VIRTUAL_MACHINE_PTR);

#undef K2SE_CROSSCHECK

}  // namespace off
}  // namespace k2se
