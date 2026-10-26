#include "kse"

int StartingConditional()
{
    return !(FindSubString(GetName(GetObjectByTag("HK47")), "Yuthura") >= 0 || FindSubString(GetName(GetObjectByTag("t3m4")), "Yuthura") >= 0);
}
