// k2ap_revit.nss -- Improved Revitalize and Master Revitalize bring back the fallen with more vitality.
//
// The game's own force power script (k_sp1_generic) gives these two powers a flat 25 and 50 vitality points, which is next to nothing at the levels where the powers
// are learned. This check is joined onto that script (tools/build_gate_wrappers.py, tools/ncs_merge.py) and runs first: for these two powers it does the same thing
// the game does (every fallen, non-droid party member stands up) with larger flat amounts, and ends the script. For every other power it answers 0 and the game's script runs untouched. Revitalize itself (the single closest ally) is left as the game has it.

int K2AP_RevitalizeHeal(int nSpell)
{
    if (nSpell == FORCE_POWER_IMPROVED_REVITALIZE) return 500;      // TEMPORARY test value; the shipped amount is 125
    return 250;                                                 // Master Revitalize
}

int StartingConditional()
{
    int nSpell = GetSpellId();
    if (nSpell != FORCE_POWER_IMPROVED_REVITALIZE && nSpell != FORCE_POWER_MASTER_REVITALIZE) return FALSE;
    // Only a party member can use it: enemies who fall die, they are not knocked out.
    if (!IsObjectPartyMember(OBJECT_SELF)) return TRUE;
    int nHeal = K2AP_RevitalizeHeal(nSpell);
    int nIndex;
    for (nIndex = 0; nIndex < 3; nIndex++)
    {
        object oMember = GetPartyMemberByIndex(nIndex);
        if (oMember == OBJECT_SELF) continue;                   // the caster is standing
        if (!GetIsObjectValid(oMember)) continue;
        if (GetRacialType(oMember) == RACIAL_TYPE_DROID) continue;
        if (GetCurrentHitPoints(oMember) >= 1) continue;
        SignalEvent(oMember, EventSpellCastAt(OBJECT_SELF, nSpell, FALSE));
        ApplyEffectToObject(DURATION_TYPE_INSTANT, EffectResurrection(), oMember);
        ApplyEffectToObject(DURATION_TYPE_INSTANT, EffectHeal(nHeal), oMember);
        ApplyEffectToObject(DURATION_TYPE_INSTANT, EffectVisualEffect(9008), oMember);
    }
    return TRUE;
}
