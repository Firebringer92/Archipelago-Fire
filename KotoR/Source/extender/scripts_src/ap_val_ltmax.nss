#include "kse"

int StartingConditional()
{
    return GetGoodEvilValue(GetPCSpeaker()) >= 90;
}
