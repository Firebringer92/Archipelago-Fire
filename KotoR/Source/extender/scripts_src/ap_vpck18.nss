#include "kse"

int StartingConditional()
{
    return !GetHasSpell(18, GetPCSpeaker());
}
