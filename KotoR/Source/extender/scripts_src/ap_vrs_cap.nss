#include "kse"

int StartingConditional()
{
    return GetLocalNumber(GetPCSpeaker(), 62) < 5 && GetRacialType(GetPCSpeaker()) != 5;
}
