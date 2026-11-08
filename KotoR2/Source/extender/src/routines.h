#pragma once
#include <cstdint>

namespace k2se {
namespace routines {

// Presence probe. A script cannot test for K2SE by calling a K2SE function --
// that call IS the failure mode when K2SE is absent. So the probe rides on
// abs(), vanilla routine 77, declared in every unmodified nwscript.nss:
//
//     abs(K2SE_PROBE_MAGIC)  ->  version code   (K2SE present)
//     abs(K2SE_PROBE_MAGIC)  ->  1234567890     (K2SE absent, plain abs)
//
// Costs zero routine IDs and needs no extended header.
constexpr int kProbeMagic = -1234567890;

// major*10000 + minor*100 + patch. Never 0: 0 means "K2SE absent".
constexpr int kVersionEncoded =
    K2SE_VERSION_MAJOR * 10000 + K2SE_VERSION_MINOR * 100 + K2SE_VERSION_PATCH;
static_assert(kVersionEncoded != 0, "version 0.0.0 is indistinguishable from 'K2SE absent'");

void Init();

// True if K2SE wants to look at this vanilla routine ID at all. Kept as cheap
// as possible: it runs on every single script action the game dispatches.
bool Intercepts(int id);

// Handles an intercepted vanilla ID. Returns false to fall through to the
// engine unchanged.
bool DispatchVanillaOverride(void* self, int id, int nParams, int* result);

// Handles an ID >= 877. Returns the engine's own out-of-range code for
// anything unregistered, so K2SE's failure mode is identical to vanilla's.
int DispatchExtended(void* self, int id, int nParams);

}  // namespace routines
}  // namespace k2se
