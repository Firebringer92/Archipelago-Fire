// Throwaway test script -- validates the Archipelago Vendor dialogue
// architecture (DLGLink/script1 branching), NOT part of the real
// feature. Safe to delete once the dialogue-authoring pattern is
// confirmed working live.
#include "kse"

void main()
{
    object oPC = GetFirstPC();
    int nBefore = GetSkillRank(SKILL_AWARENESS, oPC);
    KSE_AdjustCreatureSkills(oPC, SKILL_AWARENESS, 2);
    int nAfter = GetSkillRank(SKILL_AWARENESS, oPC);
    KSE_Diag(901, "AP|TEST|VENDOR_DIALOGUE|awareness|before=" + IntToString(nBefore)
                  + "|after=" + IntToString(nAfter));
}
