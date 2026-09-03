// STABLE dispatcher, deployed once and never rewritten. Called from every
// area's poll (via ap_poll_shared.ncs main()) on EVERY covered area
// transition, not tied to one specific module. Runs whatever is currently
// staged in ap_pending_target.ncs (rewritten by the extender's ap_apply()
// on each new stage), then reports completion so the extender can reset
// ap_pending_target.ncs back to noop -- otherwise the same grant would
// keep re-firing on every subsequent area transition.
#include "kse"

void main()
{
    ExecuteScript("ap_pending_target", OBJECT_SELF);
    KSE_Diag(94, "AP|PENDING_FIRED");
}
