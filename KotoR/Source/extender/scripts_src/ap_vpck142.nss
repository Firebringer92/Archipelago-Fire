#include "kse"

int StartingConditional()
{
    object oPC = GetPCSpeaker();
    return !GetHasSpell(142, oPC) && GetHasSpell(40, oPC) && GetHasSpell(42, oPC);
}
