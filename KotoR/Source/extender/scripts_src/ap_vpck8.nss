#include "kse"

int StartingConditional()
{
    return !GetHasSpell(8, GetPCSpeaker());
}
