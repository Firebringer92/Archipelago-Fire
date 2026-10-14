#include "kse"

int StartingConditional()
{
    return !GetHasFeat(6, GetPCSpeaker()) && GetRacialType(GetPCSpeaker()) != 5;
}
