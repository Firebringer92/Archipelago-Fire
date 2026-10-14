// Replacement for the Taris Hideout "escape plan" trigger script (tar_m02af, trigger tar02_carbas, originally k_ptar_carbas_en).
//
// Vanilla: when Bastila and Carth are both on the available roster and the trigger has not fired, set its once-only flag, block
// clicks for 2.2 seconds, hold the world fade, and after 2 seconds have the creature tagged "bastila" start the conversation
// tar02_carbast with the player. That conversation is where the quest "Taris: The Search for Bastila" gets its final stage (99)
// and the escape quest starts.
//
// Under companion_mode ap_gated/none neither companion is on the roster yet, so the vanilla condition never passes and the
// scene never plays. The first fix ran the preserved original through ExecuteScript behind a temporary roster grant, but a
// conversation started from a script reached through ExecuteScript silently fails to queue: the fade is held, nobody speaks and
// the screen stays black. So the scene is written out here. It does not need the companions on the roster at all: the dialog has
// no availability conditions, only two speakers (tags "Bastila" and "Carth") who have to be standing in the area. Nothing is
// granted, so there is nothing to revert, and a companion who arrived early through an item is untouched.
//
// Window: the journal stage of "tar_bastsearch" is 60 (race won, Bastila freed) until the conversation writes 99 on its first line.
// Own once-only flag: local boolean 10 on the trigger, cleared again if the scene could not start so a re-entry can retry.
#include "kse"

// Runs a few seconds after the conversation was queued. If nothing is being said (Bastila never appeared), release the held fade and
// allow another attempt on the next entry. It never starts the conversation itself: that is done directly from main() below.
void ReleaseHideoutFade()
{
    if (GetIsInConversation(GetFirstPC())) return;
    KSE_Diag(171, "AP|BASTILA_CARTH_GATE|carbas_en|no_conversation|bastila=" + IntToString(GetIsObjectValid(GetObjectByTag("bastila"))));
    SetGlobalFadeIn(0.0, 0.5);
    SetLocalBoolean(OBJECT_SELF, 10, FALSE);
}

void main()
{
    int nStage = GetJournalEntry("tar_bastsearch");
    if (nStage < 60 || nStage >= 99) return;
    if (GetLocalBoolean(OBJECT_SELF, 10)) return;
    SetLocalBoolean(OBJECT_SELF, 10, TRUE);

    object oPC = GetFirstPC();
    float fDelay = 2.0;

    // A speaker who is not standing here is created first. A script-created creature appears several seconds late, so wait longer.
    if (!GetIsObjectValid(GetObjectByTag("bastila")))
    {
        CreateObject(OBJECT_TYPE_CREATURE, "p_bastilla", GetLocation(oPC));
        fDelay = 8.0;
        KSE_Diag(171, "AP|BASTILA_CARTH_GATE|carbas_en|placed_bastila");
    }
    if (!GetIsObjectValid(GetObjectByTag("Carth")))
    {
        CreateObject(OBJECT_TYPE_CREATURE, "p_carth", GetLocation(oPC));
        fDelay = 8.0;
        KSE_Diag(171, "AP|BASTILA_CARTH_GATE|carbas_en|placed_carth");
    }

    NoClicksFor(fDelay + 0.2);
    HoldWorldFadeInForDialog();
    DelayCommand(fDelay, AssignCommand(GetObjectByTag("bastila"),
        ActionStartConversation(oPC, "tar02_carbast", FALSE, CONVERSATION_TYPE_CINEMATIC, TRUE)));
    DelayCommand(fDelay + 3.0, ReleaseHideoutFade());
}
