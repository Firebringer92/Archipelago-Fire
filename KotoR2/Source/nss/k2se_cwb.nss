#include "k2se"
// Crafting menu reply: the workbench forced into item creation (the screen with the Breakdown button). crafttable=N in config.txt
// picks a project recipe table for testing (1 k2se_icreate, 2 k2se_gear); the shipped build fixes the table name here.
void main()
{
    string sTable = "";
    if (K2SE_ConfigInt("ap_crafting_mode", 0) > 0) sTable = "k2se_recipes";      // the project table the client wrote for this seed (client/k2_crafting.py)
    int n = K2SE_ConfigInt("crafttable", 0);          // testing: crafttable=1 or 2 picks a research table instead
    if (n == 1) sTable = "k2se_icreate";
    if (n == 2) sTable = "k2se_gear";
    ShowUpgradeScreen(OBJECT_INVALID, GetFirstPC(), FALSE, TRUE, sTable);
}
