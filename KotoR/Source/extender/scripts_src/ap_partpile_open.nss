// TEMPORARY (loot-window memory-hunting research) -- wired
// onto plc_partpile.utp's OnOpen field (was empty, no original to preserve)
// purely for research: resolves OBJECT_SELF (this specific container,
// guaranteed-correct via the engine's own object system, no candidate
// hunting needed) and logs its type/quantity fields via KSE_ResolveItemId.
// Retargeted from the plc_rubble test onto plc_partpile ("Parts Pile",
// tag PartPile) since plc_rubble only appears on Dantooine/Kashyyyk/
// Korriban/Tatooine/Unknown World, while plc_partpile is placed on Taris
// (tar_m02/m03/m09/m10).
// Retire (delete this
// file, remove Override/plc_partpile.utp, remove the .ncs) once this
// research concludes.
#include "kse"

void main()
{
    KSE_ResolveItemId(OBJECT_SELF, 0, 0);
}
