#include "kse"

// Impact script of spells.2da row 132: runs when the Party Console item is used.
void main()
{
    KSE_Diag(199, "AP|PARTYCON|ran");
    object oPC = GetFirstPC();
    object oItem = GetSpellCastItem();
    if (!GetIsObjectValid(oItem)) oItem = GetItemActivated();
    KSE_Diag(199, "AP|PARTYCON|used|item=" + GetTag(oItem) + "|valid=" + IntToString(GetIsObjectValid(oItem)));
    string sMod = GetStringLowerCase(GetModuleFileName());
    if (sMod == "tar_m02ae" || sMod == "korr_m39aa" || sMod == "sta_m45ad" || GetStringLeft(sMod, 4) == "ebo_")
    {
        KSE_Diag(199, "AP|PARTYCON|refused|mod=" + sMod);
        SetCustomToken(901, "The Party Console cannot be used here.");
        AssignCommand(oPC, ActionStartConversation(oPC, "ap_gate_msg", FALSE, CONVERSATION_TYPE_CINEMATIC, TRUE));
        return;
    }
    AssignCommand(oPC, ActionStartConversation(oPC, "ap_party_con", FALSE, CONVERSATION_TYPE_CINEMATIC, TRUE));
}
