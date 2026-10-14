// Full replacement for the Ebon Hawk exit-ramp trigger script (UTT ebn12_ebonexit, OnEnter). The script exists in two different
// versions, one in ebo_m12aa and one in ebo_m41aa (the Hawk after the Leviathan), and an Override file replaces both, so this reproduces
// each by module name.
//
// ebo_m12aa (vanilla): when the player walks onto the ramp and K_CURRENT_PLANET is above 0, show the party selection screen whose exit
// script k_pebn_exithawk starts the landing module for that planet (forcing Bastila into the party at the Star Forge after the light
// side finale). With K_CURRENT_PLANET at 0 nothing happened, so a player who reached the Hawk without the value set (it is set by the
// Endar Spire to 5 and by the Taris Hideout to 10) had no way off. Any value below 10 is now raised to 10, Taris Upper City North
// (tar_m02aa), the fixed start of the area randomizer's door graph.
//
// ebo_m41aa (vanilla): shows the party selection screen unconditionally.
void main()
{
    if (GetStringLowerCase(GetModuleFileName()) == "ebo_m41aa")
    {
        ShowPartySelectionGUI("k_pebn_exithawk", -1, -1);
        return;
    }
    if (GetEnteringObject() != GetFirstPC()) return;
    int nPlanet = GetGlobalNumber("K_CURRENT_PLANET");
    if (nPlanet < 10)
    {
        nPlanet = 10;
        SetGlobalNumber("K_CURRENT_PLANET", 10);
    }
    if (nPlanet == 50 && GetGlobalNumber("G_FinalChoice") == 1) ShowPartySelectionGUI("k_pebn_exithawk", 0, -1);
    else ShowPartySelectionGUI("k_pebn_exithawk", -1, -1);
}
