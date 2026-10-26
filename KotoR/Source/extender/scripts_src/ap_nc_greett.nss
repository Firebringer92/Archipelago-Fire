#include "kse"

int StartingConditional()
{
    string sWho = "T3-M4";
    if (FindSubString(GetName(GetObjectByTag("t3m4")), "Meetra") >= 0) sWho = "Meetra Surik";
    if (FindSubString(GetName(GetObjectByTag("t3m4")), "Malak") >= 0) sWho = "Darth Malak";
    if (FindSubString(GetName(GetObjectByTag("t3m4")), "Calo") >= 0) sWho = "Calo Nord";
    if (FindSubString(GetName(GetObjectByTag("t3m4")), "Yuthura") >= 0) sWho = "Yuthura Ban";
    if (FindSubString(GetName(GetObjectByTag("t3m4")), "Bandon") >= 0) sWho = "Darth Bandon";
    if (FindSubString(GetName(GetObjectByTag("t3m4")), "Trask") >= 0) sWho = "Trask Ulgo";
    SetCustomToken(9013, "In T3-M4's place now: " + sWho + ".");
    return TRUE;
}
