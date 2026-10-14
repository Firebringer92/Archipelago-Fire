// Story gate 1 backstop (Taris): using the prototype accelerator. Vanilla k_ptar_accelused
// (tar_m10ac only, preserved as apo_sg_accel) gives the accelerator item, sets Tar_SwoopEng
// and advances tar_bastsearch. The engine-room door gate already stops the player getting
// here, so this only matters if the room is reached some other way.
#include "ap_gate"

void main()
{
    if (!ApGateOpen("tar", 1))
    {
        ApGateMsg("Taris", 1);
        SetCustomToken(901, ApGateText("Taris", 1));
        AssignCommand(GetFirstPC(), ActionStartConversation(GetFirstPC(), "ap_gate_msg", FALSE, CONVERSATION_TYPE_CINEMATIC, TRUE));
        return;
    }
    ExecuteScript("apo_sg_accel", OBJECT_SELF);
}
