// Taris Undercity sewer forcefield (tar_m05aa): starter condition of the "Mission opens the forcefield" conversation tar05_ff_dlg2, the only
// route into the Black Vulkar Base from the sewers (the console wrapper k_ptar_startconv stages Mission when she is not in the party).
// Vanilla body: Mission is a party member AND Zaalbar is an available companion, i.e. rescued and on the roster. Under
// companion_mode=ap_gated or ap_limited his recruit is suppressed until his item arrives or enough checks are done, so a player who rescued
// him could not get through the forcefield. The conversation only has Mission speaking, so what matters is that Zaalbar was rescued, not
// that he is on the roster: this version also accepts the persistent recruit marker (the journal quest ap_recruit_zaalbar that
// RecordRecruit writes when the rescue's last node runs) and the cell scene's own done marker (PC local boolean 77, see ap_zaal_mission.nss).
// Only the dialog tar05_ff_dlg2 uses this condition, and it exists only in tar_m05aa.
int StartingConditional()
{
    if (!IsNPCPartyMember(NPC_MISSION)) return FALSE;
    if (IsAvailableCreature(NPC_ZAALBAR)) return TRUE;
    if (GetJournalEntry("ap_recruit_zaalbar") > 0) return TRUE;
    if (GetLocalBoolean(GetFirstPC(), 77)) return TRUE;
    return FALSE;
}
