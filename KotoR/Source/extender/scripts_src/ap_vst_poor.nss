#include "kse"

int StartingConditional()
{
    return KSE_GetData("vend_state") == "poor";
}
