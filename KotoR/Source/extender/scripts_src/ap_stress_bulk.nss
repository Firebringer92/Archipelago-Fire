// Test-only: simulates "many checks arrive at once" (e.g. reconnecting after
// being offline) by granting a large batch of varied things in a SINGLE
// script invocation -- items, XP, credits, an ability increase, and a skill
// bump, all back to back with no delay between them. Probes whether a burst
// of grants in one tick causes instability, informing whether real
// AP-client delivery needs throttling/staggering.
#include "kse"

void DoApply()
{
    object oPC = GetFirstPC();
    int i;

    for (i = 0; i < 20; i++)
    {
        CreateItemOnObject("g_i_medeqpmnt01", oPC, 1);
    }
    for (i = 0; i < 15; i++)
    {
        CreateItemOnObject("g_w_fraggren01", oPC, 1);
    }
    for (i = 0; i < 10; i++)
    {
        GiveXPToCreature(oPC, 25);
    }
    GiveGoldToCreature(oPC, 500);
    ApplyEffectToObject(DURATION_TYPE_PERMANENT, EffectAbilityIncrease(ABILITY_WISDOM, 1), oPC);
    KSE_AdjustCreatureSkills(oPC, SKILL_AWARENESS, 1);

    KSE_Diag(95, "AP|TESTPREP|stress_bulk|done|xp=" + IntToString(GetXP(oPC))
        + "|credits=" + IntToString(GetGold(oPC)));
}

void main()
{
    DelayCommand(3.0, DoApply());
}
