// TEST-ONLY scaffolding: forces Mission into the active party so Zaalbar's
// suppression wrapper (which requires IsNPCPartyMember(NPC_MISSION) per
// missdoor_dlg) can be tested in isolation, without needing Mission's own
// (not-yet-built) real AP grant script or her suppressed natural
// recruitment. Same shape as the proven ap_apply_companion_canderous.nss.
// NOT part of the shipping mod.
#include "kse"

void DoApply()
{
    int nNPC = NPC_MISSION;
    string sTemplate = "p_mission";

    AddAvailableNPCByTemplate(nNPC, sTemplate);

    object oPC = GetFirstPC();
    object oNPC = CreateObject(OBJECT_TYPE_CREATURE, sTemplate, GetLocation(oPC));
    int nAdded = AddPartyMember(nNPC, oNPC);

    KSE_Diag(37, "AP|TESTPREP|force_mission_party|added=" + IntToString(nAdded));
}

void main()
{
    DelayCommand(3.0, DoApply());
}
