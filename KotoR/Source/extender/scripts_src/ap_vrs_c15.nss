#include "kse"

int StartingConditional()
{
    return StringToInt(KSE_GetData("vslot15")) > 0;
}
