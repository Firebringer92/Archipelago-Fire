// Wrapper for the Ebon Hawk's galaxy map console (placeable infoterm001, tag GalaxyMap, ebo_m12aa; the vanilla core script is
// preserved as apo_galaxy_orig). The vanilla script makes planets available and selectable from K_KOTOR_MASTER and offers the Unknown World
// only when it is exactly 30, which k_pla_actmap writes when K_STAR_MAP reaches 50. The Leviathan finale writes 20 over it afterwards, so a
// player whose fifth star map came before the Leviathan finished (shuffled areas) never saw the Unknown World again. When all five star
// maps are counted and the Leviathan is done, K_KOTOR_MASTER is raised to 30 here, which is what the star map script would have done, and
// the vanilla script then runs unchanged. In the vanilla order K_KOTOR_MASTER is already 30 and nothing differs.
void main()
{
    if (GetGlobalNumber("K_KOTOR_MASTER") == 20 && GetGlobalNumber("K_STAR_MAP") >= 50 && GetGlobalNumber("K_CAPTURED_LEV") == 10)
    {
        SetGlobalNumber("K_KOTOR_MASTER", 30);
    }
    ExecuteScript("apo_galaxy_orig", OBJECT_SELF);
}
