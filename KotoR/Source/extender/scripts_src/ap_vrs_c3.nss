#include "kse"

int StartingConditional()
{
    return StringToInt(KSE_GetData("vslot3")) > 0;
}
