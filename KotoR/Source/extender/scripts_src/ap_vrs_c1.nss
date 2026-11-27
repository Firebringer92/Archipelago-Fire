#include "kse"

int StartingConditional()
{
    return StringToInt(KSE_GetData("vslot1")) > 0;
}
