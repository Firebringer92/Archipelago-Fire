#include "kse"

int StartingConditional()
{
    return StringToInt(KSE_GetData("vslot13")) > 0;
}
