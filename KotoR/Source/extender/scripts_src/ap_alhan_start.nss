// Exit script of the party selection screen that the Dantooine council wrap-up opens (the preserved vanilla k_pdan_addbast, apo_addbast_orig,
// has its exit-script name patched from k_pdan_alhan02 to this script). It does what k_pdan_alhan02 did: tells Ahlan Matale, the settler
// demanding justice, to come over and start his conversation, which is what begins the Sandral-Matale Feud quest.
//
// Why it is not the vanilla script: the council wrapper (ap_companion_gate.nss) takes back a temporary Bastila and Carth right after the original
// runs. With nobody left on the roster the game probably has no screen to show and runs the exit script at once, while Vandar's closing
// conversation is still open, and Ahlan's order to start a conversation is dropped. The signal is therefore sent two seconds later.
// Skipped once the quest has started (DAN_ROMANCE_PLOT is set to 1 by his first conversation).
void main()
{
    if (GetGlobalNumber("DAN_ROMANCE_PLOT") > 0) return;
    object oAhlan = GetObjectByTag("dan13_ahlan");
    if (!GetIsObjectValid(oAhlan)) return;
    DelayCommand(2.0, SignalEvent(oAhlan, EventUserDefined(30)));
}
