// OnEnter of the trigger template ebo40_carthtlk (overridden .utt; the same
// template sits in ebo_m40aa and ebo_m40ad). Its vanilla script, k_pebo_carthtlk,
// is a different script in each of the three Ebon Hawk modules that use that
// name, and Override has no per-module scoping, so this is a template-level
// override instead and k_pebo_carthtlk itself is left alone (ebo_m41aa keeps its
// vanilla one).
//   ebo_m40aa (captured Hawk): no conversation from here; a sensor console is
//       placed on the deck and using it stages the cast and starts lev40_carth
//       (ap_lev_cast.nss, ap_lev_use.nss).
//   ebo_m40ad (after the escape): the vanilla behaviour -- hold the fade, start
//       conversation ebo_carth from Carth, which is what enables the Hawk's
//       take-off -- unless Carth is not standing there (companion_mode
//       ap_gated/none), in which case the same console is placed to stage him.
// The vanilla script was run through ExecuteScript from a wrapper before; the
// conversation start silently fails to queue that way.
#include "kse"
#include "ap_lev_cast"

void main()
{
    if (!GetIsPC(GetEnteringObject())) return;
    if (GetLocalBoolean(OBJECT_SELF, 10)) return;
    SetLocalBoolean(OBJECT_SELF, 10, TRUE);

    if (GetStringLowerCase(GetModuleFileName()) == "ebo_m40ad")
    {
        if (GetIsObjectValid(GetObjectByTag("carth")))
        {
            HoldWorldFadeInForDialog();
            NoClicksFor(1.2);
            DelayCommand(1.0, AssignCommand(GetObjectByTag("carth"),
                ActionStartConversation(GetFirstPC(), "ebo_carth", FALSE, CONVERSATION_TYPE_CINEMATIC, TRUE)));
            return;
        }
        KSE_SetData("lev_scene_started", "0");
        PlaceLevConsole();
        FloatingTextStringOnCreature("Something is wrong with the ship. Check the sensor console.", GetFirstPC());
        return;
    }

    // Do not start the conversation from this trigger. It fires the moment the
    // module opens, before the surrounding area has loaded, and the creatures
    // staged for the conversation only appeared after it had ended; a longer
    // wait with the screen held did not help. Put a console on the deck instead:
    // using it (ap_lev_use) stages the cast and starts the conversation after
    // the scene is up, whoever is in the party.
    KSE_SetData("lev_scene_started", "0");
    PlaceLevConsole();
    FloatingTextStringOnCreature("Something is wrong with the ship. Check the sensor console.", GetFirstPC());
}
