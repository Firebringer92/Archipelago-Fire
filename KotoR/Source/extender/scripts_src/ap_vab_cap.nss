#include "kse"

int StartingConditional()
{
    return GetLocalNumber(GetPCSpeaker(), 61) < 5;
}
