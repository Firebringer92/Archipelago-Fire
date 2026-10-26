#include "kse"

int StartingConditional()
{
    return !(FindSubString(GetName(GetObjectByTag("HK47")), "Calo") >= 0 || FindSubString(GetName(GetObjectByTag("t3m4")), "Calo") >= 0);
}
