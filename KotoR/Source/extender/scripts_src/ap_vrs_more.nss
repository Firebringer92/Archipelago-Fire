#include "kse"

int StartingConditional()
{
    return StringToInt(KSE_GetData("vrs_total")) > StringToInt(KSE_GetData("vrs_off")) + 16;
}
