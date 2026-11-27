#include "kse"

int StartingConditional()
{
    return StringToInt(KSE_GetData("vslot11")) > 0;
}
