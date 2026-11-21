// k2ap_scene.nss -- the companions a story scene needs, brought in by the scene's OWN script (include file; the generated scene checks of tools/build_gate_wrappers.py).
//
// The game's scene script (a trigger's OnEnter, a conversation's action script) is joined with a check by tools/ncs_merge.py. The check runs first and makes sure
// the companions the scene's dialogue and cut scene need are standing in the party: when one is not, they are made available (when the story never recruited them)
// and brought in. The dispatcher is not involved, so the scene plays the same way whatever the dispatcher is doing. The companion is LENT for the scene: the unlock
// bit the hiding pass reads (nss/k2ap_comp.nss) is set so that pass leaves them alone, and K2AP_SceneRelease clears it at the first calm moment after the scene (not in a
// conversation, a fight or a cut scene); the hiding pass then takes them out of the party again, which is the removal. (Adding a companion to the area starts the dispatcher,
// whose first pass would hide them before the dialogue begins, so the loan has to come first.)
//
// Does nothing in Default mode or in a game that did not get the client's patch.

#include "k2ap_seed"

// The party template each story companion is made from (the game's own "p_" templates).
string K2AP_SceneTemplate(int nSlot)
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

// The object tag of the party companion (the speaker tag a dialogue uses).
string K2AP_SceneTag(int nSlot)
{
    if (nSlot == 0) return "Atton";
    if (nSlot == 1) return "BaoDur";
    if (nSlot == 2) return "Mand";
    if (nSlot == 3) return "G0T0";
    if (nSlot == 4) return "Handmaiden";
    if (nSlot == 5) return "HK47";
    if (nSlot == 6) return "Kreia";
    if (nSlot == 7) return "Mira";
    if (nSlot == 8) return "T3M4";
    if (nSlot == 9) return "VisasMarr";
    if (nSlot == 10) return "Hanharr";
    return "Disciple";
}

// A party is the player and two companions. When a scene's companion has to come in and the party is full, one companion who is not part of the scene goes back to the
// base (the party screen brings them back afterwards); a companion other than Atton is chosen first, because most scenes use Atton.
void K2AP_SceneRoom(int nMask)
{
    int nCount = 0;
    int nPick = -1;
    int nSlot;
    for (nSlot = 0; nSlot < 12; nSlot++)
    {
        if (!IsNPCPartyMember(nSlot)) continue;
        nCount++;
        if (((nMask >> nSlot) & 1) == 0 && (nPick == -1 || nPick == 0)) nPick = nSlot;
    }
    if (nCount >= 2 && nPick != -1) RemoveNPCFromPartyToBase(nPick);
}

// The unlock bits the hiding pass reads (nss/k2ap_comp.nss, the same layout): player local numbers 5 (slots 0-6) and 6 (slot 7 in bit 4, slots 8-11 in bits 0-3), one bit per
// slot; a local number keeps only 7 bits. A companion whose bit is set is not hidden.
int K2AP_SceneNumber(int nSlot)
{
    if (nSlot < 7) return 5;
    return 6;
}

int K2AP_SceneShift(int nSlot)
{
    if (nSlot == 7) return 4;
    if (nSlot < 7) return nSlot;
    return nSlot - 8;
}

int K2AP_SceneBit(object oPC, int nSlot)
{
    return (GetLocalNumber(oPC, K2AP_SceneNumber(nSlot)) >> K2AP_SceneShift(nSlot)) & 1;
}

void K2AP_SceneSetBit(object oPC, int nSlot, int bOn)
{
    int nIndex = K2AP_SceneNumber(nSlot);
    int nValue = GetLocalNumber(oPC, nIndex);
    if (bOn) nValue = nValue | (1 << K2AP_SceneShift(nSlot));
    else nValue = nValue & ~(1 << K2AP_SceneShift(nSlot));
    SetLocalNumber(oPC, nIndex, nValue);
}

