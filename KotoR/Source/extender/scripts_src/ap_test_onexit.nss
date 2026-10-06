// ONE-OFF TEST SCRIPT -- not part of the live pipeline. Tests whether
// KOTOR 1's OnExit area event actually fires at all in this engine build.
// Set directly into kas_m23ad's ARE data (which had an empty OnExit) so
// this is read fresh on the area's first load this session -- avoids the
// earlier ambiguity where a mid-session edit to an already-loaded area's
// ARE data might not be picked up until a restart.
#include "kse"

void main()
{
    KSE_Diag(111, "AP|TEST_ONEXIT_FIRED|" + GetTag(GetArea(OBJECT_SELF)));
}
