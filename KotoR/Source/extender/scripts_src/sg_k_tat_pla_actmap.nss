// Story gate T3 (Tatooine): the star map. Replaces k_tat_pla_actmap, the OnUsed script of the star-map placeable
// K_TAT_STAR_MAP in the krayt lair (tat_m18ac only). Vanilla body: the player starts the hologram conversation with the object
// tagged tat18_starspeak. That conversation's first node writes the journal entry tat17_starmap 90 by itself (the Quest field of
// node E0, independent of its script k_ptat_starcut), so the gate has to sit here, before the conversation starts. The start is
// written out here instead of running the original through ExecuteScript, because a conversation started from a script reached
// through ExecuteScript does not start.
//
// With three Tatooine progression items the conversation starts as in vanilla. Otherwise a message is shown and nothing happens; the
// placeable stays usable.
#include "ap_gate"

void main()
{
    if (!ApGateOpen("tat", 3))
    {
        if (GetIsPC(GetLastUsedBy()))
        {
            ApGateMsg("Tatooine", 3);
            SetCustomToken(901, ApGateText("Tatooine", 3));
            AssignCommand(GetFirstPC(), ActionStartConversation(GetFirstPC(), "ap_gate_msg", FALSE, CONVERSATION_TYPE_CINEMATIC, TRUE));
        }
        return;
    }
    AssignCommand(GetFirstPC(), ActionStartConversation(GetObjectByTag("tat18_starspeak")));
}
