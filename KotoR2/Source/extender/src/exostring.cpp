#include "exostring.h"

#include "log.h"
#include "offsets.h"

namespace k2se {
namespace {

// All __thiscall, all returning `this` in EAX (the MSVC constructor convention).
using CtorDefaultFn = void*(__thiscall*)(void* self);
using CtorCStrFn = void*(__thiscall*)(void* self, const char* src);
using DtorFn = void*(__thiscall*)(void* self);

// A ceiling for the terminator scan, used only when the capacity field cannot
// bound it. No CExoString this engine builds comes close to a megabyte; the
// number exists so that a corrupt pointer costs a wrong answer rather than a
// walk off the end of the heap.
constexpr uint32_t kMaxScan = 1u << 20;

}  // namespace

ExoString::ExoString() : constructed_(false) {
    Construct(nullptr);
}

ExoString::ExoString(const char* text) : constructed_(false) {
    Construct(text);
}

void ExoString::Construct(const char* text) {
    // Zero first. If the engine call is somehow not made, the shell still looks
    // like a valid empty string rather than holding stack garbage -- which is
    // the difference between a harmless no-op and the engine free()ing whatever
    // happened to be on the stack.
    for (uint8_t& b : storage_) b = 0;

    static_assert(off::kExoStringSize == sizeof(storage_),
                  "CExoString is 8 bytes on this build; see offsets.h");

    if (text == nullptr) {
        auto ctor = reinterpret_cast<CtorDefaultFn>(off::kExoStringCtorDefault);
        ctor(storage_);
    } else {
        auto ctor = reinterpret_cast<CtorCStrFn>(off::kExoStringCtorCStr);
        ctor(storage_, text);
    }
    constructed_ = true;
}

ExoString::~ExoString() {
    if (!constructed_) return;
    // Frees the game-owned buffer and nulls the pointer. Running this exactly
    // once per construction is the whole contract.
    auto dtor = reinterpret_cast<DtorFn>(off::kExoStringDtor);
    dtor(storage_);
    constructed_ = false;
}

const char* ExoString::c_str() const {
    const char* p = *reinterpret_cast<const char* const*>(storage_ + off::kExoStringOffCStr);
    return p ? p : "";
}

uint32_t ExoString::buffer_size() const {
    return *reinterpret_cast<const uint32_t*>(storage_ + off::kExoStringOffBufferLength);
}

uint32_t ExoString::length() const {
    // Computed the way the engine computes it. GetStringLength (routine 59,
    // handler 0x00688DE0) pops the CExoString and calls strlen on CStr; it never
    // looks at the second field, because that field is the buffer capacity and
    // not the string -- and after a reassignment that reuses the buffer, the two
    // differ by an unbounded amount. So scan, and use the capacity only to BOUND
    // the scan, which is the one thing it is genuinely good for.
    //
    // A CExoString cannot carry an embedded terminator on this engine: every
    // path that fills one goes through strlen/strcpy or memcpy-then-terminate.
    const char* p =
        *reinterpret_cast<const char* const*>(storage_ + off::kExoStringOffCStr);
    if (!p) return 0;  // what GetStringLength answers for a null CStr

    const uint32_t capacity = buffer_size();
    const uint32_t limit = (capacity > 0 && capacity <= kMaxScan) ? capacity - 1 : kMaxScan;

    uint32_t n = 0;
    while (n < limit && p[n] != '\0') ++n;
    return n;
}

}  // namespace k2se
