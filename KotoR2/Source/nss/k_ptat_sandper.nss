#include "k2se"
// Impact script of spell row 85 (PLOT_TAT_SAND_PERSON_DISGUISE), an unused K1 leftover in TSL. The Crafting Console casts that
// spell, so this script runs when the player uses it and opens the crafting menu. The item is never used up; as with the roster
// console, a moment later the script gives a new one if none is left.
void GiveCraftItemBack()
{
    object oPC = GetFirstPC();
    if (!GetIsObjectValid(GetItemPossessedBy(oPC, "k2se_craft")))
        CreateItemOnObject("k2se_craft", oPC, 1, 1);
}

void main()
{
    if (GetTag(GetSpellCastItem()) == "k2se_craft")
    {
        object oPC = GetFirstPC();
        if (K2SE_IsPresent()) K2SE_Diag("ITEM", "k_ptat_sandper ran for the crafting item");
        SetCustomToken(9220, "Crafting. Which station do you want to use?");
        SetCustomToken(9221, "Workbench: create new items or break items down.");
        SetCustomToken(9222, "Workbench: upgrade an item.");
        SetCustomToken(9223, "Chemical lab: medpacs, stims, grenades and mines.");
        SetCustomToken(9224, "Close.");
        AssignCommand(oPC, ActionStartConversation(oPC, "k2se_craft", FALSE, CONVERSATION_TYPE_CINEMATIC, TRUE));
        DelayCommand(1.5, GiveCraftItemBack());
        DelayCommand(5.0, GiveCraftItemBack());
    }
}
