// Story gate F1 (Star Forge): the confrontation with Malak. Replaces the vanilla OnEnter script k_psta_init_mala of the
// trigger k45_init_malak (sta_m45ad only). It is a full reimplementation, not a wrapper, because the vanilla script ends
// by starting a conversation, and ActionStartConversation silently fails to queue when reached through ExecuteScript.
// Vanilla body, kept as is: when the party leader enters and the trigger's plot flag 0 is not set, flag Malak as talked
// to, set the trigger's plot flag 0 (the once-only latch) and have Malak start k_sta_darthmalak with the leader. The
// gate adds one check ahead of all of that: with fewer than three Star Forge progression items nothing is touched, so the latch
// stays clear and the scene starts the next time the leader walks into the trigger once the progression items have arrived.
// k_psta_malakfght and k_psta_mlkend are deliberately not gated; they run inside the conversation.
#include "k_inc_utility"
#include "ap_gate"

void main()
{
    object oLeader = GetPartyMemberByIndex(0);
    if (oLeader == GetEnteringObject() && UT_GetPlotBooleanFlag(OBJECT_SELF, SW_PLOT_BOOLEAN_01) == FALSE)
    {
        if (!ApGateOpen("fin", 3))
        {
            ApGateMsg("Star Forge", 3);
            SetCustomToken(901, ApGateText("Star Forge", 3));
            AssignCommand(GetFirstPC(), ActionStartConversation(GetFirstPC(), "ap_gate_msg", FALSE, CONVERSATION_TYPE_CINEMATIC, TRUE));
            return;
        }
        object oMalak = GetObjectByTag("sta_45darthMalak");
        UT_SetTalkedToBooleanFlag(oMalak);
        UT_SetPlotBooleanFlag(OBJECT_SELF, SW_PLOT_BOOLEAN_01, TRUE);
        AssignCommand(oMalak, ActionStartConversation(oLeader, "k_sta_darthmalak", FALSE, CONVERSATION_TYPE_CINEMATIC, TRUE));
    }
}
