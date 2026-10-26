#include "kse"

int StartingConditional()
{
    return !(FindSubString(GetName(GetObjectByTag("t3m4")), "Meetra") < 0 && FindSubString(GetName(GetObjectByTag("t3m4")), "Malak") < 0 && FindSubString(GetName(GetObjectByTag("t3m4")), "Calo") < 0 && FindSubString(GetName(GetObjectByTag("t3m4")), "Yuthura") < 0 && FindSubString(GetName(GetObjectByTag("t3m4")), "Bandon") < 0 && FindSubString(GetName(GetObjectByTag("t3m4")), "Trask") < 0);
}
