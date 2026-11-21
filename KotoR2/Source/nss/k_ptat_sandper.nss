#include "k2se"
#include "k2ap_gift"
#include "k2ap_stand"
// Impact script of spell row 85 (PLOT_TAT_SAND_PERSON_DISGUISE), an unused K1 leftover in TSL. The Crafting Console casts that
// spell, so this script runs when the player uses it and opens the crafting menu. The item is never used up; as with the roster
// console, a moment later the script gives a new one if none is left. The AP Companion Gift (tag ap_gift) casts the same spell and opens its own menu
// (nss/k2ap_gift.nss); it is a stack that the menu's answer uses up one by one. The Party Console (tag ap_partycon, nss/k2ap_pcopen.nss) opens a menu: change the active party (the
// party selection screen), choose the standing companions (nss/k2ap_stand.nss), send them away, or no change; like the crafting item it is given back if the game used it up.
void GiveCraftItemBack()
{
    object oPC = GetFirstPC();
    if (!GetIsObjectValid(GetItemPossessedBy(oPC, "k2se_craft")))
        CreateItemOnObject("k2se_craft", oPC, 1, 1);
}

void GivePartyConBack()
{
    object oPC = GetFirstPC();
    if (!GetIsObjectValid(GetItemPossessedBy(oPC, "ap_partycon")))
        CreateItemOnObject("ap_partycon", oPC, 1, 1);
}

void main()
{
    if (GetTag(GetSpellCastItem()) == "ap_partycon")
    {
        object oUser = GetFirstPC();
        if (K2SE_IsPresent()) K2SE_Diag("ITEM", "k_ptat_sandper ran for the party console");
        K2AP_StandMenu(oUser);                                  // the menu's header: who is in the party and who stands beside you
        AssignCommand(oUser, ActionStartConversation(oUser, "ap_partycon", FALSE, CONVERSATION_TYPE_CINEMATIC, TRUE));
        DelayCommand(1.5, GivePartyConBack());
        DelayCommand(5.0, GivePartyConBack());
        return;
    }
    if (GetTag(GetSpellCastItem()) == "ap_gift")
    {
        K2AP_GiftMenu(GetFirstPC());
        return;
    }
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
