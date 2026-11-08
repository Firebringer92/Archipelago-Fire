// Replacement for the Taris Sith Base entrance's OnEnter script (tar_m02ab, trigger tag tar02_openbase).
//
// The only door into the Sith Base (tar02_sithdoor, linking to tar_m09aa) is not lockable: it has no Security-skill option in the UI.
// The vanilla script is the only thing that ever opens it, and it does so only when the PC-controlled character entering the trigger is
// T3-M4 (it looks the tag up against bastila=0, cand=1, carth=2, hk47=3, jolee=4, juhani=5, mission=6, t3m4=7, zaalbar=8). No other
// script or skill check references this door. That is a hard stop whenever the player cannot control T3-M4: companion_mode=ap_gated
// before his item arrives, companion_mode=none, or simply a T3-M4 who is in the party but not being controlled.
//
// This script unlocks the door for any character once the quest has reached the stage that sends the player here, and does not run the
// vanilla script. What the vanilla script adds for T3-M4 is cosmetic only: his dialog (tar02_base_dlg) plays a welding sound, opens the
// door and fades in, with no journal or global changes. Depends on the journal tag tar_escape: stage 20 is where Canderous assigns the
// objective of breaking into the base. ActionUnlockObject is idempotent, so repeat entries and party members following through are harmless.
#include "kse"

void main()
{
    if (GetJournalEntry("tar_escape") >= 20)
    {
        object oDoor = GetObjectByTag("tar02_sithdoor");
        if (GetIsObjectValid(oDoor))
        {
            AssignCommand(oDoor, ActionUnlockObject(oDoor));
            KSE_Diag(162, "AP|SAFEGUARD|tar_sithbase_door_unlock");
        }
    }
}
