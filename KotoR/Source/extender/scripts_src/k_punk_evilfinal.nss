// Unknown World (unk44_evilbast / unk44_evilbast2): the branch where the player goes along with Bastila. Vanilla adds dark-side
// points by alignment band (5 / 5 / 10 / 25 / 40). This moves the player to exactly the full dark side (0) from wherever they
// are. Installed over the vanilla script by the player bundle.
void main()
{
    object oPC = GetFirstPC();
    int nGap = GetGoodEvilValue(oPC);
    if (nGap > 0) AdjustAlignment(oPC, ALIGNMENT_DARK_SIDE, nGap);
}
