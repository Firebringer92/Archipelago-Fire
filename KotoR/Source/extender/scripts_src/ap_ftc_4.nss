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

int StartingConditional()
{
    return !KSE_GetFeatAcquired(4, OBJECT_SELF);
}
