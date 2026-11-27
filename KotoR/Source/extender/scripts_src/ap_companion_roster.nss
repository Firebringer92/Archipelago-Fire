// Companion roster rules (0.2.1): a companion the player is not entitled to yet is BENCHED, never deleted.
//
// Before 0.2.1 every vanilla recruit was undone with RemoveAvailableNPC, so the companion stopped existing for the game's own scripts and
// the scenes that expect them (the Hideout, the Council, the Zaalbar and Mission scenes, the Unknown World finale) needed workarounds.
// Now the roster entry stays: the companion is AVAILABLE (IsAvailableCreature is true, the game's scripts find them), but out of the party and
// NOT SELECTABLE on the party screen, exactly like Zaalbar during the Kashyyyk story (k_pkas_meetking: RemovePartyMember + SetNPCSelectability
// FALSE, never RemoveAvailableNPC). The creature object stays where it stands. When the AP item arrives the companion is made selectable and
// put in the party; if the party already holds two companions, the one in the second companion slot leaves it.
//
// Who is entitled: the journal marker ap_ent_<key> (build_ap_tracker_quest.py), 10 up to 19 = entitled, 20 = trapped off, 0 = never granted.
//
// #include this (never compiled or run on its own) from the recruit wrappers and from the poll.
#include "kse"

// The key of a companion (also the end of its ap_ent_ marker), by NPC index; "" for anything else.
string ApNpcKey(int nNPC)
{
    if (nNPC == NPC_BASTILA) return "bastila";
    if (nNPC == NPC_CANDEROUS) return "canderous";
    if (nNPC == NPC_CARTH) return "carth";
    if (nNPC == NPC_HK_47) return "hk47";
    if (nNPC == NPC_JOLEE) return "jolee";
    if (nNPC == NPC_JUHANI) return "juhani";
    if (nNPC == NPC_MISSION) return "mission";
    if (nNPC == NPC_T3_M4) return "t3m4";
    if (nNPC == NPC_ZAALBAR) return "zaalbar";
    return "";
}

// The tag of the companion's creature object, by NPC index.
string ApNpcTag(int nNPC)
{
    if (nNPC == NPC_BASTILA) return "Bastila";
    if (nNPC == NPC_CANDEROUS) return "Cand";
    if (nNPC == NPC_CARTH) return "Carth";
    if (nNPC == NPC_HK_47) return "HK47";
    if (nNPC == NPC_JOLEE) return "Jolee";
    if (nNPC == NPC_JUHANI) return "Juhani";
    if (nNPC == NPC_MISSION) return "Mission";
    if (nNPC == NPC_T3_M4) return "t3m4";
    if (nNPC == NPC_ZAALBAR) return "Zaalbar";
    return "";
}

// The NPC index of a creature by its tag (case does not matter); -1 when it is not one of the nine.
int ApNpcFromCreature(object oCreature)
{
    string sTag = GetStringLowerCase(GetTag(oCreature));
    if (sTag == "bastila") return NPC_BASTILA;
    if (sTag == "cand") return NPC_CANDEROUS;
    if (sTag == "carth") return NPC_CARTH;
    if (sTag == "hk47") return NPC_HK_47;
    if (sTag == "jolee") return NPC_JOLEE;
    if (sTag == "juhani") return NPC_JUHANI;
    if (sTag == "mission") return NPC_MISSION;
    if (sTag == "t3m4") return NPC_T3_M4;
    if (sTag == "zaalbar") return NPC_ZAALBAR;
    return -1;
}

// TRUE when the player is entitled to this companion (the AP item was received, or the auto-grant of the normal mode ran) and no trap removed them.
int ApNpcEntitled(int nNPC)
{
    string sKey = ApNpcKey(nNPC);
    if (sKey == "") return FALSE;
    int nMarker = GetJournalEntry("ap_ent_" + sKey);
    if (nMarker >= 10 && nMarker < 20) return TRUE;
    return FALSE;
}

// Modules where the game scripts the party itself (the Endar Spire prologue, where slot 0 belongs to Trask, the Leviathan, the Unknown World,
// the Star Forge, the cutscene modules): the roster is left alone there and nobody is put into or taken out of the party by the AP code.
int ApPartyScripted()
{
    string sMod = GetStringLowerCase(GetModuleFileName());
    if (GetStringLeft(sMod, 7) == "end_m01") return TRUE;
    if (GetStringLeft(sMod, 7) == "lev_m40") return TRUE;
    if (GetStringLeft(sMod, 7) == "unk_m44") return TRUE;
    if (GetStringLeft(sMod, 7) == "sta_m45") return TRUE;
    if (GetStringLeft(sMod, 5) == "stunt") return TRUE;
    if (sMod == "unk_m41ad") return TRUE;
    return FALSE;
}

