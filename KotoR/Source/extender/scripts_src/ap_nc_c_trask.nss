#include "kse"

int StartingConditional()
{
    return !(FindSubString(GetName(GetObjectByTag("HK47")), "Trask") >= 0 || FindSubString(GetName(GetObjectByTag("t3m4")), "Trask") >= 0);
}
