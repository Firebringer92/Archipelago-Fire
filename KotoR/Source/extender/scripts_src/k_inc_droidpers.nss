// Persuade check for a droid PC (starting_class=droid), included by the droid copies of k_con_perseasy / persmed / pershigh and the three
// Manaan planet-vote steps (installed by scripts/generate_droid_assets.py).
//
// A droid cannot train Persuade (skills.2da droidcanuse = 0), so the vanilla AutoDC reads no usable skill rank for it. This version
// uses the same bracket table as the game's AutoDC (k_inc_utility), but takes the player's Charisma modifier (never below 0) as the rank,
// so Charisma buffs and items help. Rank over hit dice plus 5 gives the bracket: up to 0.25 only easy checks have a chance (40%), up to
// 0.5 easy 50% and medium 25%, and so on. Anyone who is not a droid gets the unchanged vanilla roll.
#include "k_inc_debug"
#include "k_inc_utility"

int DroidAutoDC(int nDC, object oPC)
{
    int nRank = GetAbilityModifier(ABILITY_CHARISMA, oPC);
    if (nRank < 0) nRank = 0;
    int nRoll = d100();
    float fPercent = IntToFloat(nRank) / IntToFloat(GetHitDice(oPC) + 5);

    if (fPercent <= 0.25)
    {
        if (nDC == 0 && nRoll <= 40) return TRUE;
    }
    else if (fPercent <= 0.5)
    {
        if (nDC == 0 && nRoll <= 50) return TRUE;
        if (nDC == 1 && nRoll <= 25) return TRUE;
    }
    else if (fPercent <= 0.75)
    {
        if (nDC == 0 && nRoll <= 75) return TRUE;
        if (nDC == 1 && nRoll <= 50) return TRUE;
        if (nDC == 2 && nRoll <= 25) return TRUE;
    }
    else if (fPercent <= 1.0)
    {
        if (nDC == 0 && nRoll <= 100) return TRUE;
        if (nDC == 1 && nRoll <= 100) return TRUE;
        if (nDC == 2 && nRoll <= 75) return TRUE;
    }
    else
    {
        return TRUE;
    }
    return FALSE;
}

// The check every droid copy calls: droids roll on Charisma, everyone else gets the vanilla roll.
int PersuadeCheck(int nDC, object oPC)
{
    if (GetRacialType(oPC) == 5) return DroidAutoDC(nDC, oPC);
    return AutoDC(nDC, SKILL_PERSUADE, oPC);
}
