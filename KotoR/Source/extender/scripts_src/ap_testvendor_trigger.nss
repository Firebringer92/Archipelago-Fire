// Throwaway test trigger -- run this directly from KOTOR's built-in
// debug console (`runscript ap_testvendor_trigger`, cheats must be
// enabled) to start the test vendor dialogue without needing any new
// arm/extender wiring. Not part of the real feature, safe to delete
// once the dialogue-authoring pattern is confirmed working live.
void main()
{
    object oPC = GetFirstPC();
    AssignCommand(oPC, ActionStartConversation(oPC, "ap_testvendor_dlg", TRUE));
}
