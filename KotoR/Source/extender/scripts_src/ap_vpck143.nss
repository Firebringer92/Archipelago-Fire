#include "kse"

int StartingConditional()
{
    object oPC = GetPCSpeaker();
    return !GetHasSpell(143, oPC) && GetHasSpell(10, oPC) && GetHasSpell(28, oPC);
}
