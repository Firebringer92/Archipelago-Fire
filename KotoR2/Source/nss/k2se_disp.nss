// k2se_disp.nss -- the Archipelago delivery dispatcher (include file).
//
// One job at a time. The client writes the job into %LOCALAPPDATA%\K2SE\ap\inbox.txt:
//     job_seq=<1..255>      job number (wraps after 255 back to 1)
//     job_guard=<1..31>     seed guard: a save belongs to one seed
//     job_action=<name>     notify | credits | xp | item | skill | ability | token | trap | release | gift
//     job_args=<text>       action arguments
//     job_msg=<text>        one line shown to the player after the job is applied (optional)
// The script takes the job when the moment is calm, applies it at most once, writes an acknowledgement to ap\outbox.txt and shows the message.
//
// Once-only rule: the number of the last applied job is kept in 8 player booleans and the seed guard in 5 more, both saved with the game.
// A job fires only if its number is exactly one past the saved number. The saved number is advanced in the same script run that applies the job,
// so a save can never hold "applied" without "counted". Booleans used (see docs/LOCAL_VARIABLE_MAP.md): counter 0,2,3,4,6,7,8,9; guard 11-15.
//
// Outbox lines written here (client reads them):
//     D|<seq>|<action>|<counter>   job applied
//     U|<seq>|<counter>            same job seen again (already applied)
//     S|<seq>|<counter>            job number does not follow the saved number: the client must resend from counter+1
//     G|<seq>|<saved>|<job>        job belongs to another seed
//     W|<seq>|<reason>             job not applied this time (not calm yet is NOT reported; only real refusals)
//     T|<counter>|<guard>          the saved job number and seed guard (sent when either changes, and once per game start)

#include "k2se"
#include "k2se_poll"
#include "k2ap_comp"
#include "k2ap_master"
#include "k2ap_bazaar"
#include "k2ap_craft"
#include "k2ap_vendor"

int DispCounterBit(int i)
{
    if (i == 0) return 0;
    if (i == 1) return 2;
    if (i == 2) return 3;
    if (i == 3) return 4;
    if (i == 4) return 6;
    if (i == 5) return 7;
    if (i == 6) return 8;
    return 9;
}

int DispCounterGet(object oPC)
{
    int n = 0;
    int i;
    for (i = 0; i < 8; i++)
    {
        if (GetLocalBoolean(oPC, DispCounterBit(i)) != 0) n = n | (1 << i);
    }
    return n;
}

void DispCounterSet(object oPC, int n)
{
    int i;
    for (i = 0; i < 8; i++)
    {
        SetLocalBoolean(oPC, DispCounterBit(i), (n >> i) & 1);
    }
}

int DispGuardGet(object oPC)
{
    int n = 0;
    int i;
    for (i = 0; i < 5; i++)
    {
        if (GetLocalBoolean(oPC, 11 + i) != 0) n = n | (1 << i);
    }
    return n;
}

void DispGuardSet(object oPC, int n)
{
    int i;
    for (i = 0; i < 5; i++)
    {
        SetLocalBoolean(oPC, 11 + i, (n >> i) & 1);
    }
}

// True when nothing the player is doing should be interrupted.
int DispCalm(object oPC)
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

// "~~" in a message is a line break (the client joins several lines into one box this way)
string DispLineBreaks(string sMsg)
{
    int nAt = FindSubString(sMsg, "~~");
    while (nAt >= 0)
    {
        sMsg = GetStringLeft(sMsg, nAt) + "\n" + GetSubString(sMsg, nAt + 2, GetStringLength(sMsg));
        nAt = FindSubString(sMsg, "~~");
    }
    return sMsg;
}

void DispMessage(object oPC, string sMsg)
{
    if (sMsg == "") return;
    sMsg = DispLineBreaks(sMsg);
    SetCustomToken(9201, sMsg);
    AssignCommand(oPC, ActionStartConversation(oPC, "k2se_msg", FALSE, CONVERSATION_TYPE_CINEMATIC, TRUE));
}

int DispSkillIndex(string sName)
{
    if (sName == "computer_use") return 0;
    if (sName == "demolitions") return 1;
    if (sName == "stealth") return 2;
    if (sName == "awareness") return 3;
    if (sName == "persuade") return 4;
    if (sName == "repair") return 5;
    if (sName == "security") return 6;
    if (sName == "treat_injury") return 7;
    return -1;
}

