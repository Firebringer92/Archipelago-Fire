#include "kse"

int StartingConditional()
{
    return !GetHasSpell(16, GetPCSpeaker());
}
