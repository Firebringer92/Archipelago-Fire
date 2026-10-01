#include "kse"

int StartingConditional()
{
    object oPC = GetPCSpeaker();
    return !GetHasFeat(101, oPC) && (GetLevelByClass(CLASS_TYPE_JEDIGUARDIAN, oPC) > 0 || GetLevelByClass(CLASS_TYPE_JEDICONSULAR, oPC) > 0 || GetLevelByClass(CLASS_TYPE_JEDISENTINEL, oPC) > 0);
}
