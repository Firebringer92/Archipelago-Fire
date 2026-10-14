#include "kse"

int StartingConditional()
{
    return !GetHasFeat(4, GetPCSpeaker()) && GetRacialType(GetPCSpeaker()) != 5;
}
