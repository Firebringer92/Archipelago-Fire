// Story gate T3 backstop (Tatooine): the star-map activation. Wrapper for the node script k_ptat_starcut on E0 of the
// hologram dialog tat18_starspeak. The script moves the party, raises tat_StarmapFound and recomputes K_STAR_MAP and
// the Leviathan journal. The journal entry tat17_starmap 90 is not written by this script but by the node itself, so
// the real gate is the wrapper on the placeable that starts the conversation (sg_k_tat_pla_actmap); this one keeps the
// activation itself closed if the dialog is ever reached another way.
//
// k_ptat_starcut has two compiled versions: tat_m18ac (this planet, kept as apo_sg_tatstar) and an unrelated copy in
// kas_m25aa and korr_m39aa (identical to each other, kept as apo_sg_tatstarx). No dialog or object in those modules
// calls their copy, but the wrapper still picks the right original by module so they behave as in vanilla.
#include "ap_gate"

void main()
{
    string sModule = GetStringLowerCase(GetModuleFileName());
    if (sModule == "kas_m25aa" || sModule == "korr_m39aa")
    {
        ExecuteScript("apo_sg_tatstarx", OBJECT_SELF);
        return;
    }
    if (!ApGateOpen("tat", 3))
    {
        ApGateMsg("Tatooine", 3);
        return;
    }
    ExecuteScript("apo_sg_tatstar", OBJECT_SELF);
}
