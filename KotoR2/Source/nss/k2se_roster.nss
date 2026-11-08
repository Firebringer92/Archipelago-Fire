// Roster library. The player's companion pool is four of the twelve companion slots (stored as global numbers, slot + 1,
// 0 = empty): pool entries 0 and 1 start as the active pair, 2 and 3 as the standing pair. Every slot has a fixed creature tag.
// The party holds two followers at a time; the other pool members stay in the area as friendly creatures that are
// told to run back to the player and to attack the nearest enemy every 3 seconds (their own AI only strikes a pose).
string SlotTag(int i)
{
    if (i == 0) return "Atton";
    if (i == 1) return "BaoDur";
    if (i == 2) return "Mand";
    if (i == 3) return "G0T0";
    if (i == 4) return "Handmaiden";
    if (i == 5) return "HK47";
    if (i == 6) return "Kreia";
    if (i == 7) return "Mira";
    if (i == 8) return "T3M4";
    if (i == 9) return "VisasMarr";
    if (i == 10) return "Hanharr";
    return "Disciple";
}

string SlotName(int i)
{
    if (i == 0) return "Atton";
    if (i == 1) return "Bao-Dur";
    if (i == 2) return "Mandalore";
    if (i == 3) return "G0-T0";
    if (i == 4) return "Handmaiden";
    if (i == 5) return "HK-47";
    if (i == 6) return "Kreia";
    if (i == 7) return "Mira";
    if (i == 8) return "T3-M4";
    if (i == 9) return "Visas";
    if (i == 10) return "Hanharr";
    return "Disciple";
}

// The pool lives in local variables of the player object: they are saved with the game and need no entry in globalcat.2da (a global number
// that is not declared there is silently dropped, which is what broke the first version). Entry k (0-3) uses booleans 16+4k .. 19+4k as
// a 4-bit number holding slot + 1 (0 means empty). The follow-loop generation is a local number.
// The vanilla script a_rumble writes boolean 20 on the player (1, then 0), so bit 20 is stored in boolean 62, which no script uses.
int PoolBit(int k, int j)
{
    int b = 16 + 4 * k + j;
    if (b == 20) return 62;
    return b;
}

int PoolGet(int k)
{
    object oPC = GetFirstPC();
    int v = 0;
    if (GetLocalBoolean(oPC, PoolBit(k, 0)) != 0) v = v + 1;
    if (GetLocalBoolean(oPC, PoolBit(k, 1)) != 0) v = v + 2;
    if (GetLocalBoolean(oPC, PoolBit(k, 2)) != 0) v = v + 4;
    if (GetLocalBoolean(oPC, PoolBit(k, 3)) != 0) v = v + 8;
    return v - 1;
}

void PoolSet(int k, int nSlot)
{
    object oPC = GetFirstPC();
    int v = nSlot + 1;
    SetLocalBoolean(oPC, PoolBit(k, 0), (v / 1) % 2);
    SetLocalBoolean(oPC, PoolBit(k, 1), (v / 2) % 2);
    SetLocalBoolean(oPC, PoolBit(k, 2), (v / 4) % 2);
    SetLocalBoolean(oPC, PoolBit(k, 3), (v / 8) % 2);
}

int FollowGen()
{
    return GetLocalNumber(GetFirstPC(), 0);
}

void FollowGenSet(int n)
{
    SetLocalNumber(GetFirstPC(), 0, n);
}

void PoolClear()
{
    int k;
    for (k = 0; k < 4; k++) PoolSet(k, -1);
    FollowGenSet(FollowGen() + 1);
}

// The creature of a slot in the current area; spawned beside the player when it is missing.
object PoolCreature(int s, object oPC)
{
    object o = GetObjectByTag(SlotTag(s));
    if (!GetIsObjectValid(o) && IsAvailableCreature(s))
        o = SpawnAvailableNPC(s, GetLocation(oPC));
    return o;
}

void PoolFollow(object oPC, int nGen)
{
    if (FollowGen() != nGen) return;
    int k;
    for (k = 0; k < 4; k++)
    {
        int s = PoolGet(k);
        if (s >= 0 && !IsNPCPartyMember(s))
        {
            object o = GetObjectByTag(SlotTag(s));
            if (GetIsObjectValid(o))
            {
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
        }
    }
    DelayCommand(3.0, PoolFollow(oPC, nGen));
}

void StartFollow(object oPC)
{
    int g = FollowGen() + 1;
    FollowGenSet(g);
    DelayCommand(3.0, PoolFollow(oPC, g));
}

int PairFirst(int nPair)
{
    if (nPair <= 2) return 0;
    if (nPair <= 4) return 1;
    return 2;
}

int PairSecond(int nPair)
{
    if (nPair == 0) return 1;
    if (nPair == 1 || nPair == 3) return 2;
    return 3;
}

// Makes the pair of pool entries (first, second) the two party followers; the other pool members are created if missing and
// stay beside the player. Works on the creatures that already exist, so nothing is duplicated.
void ApplyPair(int nPair)
{
    object oPC = GetFirstPC();
    int a = PoolGet(PairFirst(nPair));
    int b = PoolGet(PairSecond(nPair));
    if (a < 0 || b < 0) return;
    int k;
    for (k = 0; k < 4; k++)
    {
        int s = PoolGet(k);
        if (s >= 0 && s != a && s != b && IsNPCPartyMember(s)) RemovePartyMember(s);
    }
    for (k = 0; k < 4; k++)
    {
        int s2 = PoolGet(k);
        if (s2 >= 0)
        {
            object o = PoolCreature(s2, oPC);
            if ((s2 == a || s2 == b) && !IsNPCPartyMember(s2) && GetIsObjectValid(o))
            {
                AssignCommand(o, ClearAllActions());
                AddPartyMember(s2, o);
            }
        }
    }
    StartFollow(oPC);
}

// Fills the menu tokens and opens the menu on the player.
void RosterPrompt(object oPC)
{
    string sNow = "";
    int nFound = 0;
    int k;
    for (k = 0; k < 4; k++)
    {
        int s = PoolGet(k);
        if (s >= 0 && IsNPCPartyMember(s))
        {
            if (nFound > 0) sNow = sNow + " and ";
            sNow = sNow + SlotName(s);
            nFound++;
        }
    }
    if (nFound == 0) sNow = "no one";
    SetCustomToken(9210, "Roster. With you now: " + sNow + ". Who should fight beside you?");
    int p;
    for (p = 0; p < 6; p++)
    {
        int a = PoolGet(PairFirst(p));
        int b = PoolGet(PairSecond(p));
        string t = "(not chosen)";
        if (a >= 0 && b >= 0)
        {
            t = SlotName(a) + " and " + SlotName(b);
            if (IsNPCPartyMember(a) && IsNPCPartyMember(b)) t = t + " (current)";
        }
        SetCustomToken(9211 + p, t);
    }
    SetCustomToken(9217, "Keep the party as it is.");
    SetCustomToken(9218, "Change who comes along (two party selection screens).");
    AssignCommand(oPC, ActionStartConversation(oPC, "k2se_roster", FALSE, CONVERSATION_TYPE_CINEMATIC, TRUE));
}
