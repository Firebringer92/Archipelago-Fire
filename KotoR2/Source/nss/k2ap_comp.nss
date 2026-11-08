// k2ap_comp.nss -- which companions the player may use (include file; docs/COMPANION_STAGING.md section 8b).
//
// The rule: story joins stay vanilla. In the modes where items decide (none, ap_gated, ap_limited) a companion whose item has not arrived is HIDDEN: still
// available (the Hawk hub, the cutscenes and the joins need that) but not selectable and not in the active party. The item (or the client's unlock in
// ap_limited) makes them usable. In Default mode nothing here acts.
//
// Where the unlock set lives: player local numbers 5 (slots 0-7) and 6 (slots 8-11), one bit per slot. It is saved with the game, so a reload brings it back
// with the party table. (Local numbers above index 0 are unverified in K2: live test 23.) Slots 12 and up (the extra companions) are not hidden here: they
// become available only when their item arrives, so they need no hiding. Their look is applied by K2AP_LookEnforce below.

#include "k2ap_seed"

int K2AP_CompUnlocked(object oPC, int nSlot)
{
    return (GetLocalNumber(oPC, 5 + nSlot / 8) >> (nSlot % 8)) & 1;
}

void K2AP_CompSetUnlocked(object oPC, int nSlot)
{
    int nIndex = 5 + nSlot / 8;
    SetLocalNumber(oPC, nIndex, GetLocalNumber(oPC, nIndex) | (1 << (nSlot % 8)));
}

// The item arrived: the companion becomes usable. A companion the story has not recruited yet just gets the mark; when the story joins them, the hiding pass
// leaves them alone. Returns TRUE.
int K2AP_CompUnlock(object oPC, int nSlot)
{
    if (nSlot < 0 || nSlot > 11) return FALSE;
    K2AP_CompSetUnlocked(oPC, nSlot);
    if (GetNPCSelectability(nSlot) != -1) SetNPCSelectability(nSlot, 1);
    return TRUE;
}

// Hides every companion whose item has not arrived. Called from the dispatcher's tick at calm moments (not in a conversation, a cutscene or a fight).
// Returns how many changes it made. A game that did not get the client's patch (K2AP_Patched() = 0) is left alone, and so is Default mode.
int K2AP_CompEnforce(object oPC)
{
    if (K2AP_Patched() == 0 || K2AP_Companions() == 1) return 0;
    int nChanges = 0;
    int nSlot;
    for (nSlot = 0; nSlot < 12; nSlot++)
    {
        if (K2AP_CompUnlocked(oPC, nSlot)) continue;
        if (GetNPCSelectability(nSlot) == -1) continue;               // not available: the story has not recruited them yet
        if (GetNPCSelectability(nSlot) != 0)
        {
            SetNPCSelectability(nSlot, 0);
            nChanges++;
        }
        if (IsNPCPartyMember(nSlot))
        {
            RemoveNPCFromPartyToBase(nSlot);
            nChanges++;
        }
    }
    if (nChanges > 0) K2SE_OutboxPut("CH|" + IntToString(nChanges));
    return nChanges;
}

// TRUE when the creature already carries a disguise effect.
int K2AP_HasDisguise(object oCreature)
{
    effect eEffect = GetFirstEffect(oCreature);
    while (GetIsEffectValid(eEffect))
    {
        if (GetEffectType(eEffect) == EFFECT_TYPE_DISGUISE) return TRUE;
        eEffect = GetNextEffect(oCreature);
    }
    return FALSE;
}

// The look of the extra companions (slots 12 to 31): each is built from one generic template (client/k2_extras.py) and shows the character's appearance.2da row, which the
// client puts in the seed as ap_look_<slot>. A permanent disguise effect gives the look; the effect belongs to the creature, so a creature that is made again (a new
// area, a loaded game) has none until this pass puts it on. Called from the dispatcher's tick at calm moments. Returns how many disguises it put on; each is reported
// once to the client as "LK|<slot>|<row>".
int K2AP_LookEnforce()
{
    if (K2AP_Patched() == 0) return 0;
    int nApplied = 0;
    int nSlot;
    for (nSlot = 12; nSlot < 32; nSlot++)
    {
        int nLook = K2SE_ConfigInt("ap_look_" + IntToString(nSlot), 0);
        if (nLook <= 0) continue;
        object oCreature = GetObjectByTag("apxc" + IntToString(nSlot));
        if (!GetIsObjectValid(oCreature)) continue;
        if (K2AP_HasDisguise(oCreature)) continue;
        ApplyEffectToObject(DURATION_TYPE_PERMANENT, SupernaturalEffect(EffectDisguise(nLook)), oCreature);
        K2SE_OutboxPut("LK|" + IntToString(nSlot) + "|" + IntToString(nLook));
        nApplied++;
    }
    return nApplied;
}
