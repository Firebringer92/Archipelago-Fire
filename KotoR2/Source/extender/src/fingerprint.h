#pragma once

namespace k2se {
namespace fingerprint {

enum class Verdict {
    kMatch,          // this is the build we know; hooking is safe
    kWrongBuild,     // a probe disagreed -> install nothing
    kNotLoaded,      // could not read the image at all
};

// Checks the loaded swkotor2.exe against the recorded probe set:
// PE identity (TimeDateStamp, ImageBase), the CSWVirtualMachineCommands vtable
// contents, the two 877 bound constants, the 0x0DB4 allocation size, and the
// struct-offset bytes.
//
// The PE Characteristics field is deliberately MASKED OUT: the 4GB/LAA patch
// flips it from 0x0103 to 0x0123 and a huge share of real installs are patched.
// Rejecting those would be rejecting the users we are built for.
Verdict Check();

// Human-readable reason for the last verdict; always safe to call.
const char* LastFailure();

// Census of other DLLs occupying proxy slots in the game folder, so a wrapper
// conflict is diagnosable from the log alone.
void LogEnvironment();

}  // namespace fingerprint
}  // namespace k2se
