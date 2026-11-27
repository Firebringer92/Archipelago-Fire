// Companion fights: a follower the player is not controlling does not start a fight. Once the party is fighting (the leader is in combat or is attacking
// an enemy, or an enemy it can see is attacking a party member) it fights as in the game, and one left idle is sent into the fight. Orders given by
// the player are not affected, and neither is anyone who is not a follower (the leader, NPCs using these scripts).
//
// The k_hen_* companion event scripts that could start a fight include this and hand each event to the game's AI script k_ai_master, which does the
// actual fighting. Being attacked or damaged is already a fight, so those two events are left to the game. #include this (never compiled or run on
// its own).

// TRUE when the party has a fight to join.
int ApHenPartyFighting()
{
    object oLeader = GetPartyMemberByIndex(0);
    if (GetIsInCombat(oLeader)) return TRUE;
    object oTarget = GetAttackTarget(oLeader);
    if (GetIsObjectValid(oTarget))
    {
        if (!GetIsDead(oTarget) && GetIsEnemy(oTarget, oLeader)) return TRUE;
    }
    int n = 1;
    object oEnemy = GetNearestCreature(CREATURE_TYPE_REPUTATION, REPUTATION_TYPE_ENEMY, OBJECT_SELF, n, CREATURE_TYPE_PERCEPTION, PERCEPTION_SEEN);
    while (GetIsObjectValid(oEnemy) && n <= 20)
    {
        if (!GetIsDead(oEnemy))
        {
            if (IsObjectPartyMember(GetAttackTarget(oEnemy))) return TRUE;
        }
        n = n + 1;
        oEnemy = GetNearestCreature(CREATURE_TYPE_REPUTATION, REPUTATION_TYPE_ENEMY, OBJECT_SELF, n, CREATURE_TYPE_PERCEPTION, PERCEPTION_SEEN);
    }
    return FALSE;
}

// The enemy an idle follower is sent at: the leader's target, else the nearest living enemy it can see. OBJECT_INVALID when there is neither.
object ApHenFightTarget()
{
    object oLeader = GetPartyMemberByIndex(0);
    object oTarget = GetAttackTarget(oLeader);
    if (GetIsObjectValid(oTarget))
    {
        if (!GetIsDead(oTarget) && GetIsEnemy(oTarget)) return oTarget;
    }
    int n = 1;
    object oEnemy = GetNearestCreature(CREATURE_TYPE_REPUTATION, REPUTATION_TYPE_ENEMY, OBJECT_SELF, n, CREATURE_TYPE_PERCEPTION, PERCEPTION_SEEN);
    while (GetIsObjectValid(oEnemy) && n <= 20)
    {
        if (!GetIsDead(oEnemy)) return oEnemy;
        n = n + 1;
        oEnemy = GetNearestCreature(CREATURE_TYPE_REPUTATION, REPUTATION_TYPE_ENEMY, OBJECT_SELF, n, CREATURE_TYPE_PERCEPTION, PERCEPTION_SEEN);
    }
    return OBJECT_INVALID;
}

// TRUE when the rule applies right now: a follower acting on its own.
int ApHenLimited()
{
    if (!IsObjectPartyMember(OBJECT_SELF)) return FALSE;
    if (GetPartyMemberByIndex(0) == OBJECT_SELF) return FALSE;
    if (GetPlayerRestrictMode()) return FALSE;
    if (GetUserActionsPending()) return FALSE;
    return TRUE;
}

// A held follower with nothing to do goes back to the leader (the game would leave it standing while it can see any enemy). An attack on a living
// target is left running, so a player's order is carried out.
void ApHenRegroup()
{
    if (GetSoloMode() || GetIsConversationActive() || !GetCommandable()) return;
    object oTarget = GetAttackTarget();
    if (GetIsObjectValid(oTarget) && !GetIsDead(oTarget)) return;
    if (GetCurrentAction(OBJECT_SELF) != ACTION_QUEUEEMPTY) return;
    CancelCombat(OBJECT_SELF);
    ClearAllActions();
    ActionFollowLeader();
}

// Run on the heartbeat: no event need wake a follower when the leader starts on an enemy it already saw, so a follower with no fight of its own is
// sent into the party's fight. With no fight to join it goes back to the leader.
void ApHenIdle()
{
    if (!ApHenPartyFighting())
    {
        ApHenRegroup();
        return;
    }
    if (GetSoloMode() || GetIsConversationActive() || !GetCommandable()) return;
    if (GetPartyAIStyle() == PARTY_AISTYLE_PASSIVE) return;
    object oTarget = GetAttackTarget();
    if (GetIsObjectValid(oTarget) && !GetIsDead(oTarget)) return;
    int nAction = GetCurrentAction(OBJECT_SELF);
    if (nAction != ACTION_QUEUEEMPTY && nAction != ACTION_FOLLOWLEADER) return;
    object oEnemy = ApHenFightTarget();
    if (!GetIsObjectValid(oEnemy)) return;
    ClearAllActions();
    ActionAttack(oEnemy);
}

// For an event that can start a fight.
void ApHenCombatEvent(int nEvent)
{
    if (ApHenLimited() && !ApHenPartyFighting())
    {
        ApHenRegroup();
        return;
    }
    ExecuteScript("k_ai_master", OBJECT_SELF, nEvent);
}
