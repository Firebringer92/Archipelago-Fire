// k2ap_stand.nss -- Standing companions: the two extra companions of the Party Console (include file).
//
// The game's party holds the Exile and two followers; a third and fourth follower in the party table crash or corrupt it (docs/COMPANION_SLOT_TEST.md, stages 34-35), so the extra two
// are not party members. They are the companions' own creatures, spawned beside the Exile, which a script tells every three seconds to follow and to fight the nearest enemy
// (the roster of the early tests, kept as the console's second job). They have no portrait and are not on the party screen's buttons, they earn no experience and take none of
// the party-wide boosts while they stand (they work like any companion out of the party: rotate one in to level it), but they are the same characters with the same gear.
//
// State, on the Exile (saved with the game): local numbers 7 and 8 = standing slot + 1 (0 = nobody), 9 and 10 = the active pair put aside while the screen picks the standing
// pair (see nss/k2ap_pcstand.nss). The loop's generation is extender memory ("stand_gen"): a new area entry (tools/build_area_wrappers.py's tail) starts a new loop.
// Config switch: ap_standing=0 turns the whole thing off. Lines for the client's recorder: SC|<step>|<detail>.

#include "k2se_disp"
#include "k2ap_gift"

int K2AP_StandOn()
{
    if (!K2SE_IsPresent()) return FALSE;
    if (K2AP_Patched() == 0) return FALSE;
    return K2SE_ConfigInt("ap_standing", 1) != 0;
}

// the two standing slots (k = 0, 1); -1 = nobody
int K2AP_StandGet(int k)
{
    return GetLocalNumber(GetFirstPC(), 7 + k) - 1;
}

void K2AP_StandSet(int k, int nSlot)
{
    SetLocalNumber(GetFirstPC(), 7 + k, nSlot + 1);
}

// the active pair put aside during the pick (k = 0, 1); -1 = nobody
int K2AP_StandSaved(int k)
{
    return GetLocalNumber(GetFirstPC(), 9 + k) - 1;
}

void K2AP_StandSaveSet(int k, int nSlot)
{
    SetLocalNumber(GetFirstPC(), 9 + k, nSlot + 1);
}

void K2AP_StandLog(string sStep, string sDetail)
{
    if (K2SE_IsPresent()) K2SE_OutboxPut("SC|" + sStep + "|" + sDetail);
}

// The creature tags: the twelve story companions' own (the same table the early roster used), "apxc<slot>" for the extra and generated ones (client/k2_extras.py).
string K2AP_StandTag(int nSlot)
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
    if (nSlot == 11) return "Disciple";
    return "apxc" + IntToString(nSlot);
}

object K2AP_StandCreature(int nSlot)
{
    return GetObjectByTag(K2AP_StandTag(nSlot));
}

string K2AP_StandName(int nSlot)
{
    object o = K2AP_StandCreature(nSlot);
    if (GetIsObjectValid(o)) return GetName(o);
    if (nSlot < 12) return K2AP_GiftName(nSlot);
    return "companion " + IntToString(nSlot - 11);
}

// "A and B" for the slots given (-1 is skipped), "no one" for none.
string K2AP_StandNames(int nA, int nB)
{
    string sOut = "";
    if (nA >= 0) sOut = K2AP_StandName(nA);
    if (nB >= 0)
    {
        if (sOut != "") sOut = sOut + " and ";
        sOut = sOut + K2AP_StandName(nB);
    }
    if (sOut == "") return "no one";
    return sOut;
}

// The slot of the active party's k-th follower (the Exile is not a slot): the first two found; -1 when there is none.
int K2AP_StandActive(int k)
{
    int nFound = 0;
    int nSlot;
    for (nSlot = 0; nSlot < 32; nSlot++)
    {
        if (IsNPCPartyMember(nSlot))
        {
            if (nFound == k) return nSlot;
            nFound++;
        }
    }
    return -1;
}

// A standing companion leaves: the creature goes back to the base with what it carries and has learnt (RemoveNPCFromPartyToBase keeps the state of a companion whether or not
// it is in the party; a destroyed one comes back from the stored template).
void K2AP_StandRelease(int nSlot)
{
    if (nSlot < 0) return;
    if (GetIsObjectValid(K2AP_StandCreature(nSlot))) RemoveNPCFromPartyToBase(nSlot);
    K2AP_StandLog("release", IntToString(nSlot));
}

