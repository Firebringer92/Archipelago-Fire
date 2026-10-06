// Console helper, NOT shipped (not in any packaging list): run it from the in-game
// console with `runscript ap_test`. Gives the player and the active party permanent
// immunity to the effects that lock a character out of acting -- stun, paralysis,
// sleep, daze, confusion, entangle and knockdown -- for a fight that is not winnable
// otherwise (e.g. the Star Forge command center's endless spawns). It adds nothing
// else, does not touch damage, and goes away with a reload of a save made before.
#include "kse"

void Proof(object oTarget)
{
    if (!GetIsObjectValid(oTarget)) return;
    ApplyEffectToObject(DURATION_TYPE_PERMANENT, SupernaturalEffect(EffectImmunity(IMMUNITY_TYPE_STUN)), oTarget);
    ApplyEffectToObject(DURATION_TYPE_PERMANENT, SupernaturalEffect(EffectImmunity(IMMUNITY_TYPE_PARALYSIS)), oTarget);
    ApplyEffectToObject(DURATION_TYPE_PERMANENT, SupernaturalEffect(EffectImmunity(IMMUNITY_TYPE_SLEEP)), oTarget);
    ApplyEffectToObject(DURATION_TYPE_PERMANENT, SupernaturalEffect(EffectImmunity(IMMUNITY_TYPE_DAZED)), oTarget);
    ApplyEffectToObject(DURATION_TYPE_PERMANENT, SupernaturalEffect(EffectImmunity(IMMUNITY_TYPE_CONFUSED)), oTarget);
    ApplyEffectToObject(DURATION_TYPE_PERMANENT, SupernaturalEffect(EffectImmunity(IMMUNITY_TYPE_ENTANGLE)), oTarget);
    ApplyEffectToObject(DURATION_TYPE_PERMANENT, SupernaturalEffect(EffectImmunity(IMMUNITY_TYPE_KNOCKDOWN)), oTarget);
}

void main()
{
    Proof(GetFirstPC());
    Proof(GetPartyMemberByIndex(1));
    Proof(GetPartyMemberByIndex(2));
    KSE_Diag(176, "AP|CONSOLE|stunproof applied");
}
