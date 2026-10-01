#include "kse"

int StartingConditional()
{
    return !GetHasSpell(47, GetPCSpeaker());
}
