#include "vmstack.h"

#include "offsets.h"

namespace k2se {
namespace vmstack {
namespace {

using PopIntegerFn = int(__thiscall*)(void* vm, int* out);
using PushIntegerFn = int(__thiscall*)(void* vm, int value);
using PopFloatFn = int(__thiscall*)(void* vm, float* out);
using PushFloatFn = int(__thiscall*)(void* vm, float value);
using PopObjectFn = int(__thiscall*)(void* vm, uint32_t* out);
using PushObjectFn = int(__thiscall*)(void* vm, uint32_t objectId);
using PopVectorFn = int(__thiscall*)(void* vm, float* out);
using PushVectorFn = int(__thiscall*)(void* vm, float x, float y, float z);
using PopStringFn = int(__thiscall*)(void* vm, void* out);
using PushStringFn = int(__thiscall*)(void* vm, void* value);
using PopEngineStructureFn = int(__thiscall*)(void* vm, int type, void** out);
using PushEngineStructureFn = int(__thiscall*)(void* vm, int type, void* value);

}  // namespace

void* VirtualMachine() {
    return *reinterpret_cast<void**>(off::kVirtualMachineGlobal);
}

#if K2SE_ENABLE_STACK_ABI

bool PopInt(int* out) {
    void* vm = VirtualMachine();
    if (!vm) return false;
    return reinterpret_cast<PopIntegerFn>(off::kStackPopInteger)(vm, out) != 0;
}

bool PushInt(int value) {
    void* vm = VirtualMachine();
    if (!vm) return false;
    return reinterpret_cast<PushIntegerFn>(off::kStackPushInteger)(vm, value) != 0;
}

bool PopFloat(float* out) {
    void* vm = VirtualMachine();
    if (!vm) return false;
    return reinterpret_cast<PopFloatFn>(off::kStackPopFloat)(vm, out) != 0;
}

bool PushFloat(float value) {
    void* vm = VirtualMachine();
    if (!vm) return false;
    return reinterpret_cast<PushFloatFn>(off::kStackPushFloat)(vm, value) != 0;
}

bool PopObject(uint32_t* out) {
    void* vm = VirtualMachine();
    if (!vm) return false;
    return reinterpret_cast<PopObjectFn>(off::kStackPopObject)(vm, out) != 0;
}

bool PushObject(uint32_t objectId) {
    void* vm = VirtualMachine();
    if (!vm) return false;
    return reinterpret_cast<PushObjectFn>(off::kStackPushObject)(vm, objectId) != 0;
}

bool PopVector(float out[3]) {
    void* vm = VirtualMachine();
    if (!vm) return false;
    return reinterpret_cast<PopVectorFn>(off::kStackPopVector)(vm, out) != 0;
}

bool PushVector(float x, float y, float z) {
    void* vm = VirtualMachine();
    if (!vm) return false;
    return reinterpret_cast<PushVectorFn>(off::kStackPushVector)(vm, x, y, z) != 0;
}

bool PopString(ExoString* out) {
    void* vm = VirtualMachine();
    // The engine copy-assigns into `out`, which frees whatever pointer it finds
    // there first. Handing it an unconstructed shell is a free() of stack
    // garbage, so refuse rather than risk it.
    if (!vm || !out || !out->valid()) return false;
    return reinterpret_cast<PopStringFn>(off::kStackPopString)(vm, out->raw()) != 0;
}

bool PushString(ExoString* in) {
    void* vm = VirtualMachine();
    if (!vm || !in || !in->valid()) return false;
    return reinterpret_cast<PushStringFn>(off::kStackPushString)(vm, in->raw()) != 0;
}

bool PopEngineStructure(int type, void** out) {
    void* vm = VirtualMachine();
    if (!vm || !out) return false;
    *out = nullptr;
    return reinterpret_cast<PopEngineStructureFn>(off::kStackPopEngineStructure)(
               vm, type, out) != 0;
}

bool PushEngineStructure(int type, void* value) {
    void* vm = VirtualMachine();
    if (!vm) return false;
    return reinterpret_cast<PushEngineStructureFn>(off::kStackPushEngineStructure)(
               vm, type, value) != 0;
}

#else  // !K2SE_ENABLE_STACK_ABI

// Kill switch. With the ABI disabled K2SE must never touch the VM stack: a
// half-correct pop desynchronizes it and produces a subtly wrong game rather
// than a clean crash.
bool PopInt(int*) { return false; }
bool PushInt(int) { return false; }
bool PopFloat(float*) { return false; }
bool PushFloat(float) { return false; }
bool PopObject(uint32_t*) { return false; }
bool PushObject(uint32_t) { return false; }
bool PopVector(float[3]) { return false; }
bool PushVector(float, float, float) { return false; }
bool PopString(ExoString*) { return false; }
bool PushString(ExoString*) { return false; }
bool PopEngineStructure(int, void**) { return false; }
bool PushEngineStructure(int, void*) { return false; }

#endif

}  // namespace vmstack
}  // namespace k2se
