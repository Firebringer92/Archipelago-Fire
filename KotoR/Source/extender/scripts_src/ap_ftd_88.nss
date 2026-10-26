#include "kse"

string KeyOf(object oNPC)
{
    string sTag = GetTag(oNPC);
    if (sTag == "Bastila") return "bastila";
    if (sTag == "Cand") return "canderous";
    if (sTag == "Carth") return "carth";
    if (sTag == "Jolee") return "jolee";
    if (sTag == "Juhani") return "juhani";
    if (sTag == "Mission") return "mission";
    if (sTag == "Zaalbar") return "zaalbar";
    return "";
}

int TrainedCount(object oPC, string sKey)
{
    object oReceipt = GetItemPossessedBy(oPC, "ap_fn_" + sKey);
    if (!GetIsObjectValid(oReceipt)) return 0;
    return GetItemStackSize(oReceipt);
}

int PriceFor(int nTrained)
{
    return 1000 + 2000 * nTrained;
}

int HasForceLevels(object oNPC)
{
    return GetLevelByClass(CLASS_TYPE_JEDIGUARDIAN, oNPC) + GetLevelByClass(CLASS_TYPE_JEDICONSULAR, oNPC) + GetLevelByClass(CLASS_TYPE_JEDISENTINEL, oNPC) > 0;
}

void Say(string sText)
{
    SetCustomToken(9022, sText);
}

void main()
{
    object oPC = GetPCSpeaker();
    string sKey = KeyOf(OBJECT_SELF);
    string sName = GetName(OBJECT_SELF);
    if (sKey == "") { Say("Something went wrong: this is not one of the crew."); return; }
    if (KSE_GetFeatAcquired(88, OBJECT_SELF)) { Say(sName + " already knows Force Focus."); return; }
    int nTrained = TrainedCount(oPC, sKey);
    int nPrice = PriceFor(nTrained);
    if (GetGold(oPC) < nPrice) { Say("Training Force Focus costs " + IntToString(nPrice) + " credits, and you do not have enough."); return; }
    KSE_GrantFeatArrayA(88, OBJECT_SELF);
    if (!KSE_GetFeatAcquired(88, OBJECT_SELF))
    {
        Say(sName + " cannot take on Force Focus: there is no room left for another feat. You were not charged.");
        KSE_Diag(207, "AP|APPLIED|feat_training_refused|key=" + sKey + "|feat=88");
        return;
    }
    int nAfter = KSE_SetCredits(oPC, GetGold(oPC) - nPrice);
    CreateItemOnObject("ap_fn_" + sKey, oPC, 1);
    Say(sName + " has learned Force Focus. That cost " + IntToString(nPrice) + " credits.");
    KSE_Diag(208, "AP|APPLIED|feat_training|key=" + sKey + "|feat=88|price=" + IntToString(nPrice) + "|creditsAfter=" + IntToString(nAfter) + "|count=" + IntToString(nTrained + 1));
}
