#include "kse"

int StartingConditional()
{
    return !GetHasSpell(42, GetPCSpeaker());
}
