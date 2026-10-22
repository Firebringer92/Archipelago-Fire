// Replaces the vanilla dialog node script k_psta_mlkend (sta_m45ad only: the line that ends the Malak confrontation). Vanilla body, kept as is:
// STA_MALAK_DEAD is set; when the final choice (G_FinalChoice) is 1 and K_SWG_CARTH is not 16, the ending cutscene module STUNT_54a starts at once;
// otherwise the player is held for 0.7 s and Malak starts the walk-away conversation (sta_walkaway) 0.5 s later, which leads on to the landing area.
// The only addition is the goal report: in the first case the module changes inside this call, before the periodic poll or the fight-room watcher
// can see the flag, so the client is told here, right after the flag is set. A full replacement (no original kept) because the vanilla script starts
// a conversation, and a conversation started from a script reached through ExecuteScript does not start.
#include "kse"

void main()
{
    SetGlobalBoolean("STA_MALAK_DEAD", TRUE);
    KSE_Diag(84, "AP|CHECK|GOAL|MALAK_DEAD");
    if (GetGlobalNumber("G_FinalChoice") == 1 && GetGlobalNumber("K_SWG_CARTH") != 16)
    {
        StartNewModule("STUNT_54a", "", "51");
    }
    else
    {
        NoClicksFor(0.7);
        DelayCommand(0.5, ActionStartConversation(GetFirstPC(), "sta_walkaway", FALSE, CONVERSATION_TYPE_CINEMATIC, TRUE));
    }
}
