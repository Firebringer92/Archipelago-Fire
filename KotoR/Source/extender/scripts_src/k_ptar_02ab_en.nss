// TEST-ONLY: wraps tar_m02ab's real Mod_OnModLoad hook. Module-load re-fire
// on genuine re-entry is now confirmed. This second test checks the
// remaining open question: does a SINGLE ExecuteScript hop from this
// NATIVELY-triggered hook into a resref whose CONTENT CHANGES between
// calls (ap_pending_target, same file the broken 2-hop area-poll test
// used) actually pick up the current content, or does it also hit the
// same staleness the 2-hop test did?
#include "kse"

void main()
{
    ExecuteScript("apo_modtest_orig", OBJECT_SELF);
    KSE_Diag(98, "AP|MODLOADTEST|fired");
    ExecuteScript("ap_pending_target", OBJECT_SELF);
    KSE_Diag(99, "AP|MODLOADTEST|pending_done");
}
