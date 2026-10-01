#include "kse"

int StartingConditional()
{
    return !GetHasSpell(136, GetPCSpeaker());
}
