#include "kse"

int StartingConditional()
{
    return StringToInt(KSE_GetData("vslot14")) > 0;
}
