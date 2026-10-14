// Upper City North elevator door (tar02_lowdoor, OnFailToOpen). Vanilla opens it when the Sith armor is WORN by any party
// member or the guard has already seen papers (global TAR_PAPERSSHOWN). A droid PC cannot wear the armor at all (it is
// human-only), so when the PC is a droid and merely CARRIES it, this wrapper sets the same papers flag the door script reads and
// unlocks the door, then hands off to the untouched original (preserved as apo_k_ptar_alertsith_orig by
// scripts/generate_droid_assets.py). The unlock matters: the original only opens the door, and the vanilla route unlocks it
// separately (the guard dialog's k_ptar_lowopen), so setting the flag alone left the door locked while the guard said the papers
// had been shown. Everyone else runs the vanilla script unchanged. Only this one script is wrapped: the other armor checks in Taris
// are "you are in uniform, so you are not welcome here" checks, which must stay worn-only.
void main()
{
    object oPC = GetFirstPC();
    if (GetRacialType(oPC) == 5 && GetIsObjectValid(GetItemPossessedBy(oPC, "ptar_sitharmor")))
    {
        SetGlobalBoolean("TAR_PAPERSSHOWN", TRUE);
        SetLocked(OBJECT_SELF, FALSE);
    }
    ExecuteScript("apo_k_ptar_alertsith_orig", OBJECT_SELF);
}
