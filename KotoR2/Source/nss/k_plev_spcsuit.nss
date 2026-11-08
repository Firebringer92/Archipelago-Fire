#include "k2se"
#include "k2se_roster"
// Impact script of spell row 109 (PLOT_LEV_DAMAGE_SPACE_SUIT), an unused K1 leftover in TSL. The roster item casts that
// spell, so this script runs when the player uses it and opens the roster menu. The game consumes a used item, so a
// moment later the script gives the player a new one if none is left.
void GiveRosterItemBack()
{
    object oPC = GetFirstPC();
    if (!GetIsObjectValid(GetItemPossessedBy(oPC, "k2se_roster")))
        CreateItemOnObject("k2se_roster", oPC, 1, 1);
}

void main()
{
    if (GetTag(GetSpellCastItem()) == "k2se_roster")
    {
        if (K2SE_IsPresent()) K2SE_Diag("ITEM", "k_plev_spcsuit ran for the roster item");
        RosterPrompt(GetFirstPC());
        DelayCommand(1.5, GiveRosterItemBack());
        DelayCommand(5.0, GiveRosterItemBack());
    }
}
