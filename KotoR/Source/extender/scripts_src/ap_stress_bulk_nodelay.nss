// Same as ap_stress_bulk.nss but with NO DelayCommand -- calls the grant
// logic directly, synchronously, in main(). Tests whether DelayCommand
// scheduled from within an ExecuteScript-invoked context (as opposed to a
// native top-level engine invocation) survives in this engine build. If
// this variant's completion line appears but the delayed one never did,
// that confirms DelayCommand is the broken piece, not ExecuteScript nesting
// depth itself.
#include "kse"

void main()
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

    KSE_Diag(96, "AP|TESTPREP|stress_bulk_nodelay|done|xp=" + IntToString(GetXP(oPC))
        + "|credits=" + IntToString(GetGold(oPC)));
}