int DispAbilityIndex(string sName)
{
    if (sName == "strength") return ABILITY_STRENGTH;
    if (sName == "dexterity") return ABILITY_DEXTERITY;
    if (sName == "constitution") return ABILITY_CONSTITUTION;
    if (sName == "intelligence") return ABILITY_INTELLIGENCE;
    if (sName == "wisdom") return ABILITY_WISDOM;
    if (sName == "charisma") return ABILITY_CHARISMA;
    return -1;
}

// Gate release flags live in player booleans 32-50, in the order of data/gates.json.
int DispGateIndex(string sGate)
{
    string sList = "TEL1 TEL2 TEL3 NAR1 NAR2 NAR3 DXN1 DXN2 DXN3 DAN1 DAN2 DAN3 KOR1 KOR2 KOR3 FIN1 FIN2 FIN3 FIN4";
    int nAt = FindSubString(sList, sGate);
    if (nAt < 0 || GetStringLength(sGate) != 4) return -1;
    return nAt / 5;
}

int DispGateReleased(object oPC, string sGate)
{
    int n = DispGateIndex(sGate);
    if (n < 0) return FALSE;
    return GetLocalBoolean(oPC, 32 + n) != 0;
}

// ---- traps: each is decided here from the character's live state. A trap with nothing to take does nothing and counts as applied.

// One known skill, picked at random from the eight, is halved.
int DispTrapSkill(object oPC)
{
    int nStart = Random(8);
    int i;
    for (i = 0; i < 8; i++)
    {
        int nSkill = (nStart + i) % 8;
        int nRank = K2SE_GetSkillRankBase(oPC, nSkill);
        if (nRank > 0) return K2SE_SetSkillRank(oPC, nSkill, nRank / 2) == 1;
    }
    return TRUE;
}

// The ability score is halved, never below 3.
int DispTrapAbility(object oPC, int nAbility)
{
    int nScore = K2SE_GetAbilityScoreBase(oPC, nAbility);
    if (nScore < 0) return FALSE;
    int nNew = nScore / 2;
    if (nNew < 3) nNew = 3;
    if (nNew >= nScore) return TRUE;
    return K2SE_SetAbilityScoreBase(oPC, nAbility, nNew) == 1;
}

// Maximum health has no field of its own: it comes from the class levels and the constitution bonus. Two points of constitution are one point of bonus,
// worth one health point per level, so the constitution is lowered by as many points as take away about half the maximum (never below 1).
int DispTrapMaxHealth(object oPC)
{
    int nMax = GetMaxHitPoints(oPC);
    int nLevel = GetHitDice(oPC);
    int nCon = K2SE_GetAbilityScoreBase(oPC, ABILITY_CONSTITUTION);
    if (nCon < 0) return FALSE;
    if (nLevel < 1 || nMax < 2) return TRUE;
    int nDrop = ((nMax / 2) / nLevel) * 2;
    if (nDrop > nCon - 1) nDrop = nCon - 1;
    if (nDrop <= 0) return TRUE;
    return K2SE_SetAbilityScoreBase(oPC, ABILITY_CONSTITUTION, nCon - nDrop) == 1;
}

// A random companion who is in the party goes back to the Ebon Hawk (they can be picked again; permanent removal waits for the companion work).
int DispTrapCompanion(object oPC)
{
    int nStart = Random(12);
    int i;
    for (i = 0; i < 12; i++)
    {
        int nSlot = (nStart + i) % 12;
        if (IsNPCPartyMember(nSlot))
        {
            RemoveNPCFromPartyToBase(nSlot);
            return TRUE;
        }
    }
    return TRUE;
}

// Backpack items that the inventory trap may take: not plot items (quest gear, progression tokens) and nothing of ours (tags ap_ and k2se_).
int DispTrapEligible(object oItem)
{
    if (GetPlotFlag(oItem)) return FALSE;
    string sTag = GetTag(oItem);
    if (GetStringLeft(sTag, 3) == "ap_" || GetStringLeft(sTag, 5) == "k2se_") return FALSE;
    return GetLocalBoolean(oItem, 40) == 0;      // 40: already picked by this trap (the destroyed item may still be listed this frame)
}

