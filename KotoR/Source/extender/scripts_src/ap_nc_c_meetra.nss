#include "kse"

int StartingConditional()
{
    return !(FindSubString(GetName(GetObjectByTag("HK47")), "Meetra") >= 0 || FindSubString(GetName(GetObjectByTag("t3m4")), "Meetra") >= 0);
}
