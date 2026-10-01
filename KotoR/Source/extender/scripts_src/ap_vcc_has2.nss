#include "kse"

int StartingConditional()
{
    return GetClassByPosition(1, GetPCSpeaker()) != CLASS_TYPE_INVALID;
}
