#include "kse"

int StartingConditional()
{
    return !GetHasSpell(133, GetPCSpeaker());
}
