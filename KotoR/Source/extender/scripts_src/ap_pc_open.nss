#include "kse"

// Action script of the dialog's "open" line. The screen is opened shortly after, once the dialog has closed.
void main()
{
    object oPC = GetFirstPC();
    KSE_Diag(199, "AP|PARTYCON|opening|party=" + IntToString(GetPartyMemberCount()));
    AssignCommand(oPC, DelayCommand(0.6, ShowPartySelectionGUI("ap_pc_done")));
}
