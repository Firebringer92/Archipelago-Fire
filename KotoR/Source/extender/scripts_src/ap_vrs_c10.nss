#include "kse"

int StartingConditional()
{
    return StringToInt(KSE_GetData("vslot10")) > 0;
}
