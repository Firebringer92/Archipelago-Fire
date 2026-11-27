#include "kse"

int StartingConditional()
{
    return StringToInt(KSE_GetData("vslot5")) > 0;
}
