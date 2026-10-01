#include "kse"

int StartingConditional()
{
    return GetLocalNumber(GetPCSpeaker(), 63) < 5;
}
