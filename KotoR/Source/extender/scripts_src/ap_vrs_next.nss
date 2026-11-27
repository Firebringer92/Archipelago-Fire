#include "kse"

void main()
{
    KSE_SetData("vrs_off", IntToString(StringToInt(KSE_GetData("vrs_off")) + 16));
}