// Half of the eligible backpack items (a stack counts as one), picked at random. One pass to count and one pass to take: each eligible item is taken with the chance that
// leaves exactly half taken at the end (nTake of the nLeft still to look at). The first version looked through the whole backpack again for every item it took; with a
// big backpack it ran out of instructions before it finished, was not counted as done, and took more of the backpack on every retry.
int DispTrapInventory(object oPC)
{
    int nEligible = 0;
    object oItem = GetFirstItemInInventory(oPC);
    while (GetIsObjectValid(oItem))
    {
        if (DispTrapEligible(oItem)) nEligible++;
        oItem = GetNextItemInInventory(oPC);
    }
    int nTake = nEligible / 2;
    int nLeft = nEligible;
    oItem = GetFirstItemInInventory(oPC);
    while (GetIsObjectValid(oItem) && nTake > 0 && nLeft > 0)
    {
        if (DispTrapEligible(oItem))
        {
            if (Random(nLeft) < nTake)
            {
                SetLocalBoolean(oItem, 40, TRUE);
                DestroyObject(oItem, 0.0, TRUE);
                nTake--;
            }
            nLeft--;
        }
        oItem = GetNextItemInInventory(oPC);
    }
    return TRUE;
}

// DeathLink: the player dies. The poll must not report this death back (dl_incoming, see tools/generate_poll.py).
int DispDeath(object oPC)
{
    if (GetIsDead(oPC)) return TRUE;
    K2SE_MemSet("dl_incoming", "1");
    ApplyEffectToObject(DURATION_TYPE_INSTANT, EffectDeath(), oPC);
    return TRUE;
}

// The n-th number of "a:b:c".
int DispField(string sArgs, int nField)
{
    int i;
    for (i = 0; i < nField; i++)
    {
        int nAt = FindSubString(sArgs, ":");
        if (nAt < 0) return 0;
        sArgs = GetSubString(sArgs, nAt + 1, GetStringLength(sArgs));
    }
    int nEnd = FindSubString(sArgs, ":");
    if (nEnd >= 0) sArgs = GetStringLeft(sArgs, nEnd);
    return StringToInt(sArgs);
}

// The class rebuild (nss/k2se_rb.nss) on the player. args: kind:class:level:position:mode[:race[:look]]  (kind 0 convert the class at that position, 1 add a class,
// 2 resume an interrupted conversion; level 0 = the level the class has now; mode 0 keep, 1 strip the Jedi content). The result code (0 nothing changed,
// 1 changed, 2 partial, 3 bad state, 4 refused) is reported as RB|<args>|<code>; codes 0-2 count as applied.
// The pack k2se_rb takes (nss/k2se_rb.nss RB_Pack) for a class order a:b:...; the level 0 of an order means the level the character has now.
int DispClassPack(object oPC, string sArgs)
{
    int nKind = DispField(sArgs, 0);
    int nClass = DispField(sArgs, 1);
    int nLevel = DispField(sArgs, 2);
    int nPos = DispField(sArgs, 3);
    int nMode = DispField(sArgs, 4);
    if (nLevel == 0) nLevel = GetLevelByPosition(nPos + 1, oPC);
    if (nLevel < 1) return -1;
    return nKind + 4 * nClass + 128 * nLevel + 8192 * nPos + 32768 * nMode + 65536 * 12;
}

// What follows a finished conversion: the droid race, the droid look and the report line.
int DispClassFinish(object oPC, string sArgs)
{
    int nRace = DispField(sArgs, 5);
    int nLook = DispField(sArgs, 6);
    if (nRace > 0) K2SE_SetRace(oPC, nRace);        // 5 = droid: the race write zeroes the maximum Force
    // The player's model is never replaced (that broke the 3D view); a look is a permanent disguise effect, an appearance.2da row such as 66 (Droid_War_01).
    if (nLook > 0 && !K2AP_HasDisguise(oPC)) ApplyEffectToObject(DURATION_TYPE_PERMANENT, EffectDisguise(nLook), oPC);   // the tick puts it back when the game removes it (K2AP_PlayerLookEnforce)
    int nRes = 0;
    if (GetLocalBoolean(oPC, 59) != 0) nRes = nRes + 1;
    if (GetLocalBoolean(oPC, 60) != 0) nRes = nRes + 2;
    if (GetLocalBoolean(oPC, 61) != 0) nRes = nRes + 4;
    K2SE_OutboxPut("RB|" + sArgs + "|" + IntToString(nRes));
    return nRes;
}