// True while a scene or a menu has the player: the loop does nothing then.
int K2AP_StandBusy(object oPC)
{
    if (!GetIsObjectValid(oPC)) return TRUE;
    if (GetIsDead(oPC)) return TRUE;
    if (GetIsConversationActive()) return TRUE;
    if (GetIsInConversation(oPC)) return TRUE;
    if (GetPlayerRestrictMode(oPC) != 0) return TRUE;
    if (IsMoviePlaying()) return TRUE;
    return FALSE;
}

// One standing companion: made when missing (outside a fight), then sent to the nearest enemy while there is a fight, else after the Exile.
void K2AP_StandOne(object oPC, int k)
{
    int nSlot = K2AP_StandGet(k);
    if (nSlot < 0) return;
    if (IsNPCPartyMember(nSlot) || !IsAvailableCreature(nSlot))           // the active party took them, or they are no longer one of ours: no longer standing
    {
        K2AP_StandSet(k, -1);
        K2AP_StandLog("drop", IntToString(nSlot));
        return;
    }
    object o = K2AP_StandCreature(nSlot);
    if (!GetIsObjectValid(o))
    {
        if (GetIsInCombat(oPC)) return;
        o = SpawnAvailableNPC(nSlot, GetLocation(oPC));
        K2AP_StandLog("spawn", IntToString(nSlot) + "|" + IntToString(GetIsObjectValid(o)));
        if (!GetIsObjectValid(o)) return;
    }
    object oEnemy = GetNearestCreature(CREATURE_TYPE_REPUTATION, REPUTATION_TYPE_ENEMY, o, 1, CREATURE_TYPE_IS_ALIVE, TRUE);
    if (GetIsObjectValid(oEnemy) && GetDistanceBetween(oEnemy, oPC) < 25.0 && (GetIsInCombat(oPC) || GetIsInCombat(o)))
    {
        if (GetAttackTarget(o) != oEnemy)
        {
            AssignCommand(o, ClearAllActions());
            AssignCommand(o, ActionAttack(oEnemy));
        }
    }
    else if (GetDistanceBetween(o, oPC) > 4.0)
    {
        AssignCommand(o, ClearAllActions());
        AssignCommand(o, ActionMoveToObject(oPC, TRUE, 3.0));
    }
}

void K2AP_StandTick(int nGen)
{
    if (StringToInt(K2SE_MemGet("stand_gen")) != nGen) return;
    if (K2AP_StandGet(0) < 0 && K2AP_StandGet(1) < 0) return;             // nobody stands: the loop ends (the next pick starts one)
    object oPC = GetFirstPC();
    if (!K2AP_StandBusy(oPC) && GetTag(oPC) == "")                         // the Exile, not a body the story has handed over
    {
        K2AP_StandOne(oPC, 0);
        K2AP_StandOne(oPC, 1);
    }
    DelayCommand(3.0, K2AP_StandTick(nGen));
}

// Starts (or restarts) the loop; any earlier one stops at its next turn.
void K2AP_StandStart()
{
    int nGen = StringToInt(K2SE_MemGet("stand_gen")) + 1;
    K2SE_MemSet("stand_gen", IntToString(nGen));
    DelayCommand(4.0, K2AP_StandTick(nGen));
}

// The area entry hook (after the game's own entry script): the companions who stood in the last area are made again here.
void K2AP_StandEnter()
{
    if (!K2AP_StandOn()) return;
    if (K2AP_StandGet(0) < 0 && K2AP_StandGet(1) < 0) return;
    K2AP_StandStart();
}

// The console's header: who is with you and who stands beside you. Token 9250.
void K2AP_StandMenu(object oPC)
{
    string sNow = K2AP_StandNames(K2AP_StandActive(0), K2AP_StandActive(1));
    string sStand = K2AP_StandNames(K2AP_StandGet(0), K2AP_StandGet(1));
    SetCustomToken(9250, "Party Console. In your party: " + sNow + ". Standing beside you: " + sStand + " (they follow and fight, but are not in the party and earn no experience).");
}
