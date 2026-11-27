#include "kse"

int StartingConditional()
{
    return StringToInt(KSE_GetData("vslot4")) > 0;
}
