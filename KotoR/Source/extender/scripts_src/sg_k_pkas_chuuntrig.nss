// Story gate K3 (Kashyyyk): throne-room trigger. Replaces k_pkas_chuuntrig, the OnEnter script of the trigger in kas_m23ad that
// has Chuundar start kas23_chuunda_01 with whoever walked in. Vanilla body: when the entering object is the player and either
// Chuundar has not been talked to yet (local boolean 10, the "talked to" flag) or Freyyr was helped or killed, Chuundar starts the
// conversation. It is written out here instead of running the original through ExecuteScript, because a conversation started
// from a script reached through ExecuteScript does not start.
//
// The conversation starters are what actually hold the confrontation (sg_k_pkas_freydead2, sg_k_pkas_freyyhelp,
// sg_k_pkas_freyydead). This script exists for the screen: the area's OnEnter fades the screen to black whenever Freyyr was
// helped or killed, expecting the first node of that conversation to fade it back in. With fewer than three Kashyyyk progression items that
// conversation cannot start, so this script shows the message and fades the screen back in itself instead of starting it. The
// first meeting with Chuundar (before Freyyr is helped or killed) is not affected.
#include "ap_gate"

void main()
{
    object oEnterer = GetEnteringObject();
    if (!GetIsPC(oEnterer)) return;
    object oChuundar = GetObjectByTag("kas23_chuunda_01");
    int bTalked = GetIsObjectValid(oChuundar) && GetLocalBoolean(oChuundar, 10) > 0;
    int bAfterFreyyr = FALSE;
    if (GetGlobalBoolean("kas_HelpedFreyyr") == TRUE) bAfterFreyyr = TRUE;
    if (GetGlobalBoolean("kas_FreyyrDead") == TRUE) bAfterFreyyr = TRUE;
    if (bTalked && !bAfterFreyyr) return;
    if (bAfterFreyyr && !ApGateOpen("kas", 3))
    {
        ApGateMsg("Kashyyyk", 3);
        SetGlobalFadeIn(0.0, 1.0);
        DelayCommand(1.5, SetGlobalFadeIn(0.0, 1.0));
        SetCustomToken(901, ApGateText("Kashyyyk", 3));
        AssignCommand(GetFirstPC(), ActionStartConversation(GetFirstPC(), "ap_gate_msg", FALSE, CONVERSATION_TYPE_CINEMATIC, TRUE));
        return;
    }
    AssignCommand(oChuundar, ActionStartConversation(oEnterer, "", FALSE, CONVERSATION_TYPE_CINEMATIC, TRUE));
}
