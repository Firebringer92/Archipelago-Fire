// Area randomizer only (scripts/patch_story_gates.py): the Upper City North elevator door (tar02_lowdoor, OnFailToOpen).
// Vanilla lets the player through when the Sith armor is worn or the guard has already seen papers (global TAR_PAPERSSHOWN).
// With the entrances shuffled that door can sit between the player and the way on before the armor is reachable, so the
// papers flag is set for everyone, the door is unlocked (the original only opens it) and the untouched original (preserved as apo_sg_alertsith) then opens the door. The Sith
// base entrance keeps its vanilla armor and papers check. This also covers the droid PC, so the droid-only wrapper
// (k_ptar_alertsith_droid) is not deployed alongside it.
void main()
{
    SetGlobalBoolean("TAR_PAPERSSHOWN", TRUE);
    SetLocked(OBJECT_SELF, FALSE);
    ExecuteScript("apo_sg_alertsith", OBJECT_SELF);
}
