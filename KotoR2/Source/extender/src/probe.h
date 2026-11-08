#pragma once
#include <cstddef>

// Generic research probes: bounded, fault-tolerant access to process memory and a
// tiny config file. Nothing here knows what any field MEANS; scripts and offline
// tools decide that. Every function returns a failure value instead of faulting.
//
// The config file lives at %LOCALAPPDATA%\K2SE\config.txt (never the game
// directory), one "key=value" per line, '#' starts a comment. It is read on every
// call, so editing it changes behaviour without a rebuild, a recompile or a game
// restart. Because it is outside anything a shipped script can write, it is the
// gate for the dangerous probes.

namespace k2se {
namespace probe {

// Returned by routines that read memory when the read could not be done. A real
// 32-bit value can equal it, so a script comparing against it should also read
// the log line that explains the failure.
constexpr int kReadFailed = -2147483647;

// Copies up to n bytes, stopping at the first page that is not committed or not
// readable. Returns the number of bytes copied (0 on an immediate failure).
size_t SafeCopy(void* dst, const void* src, size_t n);

// Reads a 1, 2 or 4 byte little-endian value at base+offset. False on failure.
bool ReadMem(const void* base, int offset, int width, int* out);

// Writes a 1, 2 or 4 byte value at base+offset, only if the page is writable.
// Reports the previous value. False on failure. Callers must gate this.
bool WriteMem(void* base, int offset, int width, int value, int* oldValue);

// Writes a 1, 2 or 4 byte value at an absolute address, only if that page is committed and
// writable and the whole value fits in it. No offset ceiling, so it is for callers that have
// already validated the address themselves (cwrite.cpp). False on failure.
bool WriteAbs(void* addr, int width, int value, int* oldValue);

// Research only: writes a 1, 2 or 4 byte value into the game's own code (the executable's code section, 0x401000..0x986000), restoring the page
// protection afterwards. Used to try an engine limit changed in memory; callers must gate it.
bool WriteCode(void* addr, int width, int value, int* oldValue);

// Value of "key" in config.txt (decimal or 0x hex), or fallback if absent.
int ConfigInt(const char* key, int fallback);

// Writes up to size bytes starting at base to %LOCALAPPDATA%\K2SE\dumps\<label>.bin
// (label is reduced to letters, digits, '_' and '-'). Returns bytes written, or
// -1 if the file could not be created.
int DumpMem(const void* base, int size, const char* label);

}  // namespace probe
}  // namespace k2se
