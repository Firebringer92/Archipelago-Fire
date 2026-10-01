#include "kse"

int StartingConditional()
{
    return !GetHasSpell(139, GetPCSpeaker());
}