// Benches a companion: out of the party and not selectable. The roster entry, the availability and the creature object stay. Safe to call any time,
// for any companion, even one who is not on the roster.
void ApBenchNpc(int nNPC)
{
    if (IsNPCPartyMember(nNPC)) RemovePartyMember(nNPC);
    if (GetNPCSelectability(nNPC)) SetNPCSelectability(nNPC, FALSE);
}

// Makes room for one more companion: the party holds the player and two companions. With two companions already in, the one in the second
// companion slot (party index 2) leaves the party (never the player, never the first companion). Returns TRUE when there is room.
int ApMakeRoomInParty()
{
    if (GetPartyMemberCount() < 3) return TRUE;
    object oSecond = GetPartyMemberByIndex(2);
    if (!GetIsObjectValid(oSecond)) return TRUE;
    int nSecond = ApNpcFromCreature(oSecond);
    if (nSecond < 0) return FALSE;      // not one of the nine (an extra or AP companion): left alone, no swap
    RemovePartyMember(nSecond);
    return TRUE;
}

// The grant: the companion becomes available, selectable and a party member. Returns TRUE when they were added to the party now.
// The creature that already stands in this area is used when there is one (a benched companion left where they were recruited), a new one is
// made at the player otherwise.
int ApGrantNpc(int nNPC, string sTemplate)
{
    if (!IsAvailableCreature(nNPC)) AddAvailableNPCByTemplate(nNPC, sTemplate);
    SetNPCSelectability(nNPC, TRUE);
    if (IsNPCPartyMember(nNPC)) return FALSE;
    if (ApPartyScripted()) return FALSE;
    if (!ApMakeRoomInParty()) return FALSE;
    object oPC = GetFirstPC();
    object oNPC = GetObjectByTag(ApNpcTag(nNPC));
    if (!GetIsObjectValid(oNPC)) oNPC = CreateObject(OBJECT_TYPE_CREATURE, sTemplate, GetLocation(oPC));
    return AddPartyMember(nNPC, oNPC);
}

// A roster companion is not meant to be hostile outside the scripted modules, but an area-wide betrayal script of the game (the Sith Academy turning
// on the player moves every creature of the friendly and neutral factions to the hostile one) can catch one, and the save keeps them hostile.
// Such a companion standing in the player's area is made friendly again.
void ApRepairHostileCompanions()
{
    object oArea = GetArea(GetFirstPC());
    object oCreature = GetFirstObjectInArea(oArea, OBJECT_TYPE_CREATURE);
    while (GetIsObjectValid(oCreature))
    {
        int nNPC = ApNpcFromCreature(oCreature);
        if (nNPC >= 0 && IsAvailableCreature(nNPC))
        {
            int nFaction = GetStandardFaction(oCreature);
            if (nFaction == STANDARD_FACTION_HOSTILE_1 || nFaction == STANDARD_FACTION_HOSTILE_2)
            {
                ChangeToStandardFaction(oCreature, STANDARD_FACTION_FRIENDLY_1);
                AssignCommand(oCreature, ClearAllActions());
                CancelCombat(oCreature);
                SaveNPCState(nNPC);
                KSE_Diag(176, "AP|FACTIONFIX|" + ApNpcKey(nNPC) + "|was=" + IntToString(nFaction));
            }
        }
        oCreature = GetNextObjectInArea(oArea, OBJECT_TYPE_CREATURE);
    }
}

// One enforcement pass: every companion on the roster the player is not entitled to is benched (a vanilla scene or conversation may have put them
// back into the party or made them selectable). Entitled companions are left alone. A companion turned hostile is repaired. Skipped where the game
// scripts the party.
void ApEnforceRoster()
{
    if (ApPartyScripted()) return;
    ApRepairHostileCompanions();
    int nNPC = 0;
    while (nNPC <= 8)
    {
        if (IsAvailableCreature(nNPC))
        {
            if (!ApNpcEntitled(nNPC))
            {
                if (IsNPCPartyMember(nNPC) || GetNPCSelectability(nNPC))
                {
                    ApBenchNpc(nNPC);
                    KSE_Diag(176, "AP|BENCHED|" + ApNpcKey(nNPC));
                }
            }
        }
        nNPC = nNPC + 1;
    }
    // A stock companion standing in the party whom the roster does not list (a trap or a scene edited the roster, or an old save): the roster loop above never
    // sees them, so the party slots are checked too. RemovePartyMember takes them out; nothing else is touched.
    int nSlot = 1;
    while (nSlot <= 2)
    {
        object oMember = GetPartyMemberByIndex(nSlot);
        if (GetIsObjectValid(oMember))
        {
            int nMemberNPC = ApNpcFromCreature(oMember);
            if (nMemberNPC >= 0 && !ApNpcEntitled(nMemberNPC))
            {
                RemovePartyMember(nMemberNPC);
                KSE_Diag(176, "AP|BENCHED|" + ApNpcKey(nMemberNPC) + "|not_on_roster");
            }
        }
        nSlot = nSlot + 1;
    }
}
