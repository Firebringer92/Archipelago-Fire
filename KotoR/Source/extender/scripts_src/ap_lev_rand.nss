// Action script of the "Let fate decide" branch added to the capture-plan
// conversation ap_lev_carth (extender/raw_override_files/ap_lev_carth.dlg).
// Picks who escapes capture at random instead of asking the player to choose:
// it does what the choice's own reply script does (k_plev_escplot<N> is just
// SetGlobalNumber("Lev_Escape", N)) and the conversation carries on to the
// ship being dragged to the Leviathan as usual.
//   1 Mission  2 T3-M4  3 Jolee  4 Canderous  5 Juhani
// Mission, T3-M4 and Canderous are always eligible (the conversation offers
// them unconditionally); Jolee and Juhani use the same conditions as their
// menu entries (k_ptar_joleechk / k_con_juhanilive). HK-47 (6) is never
// picked: he can be replaced by another companion (new_companion option), and
// his plot is still available through the menu.
#include "kse"

string LevEscapeName(int nPick)
{
    if (nPick == 1) return "Mission";
    if (nPick == 2) return "T3-M4";
    if (nPick == 3) return "Jolee";
    if (nPick == 4) return "Canderous";
    return "Juhani";
}

void main()
{
    int bJolee = IsAvailableCreature(NPC_JOLEE);
    int bJuhani = (GetGlobalNumber("Dan_Juhani_Plot") != 2);

    int nRoll = Random(3 + bJolee + bJuhani);
    int nPick = 5;
    if (nRoll == 0) nPick = 1;
    else if (nRoll == 1) nPick = 2;
    else if (nRoll == 2) nPick = 4;
    else
    {
        nRoll -= 3;
        if (bJolee)
        {
            if (nRoll == 0) nPick = 3;
            nRoll--;
        }
    }

    SetGlobalNumber("Lev_Escape", nPick);
    KSE_Diag(177, "AP|SAFEGUARD|lev_capture_cast|random_escape=" + IntToString(nPick));
    FloatingTextStringOnCreature("Fate chose: " + LevEscapeName(nPick), GetFirstPC());
}
