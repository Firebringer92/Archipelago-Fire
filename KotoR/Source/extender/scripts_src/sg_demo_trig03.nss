// Story gate M3 (Manaan): the star map in the Hrakert Rift. Replaces demo_trig03, the OnEnter script of the trigger
// demo_trig_sm in manm28ad. Vanilla body, once (a local boolean on the trigger, index 9, latches it): when a party
// member enters, give the star pad man_starpad, set MAN_STARMAP_FOUND, start the hologram conversation on
// man28_starmapobj, add man26_starmap 40, and add man_planet 60 (MAN_PLANET_PLOT is 4) or 65.
//
// This is a full replacement, not a wrapper, because the conversation start is queued from inside the script and a
// conversation queued by a script that was run through ExecuteScript does not start. The gate adds "holds three
// Manaan progression items" and is checked before the latch is set, so a player who walks in early can walk in again later.
#include "ap_gate"

void main()
{
    object oEnter = GetEnteringObject();
    if (!IsObjectPartyMember(oEnter)) return;
    if (!ApGateOpen("man", 3))
    {
        if (GetIsPC(oEnter))
        {
            ApGateMsg("Manaan", 3);
            SetCustomToken(901, ApGateText("Manaan", 3));
            AssignCommand(GetFirstPC(), ActionStartConversation(GetFirstPC(), "ap_gate_msg", FALSE, CONVERSATION_TYPE_CINEMATIC, TRUE));
        }
        return;
    }
    if (GetLocalBoolean(OBJECT_SELF, 9)) return;
    SetLocalBoolean(OBJECT_SELF, 9, TRUE);

    CreateItemOnObject("man_starpad", GetFirstPC(), 1);
    SetGlobalBoolean("MAN_STARMAP_FOUND", TRUE);
    AssignCommand(GetObjectByTag("man28_starmapobj"), ActionStartConversation(GetFirstPC()));
    AddJournalQuestEntry("man26_starmap", 40);
    if (GetGlobalNumber("MAN_PLANET_PLOT") == 4) AddJournalQuestEntry("man_planet", 60);
    else AddJournalQuestEntry("man_planet", 65);
}
