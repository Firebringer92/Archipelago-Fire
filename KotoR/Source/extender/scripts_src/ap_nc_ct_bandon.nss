#include "kse"

int StartingConditional()
{
    return !(FindSubString(GetName(GetObjectByTag("HK47")), "Bandon") >= 0 || FindSubString(GetName(GetObjectByTag("t3m4")), "Bandon") >= 0);
}
