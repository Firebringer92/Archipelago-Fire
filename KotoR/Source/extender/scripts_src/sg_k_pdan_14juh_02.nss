// Story gate D2 (Dantooine): the Juhani confrontation, combat trigger. Wrapper for k_pdan_14juh_02 (OnEnter of the
// combat trigger dan14_juhan_cbt, danm14ac only; the vanilla script is preserved as apo_sg_juh02). Runs unchanged with
// two Dantooine progression items; otherwise the fight does not start.
#include "ap_gate"

void main()
{
    if (!ApGateOpen("dan", 2))
    {
        if (GetIsPC(GetEnteringObject()))
        {
            ApGateMsg("Dantooine", 2);
            SetCustomToken(901, ApGateText("Dantooine", 2));
            AssignCommand(GetFirstPC(), ActionStartConversation(GetFirstPC(), "ap_gate_msg", FALSE, CONVERSATION_TYPE_CINEMATIC, TRUE));
        }
        return;
    }
    ExecuteScript("apo_sg_juh02", OBJECT_SELF);
}
