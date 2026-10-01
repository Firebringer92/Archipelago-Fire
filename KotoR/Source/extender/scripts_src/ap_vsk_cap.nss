#include "kse"

int StartingConditional()
{
    return GetLocalNumber(GetPCSpeaker(), 60) < 5;
}
