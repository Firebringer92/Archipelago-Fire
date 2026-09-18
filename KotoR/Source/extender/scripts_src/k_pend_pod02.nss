// Replaces the escape pod's real vanilla OnUsed script entirely
// (preserved, unused, as apo_pod02_org.ncs). The true original never
// actually transitions to a new module at all: it does GetObjectByTag-based
// AssignCommand/JumpToObject calls (4x) to stage the party at specific
// waypoints WITHIN end_m01ab itself, a SetGlobalFadeOut/FadeIn pair, then
// an ActionStartConversation, with party heal/resurrection tacked on at
// the end. If any of those GetObjectByTag lookups fail to resolve to a
// valid object -- plausible if Additional Enemies placed something that
// collides with an expected tag/waypoint -- the party gets jumped to an
// undefined position with input disabled, a real softlock. This fix
// sidesteps the entire fragile sequence: keeps the one clearly-valuable
// part of the original (heal + resurrect the party, who may have taken
// damage/died during the Endar Spire crash) and replaces everything else
// with a direct transition to tar_m02af. See DEVELOPMENT_HISTORY.md's
// "The escape pod's four independent bugs" section for the full
// investigation this file's fixes came out of.
#include "kse"

// KSE_Diag returns int, not void -- can't be delayed directly (DelayCommand
// requires a void-returning call). This wrapper exists only so the
// 1-second delay itself is independently observable, separate from the
// real StartNewModule delay right after it.
void PodDebugDelayFired()
{
    KSE_Diag(159, "AP|POD02_DEBUG|delay_fired");
}

// Carth's real join script (k_ptar_addcarth, at the end of
// tar02_carth022.dlg) never fires naturally unless the player physically
// reaches tar_m02af's real, unmodified vanilla TRIGGER (tag
// "tar02_carstr", OnEnter script k_ptar_carstr_en, which references
// "carth"/"K_CURRENT_PLANET"/the dialogue resref "tar02_carth022"
// directly). Queuing ActionStartConversation before StartNewModule does
// not work -- the queued action does not survive the module transition.
// The actual fix is landing close enough for the trigger to fire on
// arrival: this script's StartNewModule call previously used
// "tar02_sw02af", the generic
// door-arrival waypoint, which lands ~9 units away from the trigger's
// zone -- too far for it to fire on arrival, so the player had to
// manually walk over and find it themselves (never guaranteed, and Carth
// is lost for good if you wander off first). tar_m02af's own waypoint
// list already has "tar02_swplayerapt" ("spawn waypoint, player,
// apartment") sitting under 1 unit from the trigger's own position --
// clearly the real, purpose-built landing point for this exact scene.
// Fix: land there instead, so the trigger fires immediately on arrival
// with zero extra script logic needed on our end.
void PodTransitionFired()
{
    KSE_Diag(159, "AP|POD02_DEBUG|starting_new_module");
    StartNewModule("tar_m02af", "tar02_swplayerapt");
}

// DIAGNOSTIC INSTRUMENTATION: code 159 marks each stage of main() (loop
// iteration, heal, transition) so a failure can be localized from
// kse.log instead of guessed at. Remove once no longer needed for
// debugging.
void main()
{
    KSE_Diag(159, "AP|POD02_DEBUG|main_start");
    // Must not use "continue;" to skip an invalid party slot here: this
    // is a real, documented pitfall in the original BioWare/Aurora
    // NWScript compiler this game's nwnnsscomp is based on -- "continue"
    // inside a "for" loop does not reliably compile to a jump back to the
    // increment step. Confirmed via KSE_Diag tracing that main() simply
    // STOPS EXECUTING the instant it hits "continue" for an invalid
    // member (index 1, no second party member yet this early in the
    // game), never reaching index 2 or the transition code below.
    // Confirmed this codebase uses "continue" inside a loop NOWHERE else
    // -- every other loop in the whole project already avoids it, whether
    // by convention or a lesson learned elsewhere. Fixed by wrapping the
    // rest of the body in a plain "if" instead of an early exit.
    int i;
    for (i = 0; i < 3; i++)
    {
        KSE_Diag(159, "AP|POD02_DEBUG|loop_iter_" + IntToString(i));
        object oMember = GetPartyMemberByIndex(i);
        KSE_Diag(159, "AP|POD02_DEBUG|got_member_" + IntToString(i) + "_valid=" + IntToString(GetIsObjectValid(oMember)));
        if (GetIsObjectValid(oMember))
        {
            KSE_Diag(159, "AP|POD02_DEBUG|checking_hp_" + IntToString(i));
            if (GetCurrentHitPoints(oMember) <= 0)
            {
                KSE_Diag(159, "AP|POD02_DEBUG|resurrecting_" + IntToString(i));
                ApplyEffectToObject(DURATION_TYPE_INSTANT, EffectResurrection(), oMember);
            }
            KSE_Diag(159, "AP|POD02_DEBUG|healing_" + IntToString(i));
            ApplyEffectToObject(DURATION_TYPE_INSTANT, EffectHeal(999), oMember);
            KSE_Diag(159, "AP|POD02_DEBUG|healed_" + IntToString(i));
        }
    }
    KSE_Diag(159, "AP|POD02_DEBUG|heal_done");

    // The transition target must not be tar_m02aa: it is TWO hops past
    // the actual next module -- this project's own docs/history/PHASE12.md
    // documented the real chain: "Endar Spire -> Hideout -> tar_m02aa is
    // the fixed prelude" (tar_m02af = Taris Hideout is the direct next
    // stop; tar_m02aa/South Apartments comes AFTER that, via the
    // Hideout's own real exit door, not a script). Independently
    // confirmed against LaneDibello's Kotor-Randomizer's own verified
    // module graph (KotorModules.xml): "end_m01ab -> LeadsTo tar_m02af".
    // A full game-wide disassembly scan for every script in both Endar
    // Spire modules calling StartNewModule at all found exactly one
    // reachable candidate (this script) -- so the call itself firing was
    // never in question, only its argument.
    //
    // Cross-checked against the only real, live-confirmed StartNewModule
    // call in this codebase (Bastila's recruit script, apo_bastila_orig,
    // per docs/history/PHASE11.md) -- that call fires from INSIDE a
    // dialogue script node, never from a raw OnUsed placeable handler.
    // OnUsed fires while the PC is still mid-AssignCommand "walk to and
    // use" action, so the ClearAllActions+DelayCommand wrapping stays --
    // that part was never confirmed wrong, just insufficient on its own
    // given the destination itself was also wrong.
    object oPC = GetFirstPC();
    KSE_Diag(159, "AP|POD02_DEBUG|before_clear_actions");
    AssignCommand(oPC, ClearAllActions());
    KSE_Diag(159, "AP|POD02_DEBUG|before_delay_schedule");
    // Note on StartNewModule's waypoint argument: a real failure mode
    // here is the transition succeeding but the player spawning inside a
    // wall -- leaving sWayPoint empty makes StartNewModule fall back to some arbitrary
    // default position in tar_m02af, not a real entrance. This project's
    // own door_graph.json (built from real vanilla door data, not
    // guessed) shows the actual vanilla door into this module
    // (tar_m02aa's "tar02_aprtdoor") arrives at waypoint "tar02_sw02af"
    // -- using that same real entry point instead of an empty default.
    DelayCommand(1.0, PodDebugDelayFired());
    DelayCommand(1.0, PodTransitionFired());
}