// True when nothing the player is doing should be interrupted (the same test as the dispatcher's DispCalm).
int K2AP_SceneCalm(object oPC)
{
    if (!GetIsObjectValid(oPC)) return FALSE;
    if (GetIsDead(oPC)) return FALSE;
    if (GetIsInCombat(oPC)) return FALSE;
    if (GetIsConversationActive()) return FALSE;
    if (GetIsInConversation(oPC)) return FALSE;
    if (GetPlayerRestrictMode(oPC) != 0) return FALSE;
    if (IsMoviePlaying()) return FALSE;
    return TRUE;
}

// Ends the loan of a companion: the unlock bit is cleared once the scene is over (nothing is happening: not in a conversation, a fight or a cut scene), so the hiding pass
// takes them out of the party at the next calm moment. Asked again every five seconds until then (up to five minutes). A companion whose item arrived in the meantime
// (K2AP_CompUnlock leaves a mark) stays as they are; being selectable is no sign of that, because the story makes every recruit selectable. Reported as "SR|<slot>".
void K2AP_SceneRelease(int nSlot, int nTries)
{
    object oPC = GetFirstPC();
    if (!GetIsObjectValid(oPC)) return;
    if (K2SE_MemGet("cu" + IntToString(nSlot)) == "1") return;      // the companion's item arrived during the loan (nss/k2ap_comp.nss K2AP_CompUnlock): the bit is theirs now
    if (nTries < 60 && !K2AP_SceneCalm(oPC))
    {
        AssignCommand(oPC, DelayCommand(5.0, K2AP_SceneRelease(nSlot, nTries + 1)));
        return;
    }
    K2AP_SceneSetBit(oPC, nSlot, FALSE);
    K2SE_MemSet("loan" + IntToString(nSlot), "0");
    K2SE_OutboxPut("SR|" + IntToString(nSlot));
}

// Makes sure every companion of the bit set nMask (1 << slot) is in the party for the scene. Each one is first LENT (the unlock bit is set, so the hiding pass leaves them
// alone: adding a companion to the area starts the dispatcher, whose first pass would otherwise hide them before the dialogue begins), then brought in when they are not in the
// party, and the loan ends in K2AP_SceneRelease. A companion who is already unlocked (the item arrived, or an earlier scene's loan is still running) is not touched.
// Reported as "SC|<slot>|<1 when added>".
void K2AP_SceneEnsure(int nMask)
{
    if (K2AP_Patched() == 0 || K2AP_Companions() == 1) return;
    object oPC = GetFirstPC();
    if (!GetIsObjectValid(oPC) || GetHitDice(oPC) < 1) return;
    // while the player plays a companion's body (the yacht, the Dxun scenes) the party is not ours to change
    object oLeader = GetPartyLeader();
    if (GetIsObjectValid(oLeader) && oLeader != oPC) return;
    int nSlot;
    for (nSlot = 0; nSlot < 12; nSlot++)
    {
        if (((nMask >> nSlot) & 1) == 0) continue;
        if (K2AP_SceneBit(oPC, nSlot)) continue;
        K2AP_SceneSetBit(oPC, nSlot, TRUE);
        K2SE_MemSet("loan" + IntToString(nSlot), "1");              // the hiding pass ends the loan too when this timer is cut short (nss/k2ap_comp.nss K2AP_LoanSweep)
        AssignCommand(oPC, DelayCommand(12.0, K2AP_SceneRelease(nSlot, 0)));
        int bAdded = IsNPCPartyMember(nSlot);
        if (!bAdded)
        {
            if (!IsAvailableCreature(nSlot) && !AddAvailableNPCByTemplate(nSlot, K2AP_SceneTemplate(nSlot))) continue;     // the story never recruited them: the scene needs them anyway
            object oCompanion = GetObjectByTag(K2AP_SceneTag(nSlot));
            K2AP_SceneRoom(nMask);
            if (!GetIsObjectValid(oCompanion)) oCompanion = SpawnAvailableNPC(nSlot, GetLocation(oPC));
            bAdded = GetIsObjectValid(oCompanion) && AddPartyMember(nSlot, oCompanion);
        }
        K2SE_OutboxPut("SC|" + IntToString(nSlot) + "|" + IntToString(bAdded));
    }
}

