#include "kse"

// See CLASS_AUTO_GRANTED_FEATS's own comment (generate_ap_vendor.py) --
// these are the per-class ONE-TIME level-1 auto-grants that never come
// back on an ordinary relevel, so Character Reset must never strip them.
int IsFeatProtected(int nClass, int nFeat)
{
    if (nClass == CLASS_TYPE_SOLDIER) { return (nFeat == 4 || nFeat == 5 || nFeat == 6 || nFeat == 28 || nFeat == 29 || nFeat == 39 || nFeat == 40 || nFeat == 42 || nFeat == 44); }
    if (nClass == CLASS_TYPE_SCOUT) { return (nFeat == 5 || nFeat == 6 || nFeat == 11 || nFeat == 14 || nFeat == 30 || nFeat == 39 || nFeat == 40 || nFeat == 44); }
    if (nClass == CLASS_TYPE_SCOUNDREL) { return (nFeat == 5 || nFeat == 8 || nFeat == 31 || nFeat == 39 || nFeat == 40 || nFeat == 44 || nFeat == 60 || nFeat == 104); }
    if (nClass == CLASS_TYPE_JEDIGUARDIAN) { return (nFeat == 39 || nFeat == 43 || nFeat == 44 || nFeat == 55 || nFeat == 101 || nFeat == 107 || nFeat == 116); }
    if (nClass == CLASS_TYPE_JEDICONSULAR) { return (nFeat == 39 || nFeat == 43 || nFeat == 44 || nFeat == 55 || nFeat == 88 || nFeat == 107 || nFeat == 116); }
    if (nClass == CLASS_TYPE_JEDISENTINEL) { return (nFeat == 39 || nFeat == 43 || nFeat == 44 || nFeat == 55 || nFeat == 98 || nFeat == 107 || nFeat == 116); }
    return FALSE;
}

void main()
{
    object oPC = GetPCSpeaker();
    int nAfter = KSE_SetCredits(oPC, GetGold(oPC) - 6000);

    int nClass0 = GetClassByPosition(0, oPC);
    int nClass1 = GetClassByPosition(1, oPC);

    KSE_SetCreatureField(oPC, KSE_FIELD_CLASS0_LEVEL(), 1);
    if (nClass1 != CLASS_TYPE_INVALID)
    {
        KSE_SetCreatureField(oPC, KSE_FIELD_CLASS1_LEVEL(), 1);
    }

    int i;
    for (i = 0; i < 125; i++)
    {
        if (GetHasFeat(i, oPC) && !IsFeatProtected(nClass0, i) && !IsFeatProtected(nClass1, i))
        {
            KSE_RemoveFeatArrayA(i, oPC);
        }
    }
    for (i = 0; i < 144; i++)
    {
        if (GetHasSpell(i, oPC)) { KSE_SetCreatureField(oPC, KSE_FIELD_REMOVE_FORCE_POWER(), i); }
    }

    KSE_SetCreatureField(oPC, KSE_FIELD_SET_STR_BASE(), 10);
    KSE_SetCreatureField(oPC, KSE_FIELD_SET_DEX_BASE(), 10);
    KSE_SetCreatureField(oPC, KSE_FIELD_SET_CON_BASE(), 10);
    KSE_SetCreatureField(oPC, KSE_FIELD_SET_INT_BASE(), 10);
    KSE_SetCreatureField(oPC, KSE_FIELD_SET_WIS_BASE(), 10);
    KSE_SetCreatureField(oPC, KSE_FIELD_SET_CHA_BASE(), 10);

    KSE_AdjustCreatureSkills(oPC, SKILL_COMPUTER_USE, -GetSkillRank(SKILL_COMPUTER_USE, oPC));
    KSE_AdjustCreatureSkills(oPC, SKILL_DEMOLITIONS, -GetSkillRank(SKILL_DEMOLITIONS, oPC));
    KSE_AdjustCreatureSkills(oPC, SKILL_STEALTH, -GetSkillRank(SKILL_STEALTH, oPC));
    KSE_AdjustCreatureSkills(oPC, SKILL_AWARENESS, -GetSkillRank(SKILL_AWARENESS, oPC));
    KSE_AdjustCreatureSkills(oPC, SKILL_PERSUADE, -GetSkillRank(SKILL_PERSUADE, oPC));
    KSE_AdjustCreatureSkills(oPC, SKILL_REPAIR, -GetSkillRank(SKILL_REPAIR, oPC));
    KSE_AdjustCreatureSkills(oPC, SKILL_SECURITY, -GetSkillRank(SKILL_SECURITY, oPC));
    KSE_AdjustCreatureSkills(oPC, SKILL_TREAT_INJURY, -GetSkillRank(SKILL_TREAT_INJURY, oPC));

    // Also refunds the Train Ability/Train Skill purchase-count caps --
    // Reset already wipes the abilities/skills those purchases raised, so
    // leaving the old counts in place would leave the player permanently
    // short of their full 5 uses of each with nothing to show for the
    // ones already spent.
    SetLocalNumber(oPC, 61, 0);
    SetLocalNumber(oPC, 60, 0);

    int nCount = GetLocalNumber(oPC, 62) + 1;
    SetLocalNumber(oPC, 62, nCount);
    KSE_Diag(200, "AP|APPLIED|vendor_character_reset|creditsAfter=" + IntToString(nAfter) + "|count=" + IntToString(nCount));
}
