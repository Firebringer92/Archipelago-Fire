// Unknown World (unk44_evilbast / unk44_evilbast2): the branch where the player stands against Bastila. Vanilla adds light-side
// points by alignment band (40 / 25 / 10 / 5 / 5), which only reaches the extreme from the far side. This moves the player to
// exactly the full light side (100) from wherever they are. Installed over the vanilla script by the player bundle.
void main()
{
    object oPC = GetFirstPC();
    int nGap = 100 - GetGoodEvilValue(oPC);
    if (nGap > 0) AdjustAlignment(oPC, ALIGNMENT_LIGHT_SIDE, nGap);
}