// For a scene whose own script brings the companions in (SpawnAvailableNPC at the scene's waypoints, the landing pad of Nar Shaddaa): nobody is added here, the companions are only
// LENT, so that the hiding pass does not take them away between the script's spawn and the start of the dialogue. The loan ends in K2AP_SceneRelease like the one of
// K2AP_SceneEnsure. Reported as "SL|<slot>".
void K2AP_SceneLend(int nMask)
{
    if (K2AP_Patched() == 0 || K2AP_Companions() == 1) return;
    object oPC = GetFirstPC();
    if (!GetIsObjectValid(oPC) || GetHitDice(oPC) < 1) return;
    object oLeader = GetPartyLeader();
    if (GetIsObjectValid(oLeader) && oLeader != oPC) return;
    int nSlot;
    for (nSlot = 0; nSlot < 12; nSlot++)
    {
        if (((nMask >> nSlot) & 1) == 0) continue;
        if (K2AP_SceneBit(oPC, nSlot)) continue;
        K2AP_SceneSetBit(oPC, nSlot, TRUE);
        K2SE_MemSet("loan" + IntToString(nSlot), "1");
        AssignCommand(oPC, DelayCommand(12.0, K2AP_SceneRelease(nSlot, 0)));
        K2SE_OutboxPut("SL|" + IntToString(nSlot));
    }
}

// For a scene whose actor the area should hold but does not (the story's placed copy of a party companion is missing while that companion is available but hidden: the
// Mira of the Jekk'Jekk Tarr tunnels, 305NAR): when no object with the companion's tag is in the module, the actor is made from the game's party template at the spot the
// story places it, so that the scene's script and dialogue find their speaker. Nothing is added to the party and no slot is touched. Reported as "ST|<slot>|have|<in this area>|<x>|<y>" when an object with the tag exists, and "ST|<slot>|made|<1 when it was made>".
void K2AP_SceneStage(int nSlot, float fX, float fY, float fZ, float fFacing)
{
    if (K2AP_Patched() == 0 || K2AP_Companions() == 1) return;
    object oPC = GetFirstPC();
    if (!GetIsObjectValid(oPC)) return;
    string sSlot = IntToString(nSlot);
    object oHave = GetObjectByTag(K2AP_SceneTag(nSlot));
    if (GetIsObjectValid(oHave))
    {
        vector vAt = GetPosition(oHave);
        int bHere = GetArea(oHave) == GetArea(oPC);
        K2SE_OutboxPut("ST|" + sSlot + "|have|" + IntToString(bHere) + "|" + FloatToString(vAt.x, 0, 1) + "|" + FloatToString(vAt.y, 0, 1));
        if (bHere) return;                                                                 // the story's own copy stands in this area
    }
    location lAt = Location(Vector(fX, fY, fZ), fFacing);                                 // in the area the player is in
    object oActor = CreateObject(OBJECT_TYPE_CREATURE, K2AP_SceneTemplate(nSlot), lAt);
    K2SE_OutboxPut("ST|" + sSlot + "|made|" + IntToString(GetIsObjectValid(oActor)));
}

// Shortened Peragus: the script's owner (OBJECT_SELF, a door whose OnFailToOpen or OnMeleeAttacked is a_compdlg) is unlocked and opened, as the story's own console scripts
// do (a_op106eastdr, a_op106westdr), because the condensed opening skips the puzzles that would. Returns TRUE when it did, which stops the original (its "slice the terminal"
// message). Does nothing in a game without the client's patch or without the option. Reported as "SU|<door tag>".
int K2AP_SceneUnlockDoor()
{
    if (K2AP_Patched() == 0 || K2AP_ShortenedPeragus() == 0) return FALSE;
    object oDoor = OBJECT_SELF;
    if (GetObjectType(oDoor) != OBJECT_TYPE_DOOR) return FALSE;
    SetLocked(oDoor, FALSE);
    AssignCommand(oDoor, ActionOpenDoor(oDoor));
    K2SE_OutboxPut("SU|" + GetTag(oDoor));
    // The hangar (106PER) has no area hook: its entry script is the T3-M4 switch, which must run alone. The player has to reach one of these doors to leave, so the
    // delivery loop is started here (the same script the empty-entry areas use; starting it again only replaces the running loop).
    if (GetStringLowerCase(GetModuleName()) == "106per") ExecuteScript("k2se_ap_enter", GetFirstPC());
    return TRUE;
}

