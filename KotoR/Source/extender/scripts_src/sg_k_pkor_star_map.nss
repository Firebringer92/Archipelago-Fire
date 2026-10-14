// Story gate Ko3 (Korriban): the star map in Naga Sadow's tomb. Wrapper for the OnEnter script of the trigger
// k_kor_star_map (vanilla k_pkor_star_map, korr_m39aa only, preserved as apo_sg_korstar). The vanilla script does the
// whole activation in one pass: journal kor33_findstarmap 40, plot XP, the hologram conversation, the star pad and the
// K_STAR_MAP recompute.
//
// With three Korriban progression items the vanilla script runs through ExecuteScript. A conversation started from a script reached
// through ExecuteScript does not start, so the hologram conversation (the original's last visible step) is started here
// after the original has run, only on the pass that wrote the journal entry. Without the progression items nothing runs, including the
// one-shot latch the vanilla script sets, so the trigger fires again when the player walks back in with them.
#include "ap_gate"

void main()
{
    object oEnterer = GetEnteringObject();
    if (!ApGateOpen("kor", 3))
    {
        if (GetIsPC(oEnterer))
        {
            ApGateMsg("Korriban", 3);
            SetCustomToken(901, ApGateText("Korriban", 3));
            AssignCommand(GetFirstPC(), ActionStartConversation(GetFirstPC(), "ap_gate_msg", FALSE, CONVERSATION_TYPE_CINEMATIC, TRUE));
        }
        return;
    }
    int bFirstPass = GetIsPC(oEnterer) && GetJournalEntry("kor33_findstarmap") < 40;
    ExecuteScript("apo_sg_korstar", OBJECT_SELF);
    if (bFirstPass)
    {
        DelayCommand(0.5, AssignCommand(GetFirstPC(), ActionStartConversation(GetObjectByTag("kor_startalk"))));
    }
}
