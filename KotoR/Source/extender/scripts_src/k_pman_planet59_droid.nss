// Manaan planet vote persuasion step (DC level 0). For a droid PC (starting_class=droid) Persuade cannot be trained, so the roll
// uses its Charisma modifier (k_inc_droidpers.nss); everyone else gets the vanilla roll unchanged. Installed over the vanilla k_pman_planet59 by
// scripts/generate_droid_assets.py for droid-PC seeds only.
#include "k_inc_droidpers"

void main()
{
    SetGlobalBoolean("MAN_PERS_DONE", FALSE);
    if (PersuadeCheck(0, GetPCSpeaker()))
    {
        SetGlobalBoolean("MAN_PERS_DONE", TRUE);
        SetGlobalNumber("MAN_THRESHOLD", GetGlobalNumber("MAN_THRESHOLD") + 2);
    }
}