// Clears local boolean nFlag of the script's owner (OBJECT_SELF: the door whose script this is), once: nMarker is a second boolean of the owner that records the reset. For a
// conversation whose first node tests that flag (305NAR's 305han2: c_talkedto picks the cut scene, node 1, while the flag is NOT set, and a node that was already played sets it
// at once, so a cut scene that stopped half way is never offered again and the door only shows its description). Reported as "SF|<flag>|0".
void K2AP_SceneReset(int nFlag, int nMarker)
{
    if (K2AP_Patched() == 0 || K2AP_Companions() == 1) return;
    if (GetLocalBoolean(OBJECT_SELF, nMarker) != 0) return;
    SetLocalBoolean(OBJECT_SELF, nMarker, TRUE);
    SetLocalBoolean(OBJECT_SELF, nFlag, FALSE);
    K2SE_OutboxPut("SF|" + IntToString(nFlag) + "|0");
}

// The check again after fDelay seconds (for a scene whose companion could be taken away before its dialogue starts).
void K2AP_SceneEnsureAgain(int nMask, float fDelay)
{
    object oPC = GetFirstPC();
    if (GetIsObjectValid(oPC)) AssignCommand(oPC, DelayCommand(fDelay, K2AP_SceneEnsure(nMask)));
}

// The Mandalorian duel ring (403DXN): the game's own fight start (a_circle_fight) sends the current opponent (npc_davrel, npc_kex, npc_tagren, npc_kelborn, npc_bralor, by the
// global 403DXN_Battle_Circle) to the ring's enemy spot, wp_circle_enemy. In a played game the second opponent, Kex, stayed at the camp and the duel could not start. A moment
// after the fight start this puts the current opponent at that spot when he is far from it, the same jump the game's script makes (commandable first, then a clean action
// queue). Reported as "RG|<opponent's tag>|<distance to the spot>"; an opponent already near the spot is left alone.
string K2AP_RingTag(int nStage)
{
    if (nStage == 1) return "npc_kex";
    if (nStage == 2) return "npc_tagren";
    if (nStage == 3) return "npc_kelborn";
    if (nStage == 4) return "npc_bralor";
    return "npc_davrel";
}

void K2AP_RingOpponent()
{
    object oSpot = GetObjectByTag("wp_circle_enemy");
    string sTag = K2AP_RingTag(GetGlobalNumber("403DXN_Battle_Circle"));
    object oOpp = GetObjectByTag(sTag);
    if (!GetIsObjectValid(oSpot) || !GetIsObjectValid(oOpp)) return;
    float fAway = GetDistanceBetween(oOpp, oSpot);
    K2SE_OutboxPut("RG|" + sTag + "|" + FloatToString(fAway, 0, 1));
    if (fAway < 25.0) return;
    SetCommandable(TRUE, oOpp);
    AssignCommand(oOpp, ClearAllActions());
    AssignCommand(oOpp, ActionJumpToObject(oSpot, FALSE));
}

// The check, twice (the game's own jump has had time to run by the first, a slow one by the second). Not in a game without the client's patch.
void K2AP_SceneRing()
{
    if (K2AP_Patched() == 0) return;
    object oPC = GetFirstPC();
    if (!GetIsObjectValid(oPC)) return;
    AssignCommand(oPC, DelayCommand(1.5, K2AP_RingOpponent()));
    AssignCommand(oPC, DelayCommand(4.0, K2AP_RingOpponent()));
}
