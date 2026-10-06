// TEMPORARY (loot-window memory-hunting research) -- wired
// onto partpile001.utp's OnOpen field (was empty, no original to
// preserve) purely for research: resolves OBJECT_SELF (this specific
// container, guaranteed-correct via the engine's own object system, no
// candidate hunting needed) and logs its type/quantity fields via
// KSE_ResolveItemId. This is the REAL "Parts Pile" on the Endar Spire
// (end_m01aa) -- distinct from the
// decorative plc_partpile template (Useable=0/HasInventory=0, can never
// fire OnOpen) mistakenly targeted first. partpile001 has only 2
// placements game-wide (end_m01aa, lev_m40ad).
// Retire (delete this
// file, remove Override/partpile001.utp, remove the .ncs) once this
// research concludes.
#include "kse"

void main()
{
    KSE_Diag(158, "AP|APPLIED|ap_pp001_open|ONOPEN_FIRED");
    KSE_ResolveItemId(OBJECT_SELF, 0, 0);
}
