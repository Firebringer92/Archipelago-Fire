#include "kse"

int StartingConditional()
{
    string sWho = "HK-47";
    if (FindSubString(GetName(GetObjectByTag("HK47")), "Meetra") >= 0) sWho = "Meetra Surik";
    if (FindSubString(GetName(GetObjectByTag("HK47")), "Malak") >= 0) sWho = "Darth Malak";
    if (FindSubString(GetName(GetObjectByTag("HK47")), "Calo") >= 0) sWho = "Calo Nord";
    if (FindSubString(GetName(GetObjectByTag("HK47")), "Yuthura") >= 0) sWho = "Yuthura Ban";
    if (FindSubString(GetName(GetObjectByTag("HK47")), "Bandon") >= 0) sWho = "Darth Bandon";
    if (FindSubString(GetName(GetObjectByTag("HK47")), "Trask") >= 0) sWho = "Trask Ulgo";
    SetCustomToken(9013, "In HK-47's place now: " + sWho + ".");
    return TRUE;
}
