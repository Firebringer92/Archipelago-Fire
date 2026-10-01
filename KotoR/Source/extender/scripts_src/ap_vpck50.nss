#include "kse"

int StartingConditional()
{
    return !GetHasSpell(50, GetPCSpeaker());
}