// The player's conversion runs in four script runs (K2SE_MemSet("rb_phase") in nss/k2se_rb.nss): one run is allowed too few instructions for all of it (found live 2026-11-18).
// The next phase is scheduled before this one starts, so a phase that is cut short does not stop the rest; each phase writes a line to k2se.log.
void DispClassPhase(object oPC, string sArgs, int nPhase)
{
    if (nPhase < 4) DelayCommand(1.0, DispClassPhase(oPC, sArgs, nPhase + 1));
    int nPack = DispClassPack(oPC, sArgs);
    if (nPack < 0) return;
    K2SE_MemSet("rb_phase", IntToString(nPhase));
    ExecuteScript("k2se_rb", oPC, nPack);
    K2SE_MemSet("rb_phase", "0");
    if (nPhase == 4) DispClassFinish(oPC, sArgs);
}

int DispClassJob(object oPC, string sArgs)
{
    int nKind = DispField(sArgs, 0);
    int nPack = DispClassPack(oPC, sArgs);
    if (nPack < 0) return FALSE;
    if (nKind == 0)
    {
        DelayCommand(0.5, DispClassPhase(oPC, sArgs, 1));   // the rest follows in runs of its own; the job counts as delivered, the report line comes from the last phase
        return TRUE;
    }
    K2SE_MemSet("rb_phase", "0");
    ExecuteScript("k2se_rb", oPC, nPack);
    return DispClassFinish(oPC, sArgs) <= 2;
}

// Starting stats (starting_stats randomized): fourteen numbers a0:...:a13, the six abilities (Strength, Dexterity, Constitution, Intelligence, Wisdom,
// Charisma) and then the eight skills in the order of DispSkillIndex, each written as an absolute value. Reports ST|<number of writes the game refused>.
int DispStats(object oPC, string sArgs)
{
    int nRefused = 0;
    int i;
    for (i = 0; i < 6; i++)
        if (K2SE_SetAbilityScoreBase(oPC, i, DispField(sArgs, i)) != 1) nRefused++;
    for (i = 0; i < 8; i++)
        if (K2SE_SetSkillRank(oPC, i, DispField(sArgs, 6 + i)) != 1) nRefused++;
    K2SE_OutboxPut("ST|" + IntToString(nRefused));
    return nRefused == 0;
}

// The object tag of each story companion's creature, by slot (the templates p_atton ... p_disciple).
string DispCompTag(int nSlot)
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
    if (nSlot >= 12 && nSlot <= 31) return "apxc" + IntToString(nSlot);        // the extra companions: the creature templates the client builds (client/k2_extras.py)
    return "";
}

// A class order for a companion who is in the party (the client works it out from the CC report). args: slot:kind:class:level:mode:race:position  (kind 0 convert
// the class at that position, 1 add a class). Runs the class rebuild on the companion's own creature, with the slot so the companion's protected feats are known.
int DispCompClass(string sArgs)
{
    int nSlot = DispField(sArgs, 0);
    int nKind = DispField(sArgs, 1);
    int nClass = DispField(sArgs, 2);
    int nLevel = DispField(sArgs, 3);
    int nMode = DispField(sArgs, 4);
    int nRace = DispField(sArgs, 5);
    int nPos = DispField(sArgs, 6);
    if (nSlot < 0 || nSlot > 31 || nLevel < 1) return FALSE;
    object oC = PollCompObject(DispCompTag(nSlot));                     // the one in the party when the tag is on two objects (nss/k2se_poll.nss)
    if (!GetIsObjectValid(oC)) return FALSE;
    K2SE_MemSet("rb_phase", "0");
    ExecuteScript("k2se_rb", oC, nKind + 4 * nClass + 128 * nLevel + 8192 * nPos + 32768 * nMode + 65536 * nSlot);
    if (nRace > 0) K2SE_SetRace(oC, nRace);
    int nRes = 0;
    if (GetLocalBoolean(oC, 59) != 0) nRes = nRes + 1;
    if (GetLocalBoolean(oC, 60) != 0) nRes = nRes + 2;
    if (GetLocalBoolean(oC, 61) != 0) nRes = nRes + 4;
    K2SE_OutboxPut("RB|" + sArgs + "|" + IntToString(nRes));
    return nRes <= 2;
}

