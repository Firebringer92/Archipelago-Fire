#include "kse"

int StartingConditional()
{
    return !GetHasSpell(46, GetPCSpeaker());
}
