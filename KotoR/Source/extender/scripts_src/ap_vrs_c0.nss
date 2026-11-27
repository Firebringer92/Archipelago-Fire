#include "kse"

int StartingConditional()
{
    return StringToInt(KSE_GetData("vslot0")) > 0;
}
