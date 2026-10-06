// One-shot test-prep script: fast-forwards the console-settable prerequisite
// globals for the remaining companion recruitment triggers, so each one can
// be reached by warping straight to its module instead of playing through
// the real quest chain. NOT part of the shipping mod -- test scaffolding only.
//
// Bastila:  Tar_SwoopRace = TRUE           (won the Taris swoop race)
// Jolee:    kas_PoacherJob = TRUE          (poacher encounter resolved)
// Juhani:   DAN_STARMAP_DONE = TRUE,
//           DAN_JUHANI_PLOT = 3            (Star Map found + duel arc done)
// T3-M4:    Tar_Cand_T3 = TRUE             (Canderous told you about the droid;
//                                            still need >=2000 credits live)
#include "kse"

void main()
{
    SetGlobalBoolean("Tar_SwoopRace", TRUE);
    SetGlobalBoolean("kas_PoacherJob", TRUE);
    SetGlobalBoolean("DAN_STARMAP_DONE", TRUE);
    SetGlobalNumber("DAN_JUHANI_PLOT", 3);
    SetGlobalBoolean("Tar_Cand_T3", TRUE);
    KSE_Diag(36, "AP|PREP|companions_flags_set");
}
