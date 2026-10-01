#include "kse"

int StartingConditional()
{
    object oPC = GetPCSpeaker();
    return GetClassByPosition(0, oPC) != CLASS_TYPE_JEDIGUARDIAN && GetClassByPosition(1, oPC) != CLASS_TYPE_JEDIGUARDIAN;
}
