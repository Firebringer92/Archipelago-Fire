#include "kse"

int StartingConditional()
{
    return !(FindSubString(GetName(GetObjectByTag("HK47")), "Meetra") < 0 && FindSubString(GetName(GetObjectByTag("HK47")), "Malak") < 0 && FindSubString(GetName(GetObjectByTag("HK47")), "Calo") < 0 && FindSubString(GetName(GetObjectByTag("HK47")), "Yuthura") < 0 && FindSubString(GetName(GetObjectByTag("HK47")), "Bandon") < 0 && FindSubString(GetName(GetObjectByTag("HK47")), "Trask") < 0);
}
