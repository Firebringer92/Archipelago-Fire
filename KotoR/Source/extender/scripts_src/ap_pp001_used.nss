// TEMPORARY (loot-window memory-hunting research) -- wired
// onto partpile001.utp's OnUsed field, alongside OnOpen (ap_pp001_open),
// purely as a diagnostic: OnOpen was not firing despite multiple confirmed
// open/close interactions, so this tests whether Useable=1 routes the
// interaction through OnUsed instead. Retire alongside ap_pp001_open once
// this research concludes.
#include "kse"

void main()
{
    KSE_Diag(158, "AP|APPLIED|ap_pp001_used|ONUSED_FIRED");
    KSE_ResolveItemId(OBJECT_SELF, 0, 0);
}
