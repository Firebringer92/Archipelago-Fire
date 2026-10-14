// Droid PC (starting_class=droid): Persuade cannot be trained (skills.2da droidcanuse = 0), so a droid PC rolls on its Charisma modifier
// instead (k_inc_droidpers.nss: same bracket table as the vanilla AutoDC). Everyone else gets the vanilla roll unchanged. Installed over
// the vanilla k_con_pershigh by scripts/generate_droid_assets.py for droid-PC seeds only.
#include "k_inc_droidpers"

int StartingConditional()
{
    return PersuadeCheck(2, GetPCSpeaker());
}