// An extra companion's item arrived: the creature template apxc<slot> (built into Override when the client patched) is put into its slot and made selectable.
// args: slot:template. Like the story companions, the extra then joins the party only when the player picks them on the party screen.
int DispExtraCompanion(string sArgs)
{
    int nSlot = DispField(sArgs, 0);
    int nAt = FindSubString(sArgs, ":");
    string sTemplate = "";
    if (nAt >= 0) sTemplate = GetSubString(sArgs, nAt + 1, GetStringLength(sArgs));
    if (nSlot < 12 || nSlot > 31 || sTemplate == "") return FALSE;
    if (GetNPCSelectability(nSlot) == -1)
    {
        if (!AddAvailableNPCByTemplate(nSlot, sTemplate)) return FALSE;
    }
    SetNPCSelectability(nSlot, 1);
    return TRUE;
}

// Stages of a family's progress quest (client/k2_journal.py FAMILIES): the most progression items the family can have; 0 for a key that is not a family.
int DispProgressMax(string sFamily)
{
    if (sFamily == "telos" || sFamily == "nar" || sFamily == "dxn" || sFamily == "dan" || sFamily == "kor") return 3;
    if (sFamily == "endgame") return 4;
    return 0;
}

// Applies one job. Returns TRUE if applied (the counter is then advanced by the caller).
int DispApply(object oPC, string sAction, string sArgs)
{
    if (sAction == "notify") return TRUE;
    if (sAction == "credits")
    {
        int nGold = StringToInt(sArgs);
        if (nGold <= 0) return FALSE;
        GiveGoldToCreature(oPC, nGold);
        return TRUE;
    }
    if (sAction == "xp")
    {
        int nXp = StringToInt(sArgs);
        if (nXp <= 0) return FALSE;
        GiveXPToCreature(oPC, nXp);
        return TRUE;
    }
    if (sAction == "set_xp")
    {
        // the experience clamp: the client works out what the seed entitles and sets the total (an absolute value, so a repeat or a replay is harmless)
        int nTotal = StringToInt(sArgs);
        if (nTotal < 0) return FALSE;
        SetXP(oPC, nTotal);
        return TRUE;
    }
    if (sAction == "skill")
    {
        int nSkill = DispSkillIndex(sArgs);
        if (nSkill < 0) return FALSE;
        // the Exile and every companion in the party get the rank together (nss/k2ap_party.nss); the Exile's write decides whether the job counts
        if (!K2AP_RaiseSkill(oPC, nSkill)) return FALSE;
        K2AP_RaisePartyMembers(oPC, 0, nSkill);
        return TRUE;
    }
    if (sAction == "ability")
    {
        int nAbility = DispAbilityIndex(sArgs);
        if (nAbility < 0) return FALSE;
        if (!K2AP_RaiseAbility(oPC, nAbility)) return FALSE;
        K2AP_RaisePartyMembers(oPC, 1, nAbility);
        return TRUE;
    }
    if (sAction == "token")
    {
        // story progression item: moves the family's journal quest (ap_prog_<family>, declared in global.jrl by the client) one stage on; the gate scripts
        // read that stage. A job the older save already had is not sent again (the job number), so one job is one step.
        int nMax = DispProgressMax(sArgs);
        if (nMax <= 0) return FALSE;
        string sTag = "ap_prog_" + sArgs;
        int nNow = GetJournalEntry(sTag);
        if (nNow < 0) nNow = 0;
        if (nNow >= nMax) return FALSE;                           // every item of the family is counted already: refused, the number still advances
        AddJournalQuestEntry(sTag, nNow + 1, FALSE);
        return GetJournalEntry(sTag) == nNow + 1;                 // FALSE when the quest is not declared (no global.jrl of ours in Override)
    }
    if (sAction == "tracker")
    {
        // the Archipelago Tracker quest: the stage is the percent of the run's checks that are done (1, 20, 40, 60, 80, 100); it only moves forward
        int nStage = StringToInt(sArgs);
        if (nStage != 1 && nStage != 20 && nStage != 40 && nStage != 60 && nStage != 80 && nStage != 100) return FALSE;
        AddJournalQuestEntry("ap_tracker", nStage, FALSE);
        return GetJournalEntry("ap_tracker") >= nStage;
    }
    if (sAction == "pass")
    {
        // a pass of the Archipelago Vendor: a plot item (ap_vp_<key>) that shows the menu of that name
        object oPass = CreateItemOnObject("ap_vp_" + sArgs, oPC, 1, 1);
        return GetIsObjectValid(oPass);
    }
    if (sAction == "gear")
    {
        // a piece of gear from the item pool (crafting mode off): the item itself, by template name
        object oGear = CreateItemOnObject(sArgs, oPC, 1);
        return GetIsObjectValid(oGear);
    }
    if (sAction == "gift")
    {
        // AP Companion Gifts (nss/k2ap_gift.nss): a stack of the item the client's patch put into Override
        int nGifts = StringToInt(sArgs);
        if (nGifts < 1) return FALSE;
        CreateItemOnObject("ap_gift", oPC, nGifts, 1);
        return TRUE;
    }
    if (sAction == "partycon")
    {
        // the Party Console (item ap_partycon, nss/k_ptat_sandper.nss): one, never used up; a repeated job leaves the one the player has
        if (GetIsObjectValid(GetItemPossessedBy(oPC, "ap_partycon"))) return TRUE;
        object oConsole = CreateItemOnObject("ap_partycon", oPC, 1, 1);
        return GetIsObjectValid(oConsole);
    }
    if (sAction == "materials")
    {
        // crafting mode: Components for a gear item (the item compont_00001 turns into the bench counter, one per unit of the stack)
        int nMaterials = StringToInt(sArgs);
        if (nMaterials <= 0) return FALSE;
        object oMaterials = CreateItemOnObject("compont_00001", oPC, nMaterials);
        return GetIsObjectValid(oMaterials);
    }
    if (sAction == "trap")
    {
        if (sArgs == "credits")
        {
            K2SE_SetPartyCredits(GetGold(oPC) - GetGold(oPC) / 10);
            return TRUE;
        }
        if (sArgs == "dark") { AdjustAlignment(oPC, ALIGNMENT_DARK_SIDE, 10); return TRUE; }
        if (sArgs == "light") { AdjustAlignment(oPC, ALIGNMENT_LIGHT_SIDE, 10); return TRUE; }
        if (sArgs == "influence")
        {
            int nStart = Random(12);
            int i;
            for (i = 0; i < 12; i++)
            {
                int nSlot = (nStart + i) % 12;
                if (IsAvailableCreature(nSlot)) { ModifyInfluence(nSlot, -8); return TRUE; }
            }
            return FALSE;
        }
        if (sArgs == "skill") return DispTrapSkill(oPC);
        if (sArgs == "max_health") return DispTrapMaxHealth(oPC);
        if (sArgs == "companion") return DispTrapCompanion(oPC);
        if (sArgs == "inventory") return DispTrapInventory(oPC);
        if (GetStringLeft(sArgs, 6) == "halve_")
        {
            int nAbility = DispAbilityIndex(GetSubString(sArgs, 6, GetStringLength(sArgs)));
            if (nAbility < 0) return FALSE;
            return DispTrapAbility(oPC, nAbility);
        }
        return FALSE;
    }
    if (sAction == "death") return DispDeath(oPC);
    if (sAction == "class") return DispClassJob(oPC, sArgs);
    if (sAction == "stats") return DispStats(oPC, sArgs);
    if (sAction == "compclass") return DispCompClass(sArgs);
    if (sAction == "extracompanion") return DispExtraCompanion(sArgs);
    if (sAction == "companion") return K2AP_CompUnlock(oPC, StringToInt(sArgs));       // args: the slot 0-11 of the companion whose item arrived
    if (sAction == "prestige")
    {
        // args lightClass:darkClass. The side comes from the player's alignment when the item arrives (exactly 50: a random side); the prestige class is
        // added as a further class with one level (the Level Up screen takes it on from there).
        int nAlign = GetGoodEvilValue(oPC);
        int nPrestige = DispField(sArgs, 0);
        if (nAlign < 50 || (nAlign == 50 && Random(2) == 1)) nPrestige = DispField(sArgs, 1);
        return DispClassJob(oPC, "1:" + IntToString(nPrestige) + ":1:0:0");
    }
    if (sAction == "release")
    {
        int nGate = DispGateIndex(sArgs);
        if (nGate < 0) return FALSE;
        SetLocalBoolean(oPC, 32 + nGate, TRUE);
        return TRUE;
    }
    if (sAction == "item")
    {
        // args: resref or resref:count
        string sRef = sArgs;
        int nCount = 1;
        int nColon = FindSubString(sArgs, ":");
        if (nColon > 0)
        {
            sRef = GetStringLeft(sArgs, nColon);
            nCount = StringToInt(GetSubString(sArgs, nColon + 1, GetStringLength(sArgs)));
            if (nCount < 1) nCount = 1;
        }
        object oItem = CreateItemOnObject(sRef, oPC, nCount, 1);
        return GetIsObjectValid(oItem);
    }
    return FALSE;
}

