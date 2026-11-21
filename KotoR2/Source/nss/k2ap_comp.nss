// k2ap_comp.nss -- which companions the player may use (include file; docs/COMPANION_STAGING.md section 8b).
//
// The rule: story joins stay vanilla. In the modes where items decide (none, ap_gated, ap_limited) a companion whose item has not arrived is HIDDEN: still
// available (the Hawk hub, the cutscenes and the joins need that) but not selectable and not in the active party. The item (or the client's unlock in
// ap_limited) makes them usable. In Default mode nothing here acts.
//
// Where the unlock set lives: player local numbers 5 (slots 0-6) and 6 (slot 7 in bit 4, slots 8-11 in bits 0-3), one bit per slot. A local number keeps only 7 bits (found in the
// saves 2026-11-17: number 5 read 127, so the eighth bit, Mira, slot 7, was never stored), so no bit above 6 may be used. It is saved with the game, so a reload brings it back
// with the party table. (Local numbers above index 0 are unverified in K2: live test 23.) Slots 12 and up (the extra companions) are not hidden here: they
// become available only when their item arrives, so they need no hiding. Their look is applied by K2AP_LookEnforce below.

#include "k2ap_seed"

int K2AP_CompNumber(int nSlot)
{
    if (nSlot < 7) return 5;
    return 6;
}

int K2AP_CompShift(int nSlot)
{
    if (nSlot == 7) return 4;
    if (nSlot < 7) return nSlot;
    return nSlot - 8;
}

int K2AP_CompUnlocked(object oPC, int nSlot)
{
    return (GetLocalNumber(oPC, K2AP_CompNumber(nSlot)) >> K2AP_CompShift(nSlot)) & 1;
}

void K2AP_CompSetUnlocked(object oPC, int nSlot)
{
    int nIndex = K2AP_CompNumber(nSlot);
    SetLocalNumber(oPC, nIndex, GetLocalNumber(oPC, nIndex) | (1 << K2AP_CompShift(nSlot)));
}

// A scene loan (nss/k2ap_scene.nss) sets a slot's bit for a scene and marks it in the extender's memory ("loan<slot>": 0 none, 1 and up = calm passes counted + 1). Its own timer
// ends it, but a module change or a load cuts such a timer short and the bit would stay set for good, keeping a companion the item never brought. So the hiding pass counts the
// calm passes of every marked loan and ends it after four (about twelve seconds); a companion whose item really arrived (the "cu<slot>" mark of K2AP_CompUnlock) keeps the bit.
// Reported as "SR|<slot>".
void K2AP_LoanSweep(object oPC)
{
    int nSlot;
    for (nSlot = 0; nSlot < 12; nSlot++)
    {
        string sKey = "loan" + IntToString(nSlot);
        int nCount = StringToInt(K2SE_MemGet(sKey));
        if (nCount <= 0) continue;
        if (K2SE_MemGet("cu" + IntToString(nSlot)) == "1")
        {
            K2SE_MemSet(sKey, "0");
            continue;
        }
        if (nCount < 5)
        {
            K2SE_MemSet(sKey, IntToString(nCount + 1));
            continue;
        }
        int nIndex = K2AP_CompNumber(nSlot);
        SetLocalNumber(oPC, nIndex, GetLocalNumber(oPC, nIndex) & ~(1 << K2AP_CompShift(nSlot)));
        K2SE_MemSet(sKey, "0");
        K2SE_OutboxPut("SR|" + IntToString(nSlot));
    }
}

// Slots 7 and 8 (Mira, T3-M4) are lent to the story in the prologue and on Peragus: the story makes the slot available and, a moment later, switches the player into
// that body (101PER a_106perjump, then 106PER), and hiding the slot in between breaks the switch (a black screen; the player is still the Exile then). So in those
// modules (001EBO, 002EBO and the ones ending in PER) these two slots are not hidden; the hiding starts at the first calm moment after the story leaves them.
// In 153HAR (the Sion duel) Atton and Kreia (slots 0 and 6) are held too, for the whole stay: see K2AP_StageSion.
int K2AP_CompHeld(int nSlot)
{
    string sModule = GetStringUpperCase(GetModuleName());
    if (sModule == "153HAR") return nSlot == 0 || nSlot == 6;
    if (nSlot != 7 && nSlot != 8) return FALSE;
    return GetStringRight(sModule, 3) == "PER" || sModule == "001EBO" || sModule == "002EBO";
}

// The party template each story companion is made from when the item joins them before the story has (the game's own "p_" templates, the ones the story scripts use).
string K2AP_CompTemplate(int nSlot)
{
    if (nSlot == 0) return "p_atton";
    if (nSlot == 1) return "p_baodur";
    if (nSlot == 2) return "p_mand";
    if (nSlot == 3) return "p_g0t0";
    if (nSlot == 4) return "p_handmaiden";
    if (nSlot == 5) return "p_hk47";
    if (nSlot == 6) return "p_kreia";
    if (nSlot == 7) return "p_mira";
    if (nSlot == 8) return "p_t3m4";
    if (nSlot == 9) return "p_visas";
    if (nSlot == 10) return "p_hanharr";
    return "p_disciple";
}

