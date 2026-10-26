#include "kse"

int StartingConditional()
{
    return !(FindSubString(GetName(GetObjectByTag("HK47")), "Malak") >= 0 || FindSubString(GetName(GetObjectByTag("t3m4")), "Malak") >= 0);
}