// Reports a refusal-type state once, not on every poll: the same (kind, seq, counter) is written to the outbox a single time.
void DispReportOnce(string sKind, int nSeq, int nCounter, string sLine)
{
    string sKey = sKind + IntToString(nSeq) + "/" + IntToString(nCounter);
    if (K2SE_MemGet("disp_last") == sKey) return;
    K2SE_MemSet("disp_last", sKey);
    K2SE_OutboxPut(sLine);
}

// Tells the client the saved job number and seed guard whenever either changed (and once per game start). The client needs it to number its jobs
// and to notice that an older save was loaded.
void DispReportState(object oPC)
{
    string sKey = IntToString(DispCounterGet(oPC)) + "/" + IntToString(DispGuardGet(oPC));
    if (K2SE_MemGet("disp_state") == sKey) return;
    K2SE_MemSet("disp_state", sKey);
    K2SE_OutboxPut("T|" + IntToString(DispCounterGet(oPC)) + "|" + IntToString(DispGuardGet(oPC)));
}

// One poll. Takes at most one job.
void DispPollOnce()
{
    object oPC = GetFirstPC();
    if (!GetIsObjectValid(oPC)) return;
    DispReportState(oPC);
    PollAll(oPC);
    int nSeq = K2SE_InboxInt("job_seq", 0);
    if (nSeq <= 0) return;

    int nJobGuard = K2SE_InboxInt("job_guard", 0);
    int nSavedGuard = DispGuardGet(oPC);
    int nCounter = DispCounterGet(oPC);

    if (nSavedGuard != 0 && nJobGuard != nSavedGuard)
    {
        DispReportOnce("G", nSeq, nCounter, "G|" + IntToString(nSeq) + "|" + IntToString(nSavedGuard) + "|" + IntToString(nJobGuard));
        return;
    }
    if (nSeq == nCounter)
    {
        DispReportOnce("U", nSeq, nCounter, "U|" + IntToString(nSeq) + "|" + IntToString(nCounter));
        return;
    }
    int nNext = (nCounter % 255) + 1;   // 1..255, then back to 1
    if (nSeq != nNext)
    {
        DispReportOnce("S", nSeq, nCounter, "S|" + IntToString(nSeq) + "|" + IntToString(nCounter));
        return;
    }
    if (!DispCalm(oPC)) return;

    string sAction = K2SE_InboxStr("job_action");
    string sArgs = K2SE_InboxStr("job_args");
    string sMsg = K2SE_InboxStr("job_msg");
    // A job that destroys items is counted BEFORE it runs: a script that is cut short must never be run again (every run takes more). At most once beats exactly once.
    if (sAction == "trap" && sArgs == "inventory")
    {
        if (nSavedGuard == 0 && nJobGuard > 0) DispGuardSet(oPC, nJobGuard);
        DispCounterSet(oPC, nSeq);
    }
    // A job whose script is cut short (too many instructions, say) never reaches the lines below, so the same job is tried again at the next poll, for ever, and nothing behind
    // it is delivered. Three tries per job and game session; then it is given up, reported, and the queue moves on.
    string sTry = K2SE_MemGet("disp_try");
    int nTries = 1;
    if (GetStringLeft(sTry, GetStringLength(IntToString(nSeq)) + 1) == IntToString(nSeq) + ":")
        nTries = StringToInt(GetSubString(sTry, GetStringLength(IntToString(nSeq)) + 1, 4)) + 1;
    K2SE_MemSet("disp_try", IntToString(nSeq) + ":" + IntToString(nTries));
    if (nTries > 3)
    {
        K2SE_OutboxPut("W|" + IntToString(nSeq) + "|gave up " + sAction + " after 3 tries");
        if (nSavedGuard == 0 && nJobGuard > 0) DispGuardSet(oPC, nJobGuard);
        DispCounterSet(oPC, nSeq);
        K2SE_OutboxPut("D|" + IntToString(nSeq) + "|" + sAction + "|" + IntToString(nSeq));
        return;
    }
    if (!DispApply(oPC, sAction, sArgs))
    {
        K2SE_OutboxPut("W|" + IntToString(nSeq) + "|refused " + sAction);
        // advance anyway so one bad job cannot block the queue forever
    }
    if (nSavedGuard == 0 && nJobGuard > 0) DispGuardSet(oPC, nJobGuard);
    DispCounterSet(oPC, nSeq);
    K2SE_OutboxPut("D|" + IntToString(nSeq) + "|" + sAction + "|" + IntToString(nSeq));
    DispMessage(oPC, sMsg);
}

