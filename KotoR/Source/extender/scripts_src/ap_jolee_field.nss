// Shared helpers for the Kashyyyk repulsor-field fix -- #include this (never
// compiled/run standalone) from k_pkas_talkwall.nss (stages Jolee) and from
// ap_poll_shared (CheckJoleeFieldRevert, takes him away again).
//
// Why this exists: the Czerka repulsor field that blocks the way into the
// Lower Shadowlands (dialogue kas24_force_01, on the placeable kas24_fieldspeak
// in kas_m24aa) only opens when Jolee is in the ACTIVE party -- its reply
// conditions (k_pkas_joleeopen/joleepc/jolonship/joleenopc) all test
// IsNPCPartyMember(NPC_JOLEE), the branch without him is a dead end ("If he
// were here, he would allow you to pass"), and the passage itself is the
// StartNewModule in k_pkas_move25aa at the end of that dialogue. That is the
// main Kashyyyk plot (Chuundar's task, Freyyr) and the Kashyyyk Star Map. Under
// companion_mode=ap_gated Jolee isn't recruited until his AP item arrives, and
// under companion_mode=none he never is, so without this the planet is
// uncompletable.
//
// What it does: when the field's dialogue starts and Jolee has not been
// recruited at all (not available), seat him for the conversation exactly like
// the Mission staging for Zaalbar (ap_zaal_mission.nss): make him available,
// put a p_jolee in the party, bench the slot-2 companion first if the active
// party is full. A recruited Jolee (available but not in the party) is left to
// the vanilla behaviour. He is taken away by CheckJoleeFieldRevert() from the
// poll rather than a DelayCommand, because the dialogue ends by loading another
// module and a DelayCommand does not survive that.
//
// State: KSE data (in-DLL memory) plus a local boolean on the PC (index 78,
// unused elsewhere in this project) so a save made while he is seated still
// reverts after a reload.
#include "kse"

int GetJoleeFieldNPCIndex(object oCompanion)
{
    string sTag = GetStringLowerCase(GetTag(oCompanion));
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

// Time is counted in heartbeat ticks (5 s each), not the in-game clock, which
// jumps (it has been seen to go back by minutes on a module load).
int JoleeFieldClock()
{
    int nTick = 0;
    if (KSE_HasData("hb_tick_num")) nTick = StringToInt(KSE_GetData("hb_tick_num"));
    return nTick;
}

int JoleeFieldSecondsSince(int nThen)
{
    int nElapsed = JoleeFieldClock() - nThen;
    if (nElapsed < 0) nElapsed = 0;
    return nElapsed * 5;
}

void StageJoleeForField()
{
    // Recruited (even if benched): vanilla behaviour. Already seated: nothing to do.
    if (IsAvailableCreature(NPC_JOLEE)) return;
    if (IsNPCPartyMember(NPC_JOLEE)) return;

    object oPC = GetFirstPC();
    int nBenchedNPC = -1;
    string sBenchedTag = "";
    if (GetPartyMemberCount() >= 3)
    {
        object oSlot2 = GetPartyMemberByIndex(2);
        if (GetIsObjectValid(oSlot2))
        {
            int nCandidate = GetJoleeFieldNPCIndex(oSlot2);
            if (nCandidate != -1)
            {
                nBenchedNPC = nCandidate;
                sBenchedTag = GetTag(oSlot2);
                RemovePartyMember(nBenchedNPC);
            }
        }
    }

    // Reuse a Jolee already standing in this module rather than creating a
    // second one with the same tag.
    object oJolee = GetObjectByTag("jolee");
    if (!GetIsObjectValid(oJolee))
    {
        oJolee = CreateObject(OBJECT_TYPE_CREATURE, "p_jolee", GetLocation(oPC));
    }
    AddAvailableNPCByTemplate(NPC_JOLEE, "p_jolee");
    AddPartyMember(NPC_JOLEE, oJolee);

    KSE_SetData("jolee_field_staged", "1");
    KSE_SetData("jolee_field_time", IntToString(JoleeFieldClock()));
    KSE_SetData("jolee_field_area", GetTag(GetArea(oPC)));
    KSE_SetData("jolee_field_left", "0");
    KSE_SetData("jolee_benched_npc", IntToString(nBenchedNPC));
    KSE_SetData("jolee_benched_tag", sBenchedTag);
    SetLocalBoolean(oPC, 78, TRUE);
    KSE_Diag(176, "AP|SAFEGUARD|kas_repulsor_field|staged|benched=" + IntToString(nBenchedNPC));
}

// Idempotent: safe to call whenever.
void RevertJoleeField()
{
    object oPC = GetFirstPC();
    KSE_SetData("jolee_field_staged", "0");
    SetLocalBoolean(oPC, 78, FALSE);

    RemovePartyMember(NPC_JOLEE);
    RemoveAvailableNPC(NPC_JOLEE);
    // RemovePartyMember/RemoveAvailableNPC only edit the roster; the creature
    // object keeps standing and could be walked up to and re-recruited.
    int nStray = 0;
    object oStray = GetObjectByTag("jolee", nStray);
    while (GetIsObjectValid(oStray))
    {
        DestroyObject(oStray);
        nStray++;
        oStray = GetObjectByTag("jolee", nStray);
    }

    int nBenchedNPC = -1;
    if (KSE_HasData("jolee_benched_npc")) nBenchedNPC = StringToInt(KSE_GetData("jolee_benched_npc"));
    if (nBenchedNPC != -1)
    {
        object oBenched = GetObjectByTag(KSE_GetData("jolee_benched_tag"));
        if (GetIsObjectValid(oBenched))
        {
            AddPartyMember(nBenchedNPC, oBenched);
        }
        KSE_SetData("jolee_benched_npc", "-1");
    }
    KSE_Diag(176, "AP|SAFEGUARD|kas_repulsor_field|reverted");
}

// Called from every poll. Waits out the dialogue (GetIsInConversation), and
// once the party has changed module (the dialogue's last step) gives the new
// area 10 seconds to finish loading before touching the party.
void CheckJoleeFieldRevert()
{
    object oPC = GetFirstPC();
    if (!GetIsObjectValid(oPC)) return;
    int bStaged = GetLocalBoolean(oPC, 78);
    if (KSE_HasData("jolee_field_staged") && KSE_GetData("jolee_field_staged") == "1") bStaged = TRUE;
    if (!bStaged) return;
    if (GetIsInConversation(oPC)) return;

    int nSince = 0;
    if (KSE_HasData("jolee_field_time")) nSince = StringToInt(KSE_GetData("jolee_field_time"));
    string sStageArea = "";
    if (KSE_HasData("jolee_field_area")) sStageArea = KSE_GetData("jolee_field_area");

    if (sStageArea != "" && GetTag(GetArea(oPC)) != sStageArea)
    {
        // Left the area the field is in (through the dialogue's own module change).
        int nLeft = 0;
        if (KSE_HasData("jolee_field_left")) nLeft = StringToInt(KSE_GetData("jolee_field_left"));
        if (nLeft == 0)
        {
            KSE_SetData("jolee_field_left", IntToString(JoleeFieldClock() + 1));
            return;
        }
        if (JoleeFieldSecondsSince(nLeft - 1) < 10) return;
        RevertJoleeField();
        return;
    }
    // Still in the same area (dialogue abandoned, or it ended without leaving).
    if (JoleeFieldSecondsSince(nSince) < 15) return;
    RevertJoleeField();
}
