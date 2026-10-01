#include "kse"

int StartingConditional()
{
    return !GetHasSpell(49, GetPCSpeaker());
}
