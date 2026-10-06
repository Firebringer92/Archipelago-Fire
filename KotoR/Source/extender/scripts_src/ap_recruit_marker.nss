// Shared helper for the companion recruit checks -- #include this (never
// compiled/run standalone) from every script that reports
// AP|CHECK|COMPANION|<idx>.
//
// Why: that line is a ONE-SHOT. It is written to kse.log once, at the moment
// the recruit is reached, and relayed to whichever client is attached right
// then. If no client is attached, the client is disconnected from the
// Archipelago server, or the relay drops it, the check is lost for good --
// the poll cannot re-derive it (the old IsAvailableCreature poll was removed
// because slot 0 is reused by Trask in the prologue). The journal quest
// ap_recruit_<key> (declared in global.jrl by build_ap_tracker_quest.py) is a
// marker that lives in the SAVE: ap_poll_shared's CheckRecruitMarkers()
// re-reports AP|CHECK|COMPANION|<idx> every poll for every marker that is
// set, until the client has registered it. The client dedups those against
// its checked locations, so repeating them is harmless.
//
// AddJournalQuestEntry silently does nothing for a quest tag that global.jrl
// doesn't declare (as with the tracker quest), so on an install that hasn't
// yet had the recruit quests built this degrades to the one-shot behaviour. Guarded with GetJournalEntry so re-running a hook
// that fires repeatedly (Canderous's hangar door) never re-adds the entry and
// re-triggers the "Journal Updated" notice.
//
// sKey is the companion key (bastila, canderous, carth, hk47, jolee, juhani,
// mission, t3m4, zaalbar); nIdx is Locations.py's companion_idx for it.
#include "kse"

void RecordRecruit(string sKey, int nIdx)
{
    string sTag = "ap_recruit_" + sKey;
    if (GetJournalEntry(sTag) < 1)
    {
        AddJournalQuestEntry(sTag, 1);
    }
    KSE_Diag(22, "AP|CHECK|COMPANION|" + IntToString(nIdx));
}
