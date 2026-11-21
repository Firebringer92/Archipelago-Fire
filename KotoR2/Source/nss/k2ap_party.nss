// k2ap_party.nss -- skill and ability boosts reach the whole active party (include file).
//
// Design rule for this port: every one-rank skill boost and one-point ability boost (the multiworld's Skill and Ability items, and the Archipelago Vendor's
// training) goes to the Exile and, in the same moment, to each companion who is in the party. The first game's port boosted the player only. Companions who are not
// in the party when the boost arrives do not get it; the gaps stay small because the party is who is playing. Traps stay with the Exile.
// The Exile's own write is the caller's; these helpers raise the Exile's value and the companions' value by the same step.

#include "k2ap_seed"

// One rank in one skill (0..7, the order of skills.2da). TRUE when the game took the write.
int K2AP_RaiseSkill(object oWho, int nSkill)
{
    int nRank = K2SE_GetSkillRankBase(oWho, nSkill);
    if (nRank < 0) return FALSE;
    return K2SE_SetSkillRank(oWho, nSkill, nRank + 1) == 1;
}

// One point in one ability (the ABILITY_ constants). TRUE when the game took the write.
int K2AP_RaiseAbility(object oWho, int nAbility)
{
    int nScore = K2SE_GetAbilityScoreBase(oWho, nAbility);
    if (nScore < 0) return FALSE;
    return K2SE_SetAbilityScoreBase(oWho, nAbility, nScore + 1) == 1;
}

// The same boost for each companion in the party (the three party slots; the Exile and an empty slot are skipped, so the body the player controls in a play-as scene
// is a companion and gets it). nKind 0 = skill, 1 = ability; nWhich is the skill or ability. Returns how many companions took it, reported as "PB|<kind>|<which>|<count>".
int K2AP_RaisePartyMembers(object oExile, int nKind, int nWhich)
{
    int nDone = 0;
    int nIndex;
    for (nIndex = 0; nIndex < 3; nIndex++)
    {
        object oMember = GetPartyMemberByIndex(nIndex);
        if (!GetIsObjectValid(oMember)) continue;
        if (oMember == oExile) continue;
        if (GetTag(oMember) == "") continue;                                   // the Exile's own tag is empty
        if (nKind == 0 && K2AP_RaiseSkill(oMember, nWhich)) nDone++;
        if (nKind == 1 && K2AP_RaiseAbility(oMember, nWhich)) nDone++;
    }
    K2SE_OutboxPut("PB|" + IntToString(nKind) + "|" + IntToString(nWhich) + "|" + IntToString(nDone));
    return nDone;
}
