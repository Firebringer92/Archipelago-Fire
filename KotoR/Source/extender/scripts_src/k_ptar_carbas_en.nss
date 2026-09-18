// Trampoline for the Taris Hideout "escape plan" scene's real OnEnter
// script (originally tar_m02af's k_ptar_carbas_en, trigger tag
// tar02_carbas, preserved byte-exact as apo_carbast_orig -- starts
// dialogue tar02_carbast once its gate passes). See
// ap_companion_gate.nss's own header for the full shared root-cause
// story (this scene and the Dantooine Jedi Council wrap-up family both
// need Bastila+Carth temporarily present to pass a vanilla gate, and
// both share the exact same temp-grant/bench/revert logic -- folded
// into one shared brain 2026-09-17 rather than duplicated).
//
// Root cause (unchanged from this file's original standalone version):
// the vanilla gate is `IsAvailableCreature(NPC_BASTILA) &&
// IsAvailableCreature(NPC_CARTH)` (confirmed via disassembly -- the
// debug string "SPAWNING CARTH AND BASTILA" is compiled directly into
// apo_carbast_orig). Under companion_mode=ap_gated/none, if neither has
// actually been received yet by the time the player walks into this
// trigger, the gate can never pass, so this scene (and the rest of the
// Taris departure sequence gated behind it) never fires -- a real,
// live-reported story stall, not a hypothetical.
//
// Hard prerequisite: GetJournalEntry("tar_bastsearch") >= 99 -- the real
// (and, confirmed via global.jrl, ONLY) End=1 stage for "Taris: The
// Search for Bastila". Without this, the shared brain's temp-grant logic
// would fire for ANY reason !IsAvailableCreature happens to be true
// under ap_gated/none -- which is also true, for entirely unrelated
// reasons, at every point BEFORE Bastila is ever rescued at all. Passed
// as HandleBastilaCarthGate's bAllowTempGrant parameter rather than
// wrapped around the whole call, so apo_carbast_orig -- the real trigger
// -- still always runs exactly like the original standalone version did
// (its own internal availability gate is what actually decides whether
// anything happens); only the temp-grant/bench/revert dance is
// suppressed when this prerequisite isn't met. The Council family passes
// no third argument (defaults to TRUE) since it has no equivalent
// prerequisite -- it only ever fires from inside an active dialogue
// node, which is its own natural gate.
#include "kse"
#include "ap_companion_gate"

void main()
{
    HandleBastilaCarthGate("apo_carbast_orig", "carbas_en",
                            GetJournalEntry("tar_bastsearch") >= 99);
}
