#pragma once
#include <cstdint>

namespace k2se {

// A CExoString the engine will accept, with the engine's own lifetime rules.
//
// The struct is 8 bytes -- { char* CStr; uint32_t BufferLength; } -- and the
// second field is a capacity, not a length (offsets.h says why, with the
// disassembly). The buffer it
// points at belongs to the GAME's allocator, not ours. So this holds the 8-byte
// shell inline (no heap of our own is involved at all) and drives the engine's
// real constructor and destructor over it. Freeing the inner buffer ourselves,
// or letting the shell die without running the engine destructor, would each
// corrupt the game's heap.
//
// Ownership across the VM boundary, read out of the engine rather than assumed
// (see offsets.h):
//
//   PushString  the engine allocates its OWN CExoString and copies from ours,
//               so ours is still ours and this destructor still runs.
//   PopString   the engine COPY-ASSIGNS into ours, which means ours must already
//               be constructed before it is handed over. Default construction is
//               what makes that safe.
//
// Not copyable: two shells pointing at one game-owned buffer is a double free.
class ExoString {
  public:
    // Empty string. Always safe to hand to PopString.
    ExoString();

    // Copies `text` into a game-allocated buffer via the engine's constructor.
    // A null pointer yields an empty string rather than a crash.
    explicit ExoString(const char* text);

    ~ExoString();

    ExoString(const ExoString&) = delete;
    ExoString& operator=(const ExoString&) = delete;

    // The 8-byte struct, which is what the VM accessors take.
    void* raw() { return storage_; }

    // Borrowed; owned by the game and invalid once this object dies. Never null:
    // an empty engine string reads back as "".
    const char* c_str() const;

    // Characters, not counting the terminator -- the same number vanilla
    // GetStringLength reports for the same string. It is computed, not read:
    // the engine's second field is a buffer capacity (see offsets.h).
    uint32_t length() const;

    // That capacity field, raw: bytes allocated including the terminator, 0 for
    // an empty string. It is an upper bound on length()+1 and equal to it only
    // until the string is reassigned. Exposed for diagnostics and for sizing a
    // copy -- never as a length.
    uint32_t buffer_size() const;

    // False if the engine constructor could not be run. Callers must check
    // before handing this to the VM -- passing an unconstructed shell to
    // PopString would make the engine free() a wild pointer.
    bool valid() const { return constructed_; }

  private:
    void Construct(const char* text);

    // Deliberately raw storage rather than a struct: the engine constructor is
    // what establishes the invariants, so C++ must not think it owns them.
    alignas(4) uint8_t storage_[8];
    bool constructed_;
};

static_assert(sizeof(ExoString) >= 8, "CExoString shell must hold 8 bytes");

}  // namespace k2se
