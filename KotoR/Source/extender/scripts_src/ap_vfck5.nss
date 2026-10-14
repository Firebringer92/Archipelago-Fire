#include "kse"

int StartingConditional()
{
    return !GetHasFeat(5, GetPCSpeaker()) && GetRacialType(GetPCSpeaker()) != 5;
}