// Staging for the Sion duel. In 153HAR the story's cut scene (a_sion_cut) does nothing ("No Atton or Kreia") unless both are standing in the area, which they are only
// while they are in the party. Called when the area is entered: Atton and Kreia, when not in the party, are brought into it (made available first if the story never
// recruited them, for example when the player went past the HK-50 scene), so the scene
// plays. They stay (K2AP_CompHeld) until the player leaves 153HAR; the story removes Kreia itself at the end of the duel (a_sion_cut), and the hiding pass takes
// whoever is still there out of the party at the first calm moment after the area is left. Does nothing in Default mode or without the client's patch.
void K2AP_StageSion(object oPC)
{
    if (K2AP_Patched() == 0 || K2AP_Companions() == 1) return;
    if (GetStringUpperCase(GetModuleName()) != "153HAR") return;
    int nIndex;
    for (nIndex = 0; nIndex < 2; nIndex++)
    {
        int nSlot = nIndex * 6;                                   // 0 Atton, 6 Kreia
        if (IsNPCPartyMember(nSlot)) continue;
        if (!IsAvailableCreature(nSlot) && !AddAvailableNPCByTemplate(nSlot, K2AP_CompTemplate(nSlot))) continue;     // the story never recruited them (a skipped join scene): the duel needs them anyway
        object oCompanion = GetObjectByTag(nSlot == 0 ? "Atton" : "Kreia");
        if (!GetIsObjectValid(oCompanion)) oCompanion = SpawnAvailableNPC(nSlot, GetLocation(oPC));
        int bAdded = GetIsObjectValid(oCompanion) && AddPartyMember(nSlot, oCompanion);
        K2SE_OutboxPut("SS|" + IntToString(nSlot) + "|" + IntToString(bAdded));
    }
}

// The item arrived: the companion becomes usable. A companion the story has recruited already is just unhidden. One the story has not recruited yet JOINS now: the slot
// is made available from the game's party template and selectable, so the player can pick them on the party screen (config ap_comp_join=0 turns this off and leaves
// the story to recruit them). The story's own join scene, when it comes, runs on a slot that is already available. Slots 7 and 8 (Mira, T3-M4) are lent to the
// prologue and Peragus, where the story takes them back and gives them out itself, so nothing is added there. Returns TRUE.
int K2AP_CompUnlock(object oPC, int nSlot)
{
    if (nSlot < 0 || nSlot > 11) return FALSE;
    K2AP_CompSetUnlocked(oPC, nSlot);
    K2SE_MemSet("cu" + IntToString(nSlot), "1");                      // the item arrived: a scene loan that ends now (nss/k2ap_scene.nss K2AP_SceneRelease) leaves the bit alone
    if (GetNPCSelectability(nSlot) == -1 && K2SE_ConfigInt("ap_comp_join", 1) != 0)
    {
        if (!K2AP_CompHeld(nSlot))
        {
            int bAdded = AddAvailableNPCByTemplate(nSlot, K2AP_CompTemplate(nSlot));
            K2SE_OutboxPut("CJ|" + IntToString(nSlot) + "|" + IntToString(bAdded));
        }
    }
    if (GetNPCSelectability(nSlot) != -1) SetNPCSelectability(nSlot, 1);
    return TRUE;
}

