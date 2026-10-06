// Shared helpers for the Zaalbar-recruit Mission staging fix -- #include this
// (never compiled/run standalone) from k_ptar_trigdoor.nss (stages Mission)
// and k_ptar_addzaal.nss (reverts her once the recruit node has run).
//
// Why this exists: Zaalbar's rescue is the cell-door scene in the Undercity
// sewers (tar_m05aa, dialogue missdoor_dlg), and every branch that frees him
// is gated on IsNPCPartyMember(NPC_MISSION) (k_ptar_mischk) -- Zaalbar only
// speaks Shyriiwook and Mission translates. The no-Mission starter
// (k_con_missionnpm) is a dead-end with no scripts attached. Under
// companion_mode=ap_gated Mission's own item may not have arrived by the time
// the player reaches the cell (nothing orders the checks), and under
// companion_mode=none she never does, so the recruit check could never fire.
//
// The scene is started by the trigger tar05_trigdoor (script k_ptar_trigdoor,
// bound to BOTH its OnEnter and OnExit), which only acts when Mission is a
// party member. So Mission is staged BEFORE that trigger runs, and the real
// vanilla scene then plays untouched.
//
// Mission must STAY seated for the whole conversation, not be reverted in the
// same tick the way the Bastila/Carth gate does: missdoor_dlg's starter checks
// IsNPCPartyMember(NPC_MISSION) when the conversation actually BEGINS, which
// is after the script that queued it has returned. She is reverted from
// k_ptar_addzaal (the conversation's final node) instead, with a fallback
// timer for a player who never completes the scene.
//
// State lives in KSE data (in-DLL memory, no save persistence needed for
// something this short-lived), same as the Vulkar forcefield fix in
// k_ptar_startconv.nss. Same party-cap protection as that fix: AddPartyMember
// silently fails to seat a companion when the active party is already full,
// so whichever companion occupies slot 2 is benched first (same object
// reference, no recreation) and restored afterward.
#include "kse"

