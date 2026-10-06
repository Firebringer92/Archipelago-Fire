// OnUsed of ap_lev_console, the sensor console the Leviathan fixes put on the
// Ebon Hawk's deck (see ap_lev_cast.nss). Using it stages whoever the scene's
// conversation assumes and, eight seconds later, has Carth start that
// conversation with the player:
//   ebo_m40aa (captured Hawk)   -> the whole cast, conversation lev40_carth
//   ebo_m40ad (after the escape) -> Carth only, conversation ebo_carth
// The wait is world time with the world visible, so the staged creatures finish
// appearing first (a creature staged right before a conversation only shows up
// after it, since the world does not tick during one). The start stays directly
// inside DelayCommand: that is the form that works (ActionStartConversation from
// a custom function, or reached through ExecuteScript, silently fails to queue).
#include "kse"
#include "ap_lev_cast"

void main()
{
    if (KSE_HasData("lev_scene_started") && KSE_GetData("lev_scene_started") == "1") return;
    KSE_SetData("lev_scene_started", "1");

    int bEscape = (GetStringLowerCase(GetModuleFileName()) == "ebo_m40ad");
    if (bEscape) StageLevCastCarth();
    else StageLevCast();
    NoClicksFor(8.2);
    KSE_Diag(177, "AP|SAFEGUARD|lev_capture_cast|console_used|escape=" + IntToString(bEscape)
        + "|standing=" + IntToString(LevCastReady()));
    if (bEscape)
    {
        DelayCommand(8.0, AssignCommand(GetObjectByTag("carth"),
            ActionStartConversation(GetFirstPC(), "ebo_carth", FALSE, CONVERSATION_TYPE_CINEMATIC, TRUE)));
    }
    else
    {
        DelayCommand(8.0, AssignCommand(GetObjectByTag("carth"),
            ActionStartConversation(GetFirstPC(), "lev40_carth", FALSE, CONVERSATION_TYPE_CINEMATIC, TRUE)));
    }
    // Not destroyed here: the delayed start above is scheduled against this
    // console, and a delayed command dies with the object that issued it (the
    // first version destroyed it at once and the conversation never started).
    DelayCommand(10.0, DestroyObject(OBJECT_SELF));
}
