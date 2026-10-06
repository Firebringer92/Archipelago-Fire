// Wrapper for the Unknown World temple guide's ritual scene (conversation
// unk41_guide_dlg in unk_m41ad; real script preserved as apo_temple02_orig).
//
// The real script pauses the conversation for 11 seconds, and 1.5 seconds in
// calls SpawnAvailableNPC for Jolee and (unless DAN_JUHANI_PLOT is 2) Juhani
// at their waypoints; the lines that follow ("Wait... someone is coming!") are
// spoken by them. Nothing checks that they are available. Under
// companion_mode=ap_gated/none they are not. A first fix that only made them
// available (AddAvailableNPCByTemplate) left SpawnAvailableNPC producing no
// creature, as for a roster entry added moments earlier anywhere else (see
// ap_lev_cast.nss), so the conversation still ended at their first line.
//
// Fix: make both available and CREATE them from their templates at the
// waypoints at once (the proven way the companion grants seat a creature), so
// they are standing well inside the 11-second pause, then run the real
// script. If its own spawn also produces a creature, the extra one is removed
// five seconds later. The ritual's last script (k_punk_pretempl2) seats them
// in the party as in the vanilla game, so they stay for the last stretch.
#include "kse"

void StageTempleNpc(int nNPC, string sTag, string sTemplate, string sWaypointTag)
{
    if (!IsAvailableCreature(nNPC)) AddAvailableNPCByTemplate(nNPC, sTemplate);
    if (GetIsObjectValid(GetObjectByTag(sTag))) return;
    object oWp = GetObjectByTag(sWaypointTag);
    location lLoc = GetLocation(GetFirstPC());
    if (GetIsObjectValid(oWp)) lLoc = GetLocation(oWp);
    CreateObject(OBJECT_TYPE_CREATURE, sTemplate, lLoc);
}

void RemoveExtra(string sTag)
{
    int nIdx = 1;
    object oExtra = GetObjectByTag(sTag, nIdx);
    while (GetIsObjectValid(oExtra))
    {
        DestroyObject(oExtra);
        nIdx++;
        oExtra = GetObjectByTag(sTag, nIdx);
    }
}

void RemoveExtras()
{
    RemoveExtra("jolee");
    RemoveExtra("juhani");
}

void main()
{
    StageTempleNpc(NPC_JOLEE, "jolee", "p_jolee", "unk41_wpjolee");
    if (GetGlobalNumber("DAN_JUHANI_PLOT") != 2)
    {
        StageTempleNpc(NPC_JUHANI, "juhani", "p_juhani", "unk41_wpjuhani");
    }
    ExecuteScript("apo_temple02_orig", OBJECT_SELF);
    DelayCommand(5.0, RemoveExtras());
    KSE_Diag(162, "AP|SAFEGUARD|unk41_temple_jolee_juhani|created="
        + IntToString(GetIsObjectValid(GetObjectByTag("jolee"))) + IntToString(GetIsObjectValid(GetObjectByTag("juhani"))));
}
