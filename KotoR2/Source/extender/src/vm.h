#pragma once
#include <cstdint>

namespace k2se {
namespace vm {

// ExecuteCommand is __thiscall(this, nCommandId, nParameters) with `ret 8`.
// __fastcall with a dummy EDX parameter reproduces that exactly in C++:
// ECX = this, EDX = ignored, then two stack arguments, callee cleans 8 bytes.
using ExecuteCommandFn = int(__fastcall*)(void* self, void* edx, int id, int nParams);

// Swaps vtable slot[2] (0x009940D8) for our thunk, saving the original.
// .rdata is read-only, so this VirtualProtects, writes, and restores.
bool InstallHook();
void RemoveHook();

// Calls the engine's original ExecuteCommand.
int CallOriginal(void* self, int id, int nParams);

// Number of dispatches seen since load (all IDs, including pass-through).
uint64_t ForwardedCallCount();

// Reads m_pCommands off a live CSWVirtualMachineCommands instance.
void** CommandTable(void* self);

}  // namespace vm
}  // namespace k2se
