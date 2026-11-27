#include "kse"

int StartingConditional()
{
    return StringToInt(KSE_GetData("vslot6")) > 0;
}
