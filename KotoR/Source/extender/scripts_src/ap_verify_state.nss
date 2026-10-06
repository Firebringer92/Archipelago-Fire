// Diagnostic only -- reads back the player's current skill ranks, class(es),
// and levels via 100% vanilla read-only functions, and logs them all in one
// line. This gives us exact, known-correct values to search for when memory
// scanning for the creature stats structure -- no guessing needed.
#include "kse"

void DoVerify()
{
    object oPC = GetFirstPC();

    string sSkills = "cu=" + IntToString(GetSkillRank(SKILL_COMPUTER_USE, oPC))
        + ",dm=" + IntToString(GetSkillRank(SKILL_DEMOLITIONS, oPC))
        + ",st=" + IntToString(GetSkillRank(SKILL_STEALTH, oPC))
        + ",aw=" + IntToString(GetSkillRank(SKILL_AWARENESS, oPC))
        + ",pe=" + IntToString(GetSkillRank(SKILL_PERSUADE, oPC))
        + ",rp=" + IntToString(GetSkillRank(SKILL_REPAIR, oPC))
        + ",se=" + IntToString(GetSkillRank(SKILL_SECURITY, oPC))
        + ",ti=" + IntToString(GetSkillRank(SKILL_TREAT_INJURY, oPC));

    int nClass0 = GetClassByPosition(0, oPC);
    int nLevel0 = GetLevelByPosition(0, oPC);
    int nClass1 = GetClassByPosition(1, oPC);
    int nLevel1 = GetLevelByPosition(1, oPC);

    string sClasses = "class0=" + IntToString(nClass0) + "@" + IntToString(nLevel0)
        + ",class1=" + IntToString(nClass1) + "@" + IntToString(nLevel1);

    int nXP = GetXP(oPC);
    int nHD = GetHitDice(oPC);

    KSE_Diag(7, "AP|VERIFY|" + sSkills + "|" + sClasses + "|xp=" + IntToString(nXP) + "|hd=" + IntToString(nHD));
}

void main()
{
    DelayCommand(3.0, DoVerify());
}