int GetZaalMissionNPCIndex(object oCompanion)
{
    string sTag = GetTag(oCompanion);
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

// "The cell-door scene has already played." Vanilla's own marker is local
// boolean 10 on tar05_celltalker (set by the dialogue's k_act_talktrue on the
// conversation OWNER), which is only that object when the scene was started
// through the talker, so it can't be the only signal. ZaalbarSceneComplete()
// marks it in three places: KSE data (this process only), a local boolean on
// the PC (meant to persist with the character across a save/load -- not yet
// verified; index 77 is unused elsewhere in this project), and vanilla's own
// flag so the vanilla trigger agrees.
int ZaalSceneAlreadyPlayed()
{
    if (KSE_GetData("zaal_scene_done") == "1") return TRUE;
    if (GetLocalBoolean(GetFirstPC(), 77)) return TRUE;
    object oTalker = GetObjectByTag("tar05_celltalker");
    if (GetIsObjectValid(oTalker) && GetLocalBoolean(oTalker, 10)) return TRUE;
    return FALSE;
}

void MarkZaalSceneDone()
{
    KSE_SetData("zaal_scene_done", "1");
    SetLocalBoolean(GetFirstPC(), 77, TRUE);
    object oTalker = GetObjectByTag("tar05_celltalker");
    if (GetIsObjectValid(oTalker))
    {
        SetLocalBoolean(oTalker, 10, TRUE);
    }
}

// Forward declaration: the fallback re-arms itself while a conversation is
// still running.
void ZaalbarMissionFallback();

// RemovePartyMember/RemoveAvailableNPC only edit the party roster: the
// creature object keeps standing in the area and the player can still walk
// up to her and pick her back up. A staged Mission is temporary by
// definition (she is only staged while her AP item hasn't arrived, and a
// real grant later creates a fresh object), so destroy every object that
// carries her tag. Looped because an earlier staging may have left a second
// one behind.
void PurgeStrayMission()
{
    int nStray = 0;
    object oStray = GetObjectByTag("mission", nStray);
    while (GetIsObjectValid(oStray))
    {
        DestroyObject(oStray);
        nStray++;
        oStray = GetObjectByTag("mission", nStray);
    }
}

// Idempotent. KSE_HasData only checks key EXISTENCE, not value truthiness, so
// the explicit value comparison is the reliable way to make this safe to call
// from several paths (recruit node, fallback timer) in any order.
void RevertZaalbarMission()
{
    if (KSE_GetData("zaal_mission_staged") != "1") return;
    KSE_SetData("zaal_mission_staged", "0");

    RemovePartyMember(NPC_MISSION);
    RemoveAvailableNPC(NPC_MISSION);
    PurgeStrayMission();

    int nBenchedNPC = StringToInt(KSE_GetData("zaal_benched_npc"));
    if (nBenchedNPC != -1)
    {
        object oBenched = GetObjectByTag(KSE_GetData("zaal_benched_tag"));
        if (GetIsObjectValid(oBenched))
        {
            AddPartyMember(nBenchedNPC, oBenched);
        }
    }

    KSE_Diag(172, "AP|SAFEGUARD|tar_zaalbar_mission|reverted");
}

// Safety net only: if the player stages Mission but never completes the scene
// (walks off, or the scene never starts), don't leave her seated forever. The
// cell-door conversation is long, so while the PC is still in a conversation
// this looks again later instead of pulling Mission out from under it.
void ZaalbarMissionFallback()
{
    if (KSE_GetData("zaal_mission_staged") != "1") return;

    if (GetIsInConversation(GetFirstPC()))
    {
        DelayCommand(30.0, ZaalbarMissionFallback());
        return;
    }
    RevertZaalbarMission();
}

void StageZaalbarMission()
{
    object oPC = GetFirstPC();
    int nBenchedNPC = -1;
    object oBenched = OBJECT_INVALID;

    object oSlot2 = GetPartyMemberByIndex(2);
    if (GetIsObjectValid(oSlot2))
    {
        int nCandidate = GetZaalMissionNPCIndex(oSlot2);
        if (nCandidate != -1)
        {
            oBenched = oSlot2;
            nBenchedNPC = nCandidate;
            RemovePartyMember(nBenchedNPC);
        }
    }

    // Reuse a Mission already standing in this module (e.g. left behind by
    // the Vulkar forcefield staging, which doesn't destroy hers) instead of
    // always creating another, so there is never a tag-colliding clone.
    object oMission = GetObjectByTag("mission");
    if (!GetIsObjectValid(oMission))
    {
        oMission = CreateObject(OBJECT_TYPE_CREATURE, "p_mission", GetLocation(oPC));
    }
    AddAvailableNPCByTemplate(NPC_MISSION, "p_mission");
    AddPartyMember(NPC_MISSION, oMission);

    KSE_SetData("zaal_mission_staged", "1");
    KSE_SetData("zaal_benched_npc", IntToString(nBenchedNPC));
    if (nBenchedNPC != -1)
    {
        KSE_SetData("zaal_benched_tag", GetTag(oBenched));
    }

    KSE_Diag(172, "AP|SAFEGUARD|tar_zaalbar_mission|staged|benched=" + IntToString(nBenchedNPC));

    DelayCommand(240.0, ZaalbarMissionFallback());
}

// Called from the recruit wrapper (k_ptar_addzaal), the final node of the
// cell-door conversation. Mission is a speaker in that dialogue, so give it
// time to wind down before taking her out of the party.
void ZaalbarSceneComplete()
{
    // Always mark it done, whether or not Mission was staged: this node is
    // the end of the scene either way, and the trigger must not stage her
    // again for a scene that has already played.
    MarkZaalSceneDone();

    if (KSE_GetData("zaal_mission_staged") == "1")
    {
        DelayCommand(6.0, RevertZaalbarMission());
    }
}
