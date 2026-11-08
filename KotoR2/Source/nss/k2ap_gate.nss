// k2ap_gate.nss -- the story gate check (include file). Generated wrappers in Override call K2AP_GateOpen at the story beat they hold back.
//
// A gate is open when any of these holds:
//   * the seed has story gates off, or no patch was applied (K2AP_StoryGates() reads 0);
//   * the seed switched this gate off (K2AP_GateOff);
//   * the player released it with /release (a player boolean, 32 + the gate's number, set by the dispatcher's "release" job);
//   * the player has enough progression items of the gate's family: the stage of the family's journal quest ap_prog_<family> (client/k2_journal.py) is the number
//     received; the dispatcher's "token" job moves it one stage on. The stage lives in the save and is not an item, so the lockers of 202TEL cannot take it.
// The Bazaar's token and receipts and the Vendor's passes are still items; the wrapper of my_clear_inv gives them back from the lockers (K2AP_TokensFromLockers).
// Every decision is reported to the client: "GB|<gate>|<have>|<need>" when the beat is held back, "GP|<gate>" when it passes.
//
// Testing aids (set by hand in the extender's config.txt, outside the client's block; both default to 0 = off):
//   ap_debug=1         every wrapper reports what it did on screen ("[AP] a_load262: gate FIN2 open, running the original"); the same lines always go to the
//                      client as "WT|<script>|<module>|<what>" and into its recorder
//   ap_gate_dryrun=1   a gate that would hold a beat back lets it through and says so ("[AP dry run] FIN2 would hold: you need 2, you have 0"); the client
//                      gets "GB|<gate>|<have>|<need>|dry"

#include "k2ap_seed"

// What a wrapper did, for the client's record and (with ap_debug) on screen.
void K2AP_Trace(string sScript, string sWhat)
{
    K2SE_OutboxPut("WT|" + sScript + "|" + GetStringUpperCase(GetModuleName()) + "|" + sWhat);
    if (K2SE_ConfigInt("ap_debug", 0) != 0) FloatingTextStringOnCreature("[AP] " + sScript + ": " + sWhat, GetFirstPC(), FALSE);
}

// Progression items of a family received so far (families: telos, nar, dxn, dan, kor, endgame): the stage of the family's journal quest, 0 while it has not
// been started. A quest that is not declared in global.jrl (no patch applied) reads as 0 as well.
int K2AP_Tokens(string sFamily)
{
    int nStage = GetJournalEntry("ap_prog_" + sFamily);
    if (nStage < 0) return 0;
    return nStage;
}

// The tags the locker script must not keep from the player: the Bazaar's token and receipts, the Vendor's passes and receipts.
string K2AP_KeptTag(int n)
{
    if (n == 0) return "ap_bz_token";
    if (n == 1) return "ap_bz_buy";
    if (n == 2) return "ap_bz_swap";
    if (n == 3) return "ap_vp_skill";
    if (n == 4) return "ap_vp_abil";
    if (n == 5) return "ap_vp_align";
    if (n == 6) return "ap_vp_supply";
    if (n == 7) return "ap_vd_skill";
    return "ap_vd_abil";
}

// Gives every Bazaar and Vendor item the Telos locker script stored away back to the player. A transfer is immediate (the game's own script relies on that), so
// asking for the first item again after each one finds the next; the count caps the loop.
int K2AP_TokensFromLockers()
{
    int nMoved = 0;
    object oPC = GetFirstPC();
    int nLocker;
    int nKept;
    for (nLocker = 0; nLocker < 5; nLocker++)
    {
        object oLocker = GetObjectByTag("LockerTSFINV", nLocker);
        if (!GetIsObjectValid(oLocker)) continue;
        for (nKept = 0; nKept < 9; nKept++)
        {
            int nGuard = 0;
            object oTok = GetItemPossessedBy(oLocker, K2AP_KeptTag(nKept));
            while (GetIsObjectValid(oTok) && nGuard < 100)
            {
                GiveItem(oTok, oPC);
                nMoved++;
                nGuard++;
                oTok = GetItemPossessedBy(oLocker, K2AP_KeptTag(nKept));
            }
        }
    }
    return nMoved;
}

int K2AP_GateReleased(string sGate)
{
    int nBit = K2AP_GateBit(sGate);
    if (nBit < 0) return FALSE;
    return GetLocalBoolean(GetFirstPC(), 32 + nBit) != 0;
}

// The same decision without a message or a report (for the Jedi count that waits for a token, nss/k2ap_master.nss). A dry run lets everything through.
int K2AP_GateOpenQuiet(string sGate, string sFamily, int nNeeded)
{
    if (!K2AP_StoryGates() || K2AP_GateOff(sGate) || K2AP_GateReleased(sGate)) return TRUE;
    if (K2SE_ConfigInt("ap_gate_dryrun", 0) != 0) return TRUE;
    return K2AP_Tokens(sFamily) >= nNeeded;
}

// sFamily is the config key (telos, nar, dxn, dan, kor, endgame); sFamilyName is the name shown to the player.
int K2AP_GateOpen(string sGate, string sFamily, string sFamilyName, int nNeeded)
{
    if (!K2AP_StoryGates() || K2AP_GateOff(sGate) || K2AP_GateReleased(sGate))
    {
        K2SE_OutboxPut("GP|" + sGate);
        return TRUE;
    }
    int nHave = K2AP_Tokens(sFamily);
    if (nHave >= nNeeded)
    {
        K2SE_OutboxPut("GP|" + sGate);
        return TRUE;
    }
    if (K2SE_ConfigInt("ap_gate_dryrun", 0) != 0)
    {
        FloatingTextStringOnCreature("[AP dry run] " + sGate + " would hold: you need " + IntToString(nNeeded) + " " + sFamilyName + ", you have " + IntToString(nHave) + ".",
                                     GetFirstPC(), FALSE);
        K2SE_OutboxPut("GB|" + sGate + "|" + IntToString(nHave) + "|" + IntToString(nNeeded) + "|dry");
        return TRUE;
    }
    string sMsg = "You need " + IntToString(nNeeded) + " " + sFamilyName + " Progression item(s) to continue.";
    FloatingTextStringOnCreature(sMsg, GetFirstPC(), FALSE);
    K2SE_OutboxPut("GB|" + sGate + "|" + IntToString(nHave) + "|" + IntToString(nNeeded));
    return FALSE;
}
