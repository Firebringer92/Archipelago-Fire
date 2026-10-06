// TEMPORARY (loot-window memory-hunting research) -- wired
// onto g_trescivil002.utp's OnOpen field (was empty, no original to
// preserve) purely for research: resolves OBJECT_SELF (this specific
// container, guaranteed-correct via the engine's own object system, no
// candidate hunting needed) and logs its type/quantity fields via
// KSE_ResolveItemId. Retargeted from plc_partpile after confirming that
// template has Useable=0/HasInventory=0 in vanilla (a pure decoration
// prop, OnOpen can never fire on it) -- g_trescivil002 ("Bag", tag
// CivilBagStrap) is a REAL container (Useable=1/HasInventory=1),
// scoped to only 3 placements, all inside tar_m02aa.
// Retire (delete this file, remove Override/g_trescivil002.utp, remove
// the .ncs) once this research concludes.
#include "kse"

void main()
{
    KSE_ResolveItemId(OBJECT_SELF, 0, 0);
}
