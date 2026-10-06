// TEMPORARY (loot-window memory-hunting research) -- wired
// onto plc_rubble.utp's OnOpen field (was empty, no original to preserve)
// purely for research: resolves OBJECT_SELF (this specific container,
// guaranteed-correct via the engine's own object system, no candidate
// hunting needed) and logs its type/quantity fields via KSE_ResolveItemId.
// Retire (restore the
// real vanilla plc_rubble.utp) once this research concludes -- see
// patch scripts' existing --restore conventions for the pattern.
#include "kse"

void main()
{
    KSE_ResolveItemId(OBJECT_SELF, 0, 0);
}