// The poll loop. A new loop gets a new generation number; an older loop notices it is stale and stops.
// (A Load Game or a module change silently ends the chains that were running, so each area entry starts a new one.)
void DispTick(int nGen)
{
    if (K2SE_MemGet("disp_gen") != IntToString(nGen)) return;
    object oPC = GetFirstPC();
    // In the first moments of an area (after a load, or the skipped prologue) the player object can exist before its creature does. GetHitDice then reads 0,
    // and routines such as GetGoodEvilValue read a null creature and crash the game (found live: 101PER after skipping the prologue). Wait until the player is real.
    if (!GetIsObjectValid(oPC) || GetHitDice(oPC) < 1)
    {
        DelayCommand(1.0, DispTick(nGen));
        return;
    }
    // While the player controls a companion's body (the Dxun jungle tomb, the yacht, the Mira and Atton switches) GetFirstPC() is that companion, not the Exile.
    // The job number, the seed guard and the companion unlock set live on the Exile, so that body shows its own old numbers: the client would take them for a
    // loaded older save and send every job since then again, onto the wrong body. Nothing is read, reported or delivered until the Exile is back; the jobs wait
    // in the inbox. The Exile's own tag is empty, so any other tag is a played companion (the same test as nss/k2ap_comp.nss).
    if (GetTag(oPC) != "")
    {
        DelayCommand(1.0, DispTick(nGen));
        return;
    }
    // The next poll is scheduled first: a poll whose script is cut short (too many instructions) must not end the loop, or the same job would wait for ever.
    AssignCommand(oPC, DelayCommand(K2SE_ConfigInt("disp_period", 3) + 0.0, DispTick(nGen)));
    DispPollOnce();
    // companions whose item has not arrived are kept hidden (nss/k2ap_comp.nss); only at calm moments, so a scene that needs them in the party is not cut
    if (GetIsObjectValid(oPC) && DispCalm(oPC)) K2AP_CompEnforce(oPC);
    if (GetIsObjectValid(oPC) && DispCalm(oPC)) K2AP_LookEnforce();
    if (GetIsObjectValid(oPC) && DispCalm(oPC)) K2AP_PlayerLookEnforce(oPC);
    if (GetIsObjectValid(oPC) && DispCalm(oPC)) K2AP_CompLookEnforce();
    if (GetIsObjectValid(oPC) && DispCalm(oPC) && K2AP_Patched() != 0) K2AP_DroidHideEnforce();    if (GetIsObjectValid(oPC) && DispCalm(oPC)) K2AP_BazaarEnsure(oPC);
    if (GetIsObjectValid(oPC) && DispCalm(oPC)) K2AP_CraftEnsure(oPC);
    if (GetIsObjectValid(oPC) && DispCalm(oPC)) K2AP_VendorEnsure(oPC);
    // a Master's +1 on the Jedi count that waited for its token is applied once the gate is open (nss/k2ap_master.nss)
    if (GetIsObjectValid(oPC) && K2AP_Patched() != 0) K2AP_MasterCatchUp(oPC);
}

void DispStart()
{
    int nGen = StringToInt(K2SE_MemGet("disp_gen")) + 1;
    K2SE_MemSet("disp_gen", IntToString(nGen));
    K2SE_Diag("DISP", "dispatcher loop " + IntToString(nGen) + " started");
    K2SE_OutboxPut("V|" + GetStringUpperCase(GetModuleName()));
    // The first poll runs a moment later, in a script run of its own. Run inline it shares the instruction budget of the area entry script (the game's own script, our hooks and
    // the poll), and a class rebuild started by the first job ran out of it: the conversion stopped half way, the job was never acknowledged and nothing else was delivered
    // (found live 2026-11-18, the first droid start). Every later poll already runs from a DelayCommand.
    DelayCommand(1.0, DispTick(nGen));
}
