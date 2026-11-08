#include "k2se"
// Condition of the Crafting Console's reply: shown unless the seed has switched it off (the client writes ap_craft_bench=0 while its crafting type is still locked).
int StartingConditional()
{
    return K2SE_ConfigInt("ap_craft_bench", 1) == 1;
}