// Hides every companion whose item has not arrived. Called from the dispatcher's tick at calm moments (not in a conversation, a cutscene or a fight).
// Returns how many changes it made. A game that did not get the client's patch (K2AP_Patched() = 0) is left alone, and so is Default mode.
int K2AP_CompEnforce(object oPC)
{
    if (K2AP_Patched() == 0 || K2AP_Companions() == 1) return 0;
    // While the player is playing a companion's body (the yacht and the Dxun scenes) nothing is hidden: making the character the player controls unselectable
    // leaves the game with nobody to show (a black screen). The Exile's own tag is empty, so any other tag is a played companion.
    object oLeader = GetPartyLeader();
    if (GetIsObjectValid(oLeader) && oLeader != oPC) return 0;
    if (GetTag(oPC) != "") return 0;
    K2AP_LoanSweep(oPC);
    // Mira and T3-M4 are not hidden while the story lends them (K2AP_CompHeld above).
    int nChanges = 0;
    int nSlot;
    for (nSlot = 0; nSlot < 12; nSlot++)
    {
        if (K2AP_CompHeld(nSlot)) continue;
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

// The droid player's look. The class job puts the disguise on once (nss/k2se_disp.nss DispClassFinish); the game takes disguise effects off the Exile by itself (the Peragus
// script a_suitrestrict removes every effect of type EFFECT_TYPE_DISGUISE when the space-suit state is on), so the tick puts it back. The client writes ap_pc_look=<row> only
// for a seed whose start class has a look. Reported once per application as "LK|0|<row>".
int K2AP_PlayerLookEnforce(object oPC)
{
    int nLook = K2SE_ConfigInt("ap_pc_look", 0);
    if (nLook <= 0 || !GetIsObjectValid(oPC)) return 0;
    if (GetLevelByPosition(1, oPC) < 1) return 0;                        // the character is not ready yet
    if (K2AP_HasDisguise(oPC)) return 0;
    ApplyEffectToObject(DURATION_TYPE_PERMANENT, SupernaturalEffect(EffectDisguise(nLook)), oPC);
    K2SE_OutboxPut("LK|0|" + IntToString(nLook));
    return 1;
}

// The droid plating: every droid in the party (the player of a droid start and the companions the seed makes droids, race 5) wears the hidden item ap_drdhide (client/k2_assets.py:
// immunity to poison, paralysis and mind spells, as the game's own droid companions have). A droid that already wears a creature hide (G0-T0, HK-47, T3-M4) is left alone.
// A creature made anew (another template copy, a new area) has none, so the tick puts it on again. Reported as "DH|<tag or 0 for the Exile>".
int K2AP_DroidHideEnforce()
{
    int nDone = 0;
    int nIndex;
    for (nIndex = 0; nIndex < 3; nIndex++)
    {
        object oMember = GetPartyMemberByIndex(nIndex);
        if (!GetIsObjectValid(oMember)) continue;
        if (GetRacialType(oMember) != RACIAL_TYPE_DROID) continue;
        if (GetIsObjectValid(GetItemInSlot(INVENTORY_SLOT_CARMOUR, oMember))) continue;
        object oHide = CreateItemOnObject("ap_drdhide", oMember, 1);
        if (!GetIsObjectValid(oHide)) continue;
        AssignCommand(oMember, ActionEquipItem(oHide, INVENTORY_SLOT_CARMOUR));
        K2SE_OutboxPut("DH|" + (GetTag(oMember) == "" ? "0" : GetTag(oMember)));
        nDone++;
    }
    return nDone;
}

// The tag of each story companion's creature (the game's p_ templates), to find the one that stands in the area.
string K2AP_CompTag(int nSlot)
{
    if (nSlot == 0) return "Atton";
    if (nSlot == 1) return "BaoDur";
    if (nSlot == 2) return "Mand";
    if (nSlot == 4) return "Handmaiden";
    if (nSlot == 6) return "Kreia";
    if (nSlot == 7) return "Mira";
    if (nSlot == 9) return "VisasMarr";
    if (nSlot == 10) return "Hanharr";
    if (nSlot == 11) return "Disciple";
    return "";
}

// Takes every disguise effect off a creature (one scan per effect: the scan restarts after each removal).
void K2AP_StripDisguise(object oCreature)
{
    int nGuard;
    for (nGuard = 0; nGuard < 6; nGuard++)
    {
        int bFound = FALSE;
        effect eEffect = GetFirstEffect(oCreature);
        while (GetIsEffectValid(eEffect))
        {
            if (GetEffectType(eEffect) == EFFECT_TYPE_DISGUISE)
            {
                RemoveEffect(oCreature, eEffect);
                bFound = TRUE;
                break;
            }
            eEffect = GetNextEffect(oCreature);
        }
        if (!bFound) return;
    }
}

// The droid look of a story companion that must be a disguise (the protocol droid body; client k2_extras.companion_look_lines writes ap_clook_<slot>=<row>). The creature's
// own appearance stays, and the effect is put on again whenever a creature made anew has none. A disguise is saved with the game, so one put on under an earlier look row
// would stay for ever: the first pass of a game session takes any disguise off and puts the configured one on (the session's mark "clk<slot>" holds the row done).
// Reported once per application as "LK|<slot>|<row>".
int K2AP_CompLookEnforce()
{
    int nApplied = 0;
    int nSlot;
    for (nSlot = 0; nSlot < 12; nSlot++)
    {
        int nLook = K2SE_ConfigInt("ap_clook_" + IntToString(nSlot), 0);
        if (nLook <= 0) continue;
        string sTag = K2AP_CompTag(nSlot);
        if (sTag == "") continue;
        string sMark = "clk" + IntToString(nSlot);
        int bFresh = K2SE_MemGet(sMark) != IntToString(nLook);          // no pass yet in this session: any saved disguise is of unknown look
        int nSeen = 0;
        int nCopy;
        for (nCopy = 0; nCopy < 4; nCopy++)                          // every object with the tag: a module's own copy and the party's can both exist
        {
            object oCreature = GetObjectByTag(sTag, nCopy);
            if (!GetIsObjectValid(oCreature)) break;
            if (GetObjectType(oCreature) != OBJECT_TYPE_CREATURE) continue;
            nSeen++;
            if (bFresh) K2AP_StripDisguise(oCreature);
            else if (K2AP_HasDisguise(oCreature)) continue;
            ApplyEffectToObject(DURATION_TYPE_PERMANENT, SupernaturalEffect(EffectDisguise(nLook)), oCreature);
            K2SE_OutboxPut("LK|" + IntToString(nSlot) + "|" + IntToString(nLook));
            nApplied++;
        }
        if (nSeen > 0) K2SE_MemSet(sMark, IntToString(nLook));
    }
    return nApplied;
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
