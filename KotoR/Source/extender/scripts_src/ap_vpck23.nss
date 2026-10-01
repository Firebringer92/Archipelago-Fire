#include "kse"

int StartingConditional()
{
    return !GetHasSpell(23, GetPCSpeaker());
}
