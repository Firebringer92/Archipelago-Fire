#include "kse"

int StartingConditional()
{
    return !GetHasSpell(22, GetPCSpeaker());
}
