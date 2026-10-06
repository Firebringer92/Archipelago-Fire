// Wrapper for the Undercity sewer cell-door trigger's real script
// (originally tar_m05aa's k_ptar_trigdoor, trigger tag tar05_trigdoor, bound
// to BOTH its OnEnter and OnExit; preserved byte-exact as apo_trigdoor_orig).
//
// Root cause, confirmed via disassembly: this trigger is what starts the
// scene that frees and recruits Zaalbar. It only acts when Mission is a party
// member (IsNPCPartyMember(NPC_MISSION)) and the cell talker's "already
// played" flag (local boolean 10 on tar05_celltalker, set by the dialogue's
// k_act_talktrue) is clear. Zaalbar speaks only Shyriiwook and Mission is his
// translator: missdoor_dlg's no-Mission starter is a dead-end with no
// scripts, so without her the recruit node (k_ptar_addzaal, which reports the
// "Companion Recruited: Zaalbar" AP check) can never be reached. Under
// companion_mode=ap_gated her item may not have arrived yet, and under
// companion_mode=none it never does.
//
// Fix: when the PC walks into the trigger and Mission isn't available, seat
// her first (ap_zaal_mission.nss: bench a companion if the party is full,
// AddAvailableNPCByTemplate + AddPartyMember), then let the REAL vanilla scene
// run untouched. That event itself only stages and returns without running
// the original: the scene needs a settled party member, and a Mission created
// in the same tick isn't one yet (same finding as the Vulkar forcefield fix in
// k_ptar_startconv.nss). Because this script is bound to the trigger's
// OnExit as well, the original runs the next time the trigger fires -- on
// leaving it, or on re-entering it -- by which point she is settled, and the
// vanilla cinematic and conversation start exactly as designed. Clicking the
// door instead works too: its OnFailToOpen conversation sees Mission in the
// party and takes the real branch.
//
// Every other case calls straight through to the preserved original, so a
// player who legitimately has Mission (companion_mode=normal, or ap_gated
// after her item arrives) gets the unchanged vanilla scene. Mission is
// reverted from k_ptar_addzaal once the recruit node has run, with a
// conversation-aware fallback timer for a player who never completes it.
#include "kse"
#include "ap_zaal_mission"

void main()
{
    object oEntering = GetEnteringObject();

    if (GetIsPC(oEntering)
        && !IsAvailableCreature(NPC_MISSION)
        && KSE_GetData("zaal_mission_staged") != "1"
        && !ZaalSceneAlreadyPlayed())
    {
        StageZaalbarMission();
        return;
    }

    ExecuteScript("apo_trigdoor_orig", OBJECT_SELF);
}
