// Story gate T2 (Tatooine): the dragon scene. Replaces the vanilla condition k_ptat_banthardy, the "banthas are in
// position" test. It is used only by Komad's dialog tat18_11komad_01 (the copy in tat_m18aa is identical and unused):
// his starter E10 and the links into E10, E50, E87 and E100 all lead to the node that spawns the krayt dragon and runs
// the cutscene chain (journal tat18ac_dragonhunt 60 to 70, tat17_starmap 80). Vanilla body: area flag 4 (set by
// k_ptat_banthcut2) is set. The gate adds "holds two Tatooine progression items". Without them Komad falls back to his other
// lines and the flag stays set, so the scene plays as soon as the progression items arrive.
#include "ap_gate"

int StartingConditional()
{
    if (GetLocalBoolean(GetArea(OBJECT_SELF), 4) == 0) return FALSE;
    if (!ApGateOpen("tat", 2))
    {
        ApGateMsg("Tatooine", 2);
        return FALSE;
    }
    return TRUE;
}
