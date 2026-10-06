// Throwaway test script -- validates the Archipelago Vendor dialogue
// architecture (DLGLink/script1 branching), NOT part of the real
// feature. Safe to delete once the dialogue-authoring pattern is
// confirmed working live.
#include "kse"

void main()
{
    object oPC = GetFirstPC();
    int nBefore = GetSkillRank(SKILL_COMPUTER_USE, oPC);
    KSE_AdjustCreatureSkills(oPC, SKILL_COMPUTER_USE, 2);
    int nAfter = GetSkillRank(SKILL_COMPUTER_USE, oPC);
    KSE_Diag(900, "AP|TEST|VENDOR_DIALOGUE|computer_use|before=" + IntToString(nBefore)
                  + "|after=" + IntToString(nAfter));
}
