#include "kse"

int StartingConditional()
{
    return !GetHasSpell(45, GetPCSpeaker());
}
