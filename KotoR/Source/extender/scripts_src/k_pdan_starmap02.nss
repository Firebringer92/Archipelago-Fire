// Full replacement for the Dantooine ruins star-map node script (danm15, run from the dan15_bastila conversation after the star-map hologram).
//
// Vanilla writes K_STAR_MAP = 10. The planet star maps (k_pla_actmap) add 10 each and apply the thresholds themselves, so the
// counter only reaches 50 (the Unknown World) when the Dantooine map comes first. With the doors shuffled the ruins map can come after
// planet maps, and the absolute write then erased them: the Leviathan or the Unknown World never fired, or the Unknown World never opened.
//
// This version adds 10 once, then applies the same thresholds k_pla_actmap applies to the new value:
//   30: K_SWG_BASTILA below 3 becomes 99 (Bastila's star-map conversation on the Hawk)
//   40: K_CAPTURED_LEV becomes 5 (the Hawk travel scripts start the Leviathan), and K_SWG_BASTILA below 5 becomes 99
//   50: K_KOTOR_MASTER becomes 30 (the galaxy map offers the Unknown World)
// In the vanilla order (Dantooine first) the counter is 0 here, so the result is 10 with no thresholds, exactly as before.
//
// The node can be reached again by using the star map a second time, so the add is guarded by a local flag on the star-map placeable.
// The rest (the finished flag, the pause and the user-defined event that resumes the conversation) is the vanilla script unchanged.
void main()
{
    object oMap = GetObjectByTag("dan15_starmap");
    int bCounted = GetIsObjectValid(oMap) && GetLocalBoolean(oMap, 40) != 0;
    if (!bCounted)
    {
        if (GetIsObjectValid(oMap)) SetLocalBoolean(oMap, 40, TRUE);
        int nSwg = GetGlobalNumber("K_SWG_BASTILA");
        int nMap = GetGlobalNumber("K_STAR_MAP") + 10;
        SetGlobalNumber("K_STAR_MAP", nMap);
        if (nMap == 30 && nSwg < 3) SetGlobalNumber("K_SWG_BASTILA", 99);
        if (nMap == 40)
        {
            SetGlobalNumber("K_CAPTURED_LEV", 5);
            if (nSwg < 5) SetGlobalNumber("K_SWG_BASTILA", 99);
        }
        if (nMap == 50) SetGlobalNumber("K_KOTOR_MASTER", 30);
    }
    SetGlobalBoolean("DAN_STARMAP_DONE", TRUE);
    ActionPauseConversation();
    ActionDoCommand(SignalEvent(GetObjectByTag("dan15_starmap"), EventUserDefined(10)));
}
