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
    object oPC = GetPCSpeaker();
    string sKey = KeyOf(OBJECT_SELF);
    if (sKey == "") return FALSE;
    if (GetIsInCombat(oPC)) return FALSE;
    if (GetStringLeft(GetStringLowerCase(GetModuleFileName()), 4) == "ebo_") return FALSE;
    return GetIsObjectValid(GetItemPossessedBy(oPC, "ap_ft_" + sKey));
}
