// Story gate 1 (Taris): the Vulkar engine rooms. Replaces k_ptar_kandtalk, the OnOpen script of the two key doors into
// tar_m10ac's engine rooms. Both Kandon's double-cross offer and the prototype accelerator are behind these doors, so every
// route to the swoop race sponsor passes here.
//
// Vanilla body: unless Kandon's talker object (tar10_kandtalker) has already spoken (its local boolean 10, the "talked to" flag), hand the party
// leader to the player, block clicks for 1.2 seconds, and after one second have the talker start its conversation with the party leader (the talker is assigned a conversation with itself). This script
// reproduces that itself instead of running the original through ExecuteScript, because a conversation started from a script
// reached through ExecuteScript does not start.
//
// Without a Taris progression item the door is closed and locked again and nothing else happens, so none of the once-only state is used.
#include "ap_gate"

void main()
{
    if (!ApGateOpen("tar", 1))
    {
        ApGateMsg("Taris", 1);
        // Say it as a one-line dialog with the player speaking (no one else involved); started directly here, not through a helper.
        SetCustomToken(901, ApGateText("Taris", 1));
        AssignCommand(GetFirstPC(), ActionStartConversation(GetFirstPC(), "ap_gate_msg", FALSE, CONVERSATION_TYPE_CINEMATIC, TRUE));
        AssignCommand(OBJECT_SELF, ActionCloseDoor(OBJECT_SELF));
        DelayCommand(1.5, SetLocked(OBJECT_SELF, TRUE));
        return;
    }
    object oTalker = GetObjectByTag("tar10_kandtalker");
    if (GetIsObjectValid(oTalker) && GetLocalBoolean(oTalker, 10) > 0) return;
    SetPartyLeader(NPC_PLAYER);
    NoClicksFor(1.2);
    DelayCommand(1.0, AssignCommand(oTalker, ActionStartConversation(oTalker)));
}
