// Shared by the Tatooine story-gate scripts (include only, no entry point). Banthas for the krayt dragon hunt.
//
// Vanilla creates the three banthas (tat18_bantha1 to 3) only from Komad's bait briefing (k_ptat_spwnbanth, node
// tat18_11komad_01 E59) and never again. If Komad dies or turns hostile before that briefing, or the player kills the
// banthas, there is nothing left to lure and the dragon lair stays shut.
//
// SgTatEnsureBanthas() creates each missing bantha at its vanilla spawn waypoint (WP_tat18_bantha<n>_05) and removes the
// corpse of a dead one first, so it can run any number of times and never produces duplicates.
//
// SgTatBanthaRepair() decides when that is needed. It must be called with the tat_m18ac area as OBJECT_SELF (the area
// local flag 4 is vanilla's "banthas are in position" mark, set by k_ptat_banthcut2). It acts only while the dragon is
// alive, the banthas are not yet in position, and either Komad is dead or hostile (tat_KomadDead is set by both
// k_ptat_komaduser and k_ptat_komaenemy) or the hunt journal has reached the briefing (tat18ac_dragonhunt 20 or higher).

void SgTatEnsureBanthas()
{
    int i;
    for (i = 1; i <= 3; i++)
    {
        string sTag = "tat18_bantha" + IntToString(i);
        object oBantha = GetObjectByTag(sTag);
        int bAlive = GetIsObjectValid(oBantha) && !GetIsDead(oBantha);
        if (!bAlive)
        {
            if (GetIsObjectValid(oBantha)) DestroyObject(oBantha);
            object oWP = GetWaypointByTag("WP_tat18_bantha" + IntToString(i) + "_05");
            if (GetIsObjectValid(oWP)) CreateObject(OBJECT_TYPE_CREATURE, sTag, GetLocation(oWP), FALSE);
        }
    }
}

void SgTatBanthaRepair()
{
    if (GetGlobalBoolean("tat_KraytDead")) return;
    if (GetLocalBoolean(OBJECT_SELF, 4) != 0) return;
    if (!GetGlobalBoolean("tat_KomadDead") && GetJournalEntry("tat18ac_dragonhunt") < 20) return;
    SgTatEnsureBanthas();
}
