#include "kse"

int StartingConditional()
{
    return StringToInt(KSE_GetData("vslot2")) > 0;
}
