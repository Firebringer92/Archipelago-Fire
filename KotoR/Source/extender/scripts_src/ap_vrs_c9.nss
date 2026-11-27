#include "kse"

int StartingConditional()
{
    return StringToInt(KSE_GetData("vslot9")) > 0;
}
