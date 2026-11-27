#include "kse"

int StartingConditional()
{
    return StringToInt(KSE_GetData("vslot8")) > 0;
}
