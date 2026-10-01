#include "kse"

int StartingConditional()
{
    return !GetHasSpell(43, GetPCSpeaker());
}
