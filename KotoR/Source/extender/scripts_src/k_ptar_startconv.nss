// Wrapper for the Undercity sewer route's forcefield control console
// (originally tar_m05aa's k_ptar_startconv, placeable tag
// tar05_ffcontrol, OnUsed script, preserved byte-exact as
// apo_startconv_orig).
//
// Root cause, confirmed via disassembly: this is the "back way" into the
// Black Vulkar Base (tar_m04aa -> tar_m05aa -> forcefield -> tar_m05ab
// -> elevator -> tar_m10aa) -- the alternative to the front door
// (tar03_blkdoor, which vanilla only unlocks AFTER you're already
// inside, so it's a return-trip convenience, not a first-entry route).
// The console's own script checks `!GetIsOpen(tar05_forcefield) &&
// IsNPCPartyMember(NPC_MISSION)` before starting the real "Mission opens
// the forcefield" conversation (`tar05_ff_dlg2`, whose own dialogue
// action nodes do the actual SetLocked/ActionOpenDoor work -- not
// reimplemented here, just gated the same way vanilla does). If Mission
// isn't in the party, this is a silent no-op (an empty fallback
// conversation, confirmed via disassembly) -- no Security/Demolitions
// bypass exists anywhere on this route.
//
// This makes the Black Vulkar Base's first entry a hard, two-route
// requirement: EITHER route needs Mission -- the front door
// (tar03_blkdoor) is closed until the game already considers you
// "inside" (set by tar_m10aa's own OnEnter, an obvious chicken-and-egg),
// so this back way, gated on Mission specifically, is genuinely the
// only way in the first time. tar05_forcefield's own UTD confirms
// locked=TRUE/lockable=FALSE (no Security bypass, same shape as the
// Sith Base door fixed earlier); a full game-wide scan of every
// module's compiled scripts for anything else that ever calls
// SetLocked/ActionOpenDoor on tar03_blkdoor or tar05_forcefield found
// nothing else -- this console is the sole unlock path.
//
// Real, confirmed bug this closes: under companion_mode=ap_gated,
// "Companion: Mission Vao" is a real placeable AP item (Options.py) that
// could land on "Taris: Inside the Vulkar Base" itself -- a location
// whose own journal completion requires having ALREADY infiltrated the
// base. See `Archipelago/worlds/kotor/__init__.py`'s
// MISSION_ITEM_EXCLUDED_LOCATIONS, now also excluding that location at
// generation time for all FUTURE seeds -- but a seed already generated
// before that fix could have this exact circular dependency baked in
// (Mission's own recruit item needed to enter the one place that grants
// it), a genuine permanent story soft-lock. This wrapper is the live
// safety net for exactly that case, and for the general
// companion_mode=ap_gated/none timing risk this project has already
// fixed the same way for the Taris Hideout and the Sith Base door.
//
// Hard prerequisite, same principle as those two fixes:
// GetJournalEntry("tar_bastsearch") >= 28 -- the real stage where the
// game first tells the player Bastila's been captured by the Vulkars
// and finding a way into their base won't be easy (confirmed directly
// against global.jrl), so this never fires before that objective is
// even assigned.
//
// DESIGN, arrived at after several live-tested dead ends (party-cap
// silently failing AddPartyMember; a freshly CreateObject'd companion
// not being fully "materialized" for GetPartyMemberByIndex/UI purposes
// in the same tick; ActionStartConversation only queuing rather than
// blocking, so an immediate same-tick revert likely cancelled it
// silently) -- fixing each of those individually with scripted
// DelayCommand delays never got the real dialogue to actually fire,
// even after 8+ real seconds. The user's own suggestion, confirmed to
// work by matching how they actually play it: split this across TWO
// REAL, PLAYER-DRIVEN clicks instead of trying to script-simulate
// enough settling time in one shot.
//   - Click 1 (Mission not yet available): stage her (bench a companion
//     if a slot's needed, AddAvailableNPCByTemplate+CreateObject+
//     AddPartyMember), then STOP -- do not touch the real console logic
//     at all this click. This guarantees real engine ticks/frames pass
//     before anything else happens, which no scripted delay reliably
//     replicated.
//   - Click 2 (Mission now available, confirmed by the player
//     themselves before clicking again): originally delegated straight
//     to the preserved original via ExecuteScript -- but even with every
//     gate condition fully traced and confirmed passing (!GetIsOpen(FF)
//     && IsNPCPartyMember(Mission)), the conversation never actually
//     played. CONFIRMED LIVE, a new engine-behavior finding for this
//     project: ActionStartConversation, called from a script reached
//     via ExecuteScript rather than directly by the native OnUsed event,
//     silently fails to queue -- same general category as the
//     already-documented "FloatingTextStringOnCreature silently no-ops
//     when called from inside a DelayCommand-targeted custom function"
//     finding, just for a different native and a different indirection
//     path. Fix: replicate the real (fully-traced) gate directly in this
//     wrapper and call ActionStartConversation ourselves -- no
//     ExecuteScript hop at all. Applies to BOTH the click-2 path below
//     AND the "already legitimate" passthrough further down (which
//     affects every player who reaches this console, not just the
//     AP-gated case this wrapper exists for).
// Whether THIS click actually needed to stage anyone is remembered
// across the two separate script invocations via KSE_SetData/KSE_
// HasData (in-DLL memory, no save-file persistence needed for
// something this short-lived) -- see kse.nss's own LIFETIME comment.
// Reverts Mission (and restores any benched companion) immediately
// after the real original runs on click 2, same "no permanent change"
// principle as every other fix in this family. A generous 60-second
// DelayCommand fallback also force-reverts if the player stages Mission
// on click 1 but never actually returns for a second click (e.g. they
// wander off) -- guarded by the same KSE flag so it's a safe no-op if
// click 2 already handled it normally.
#include "kse"

int GetCompanionNPCIndex(object oCompanion)
{
    string sTag = GetTag(oCompanion);
    if (sTag == "bastila") return NPC_BASTILA;
    if (sTag == "cand") return NPC_CANDEROUS;
    if (sTag == "carth") return NPC_CARTH;
    if (sTag == "hk47") return NPC_HK_47;
    if (sTag == "jolee") return NPC_JOLEE;
    if (sTag == "juhani") return NPC_JUHANI;
    if (sTag == "mission") return NPC_MISSION;
    if (sTag == "t3m4") return NPC_T3_M4;
    if (sTag == "zaalbar") return NPC_ZAALBAR;
    return -1;
}

void RevertForcefieldMission()
{
    // KSE_HasData only checks key EXISTENCE, not value truthiness -- a
    // key set to "" still "exists", so explicit value comparison is the
    // only reliable way to make this idempotent/resettable across
    // multiple real triggers of this whole sequence.
    if (KSE_GetData("ff_mission_staged") != "1") return;

    RemovePartyMember(NPC_MISSION);
    RemoveAvailableNPC(NPC_MISSION);

    int nBenchedNPC = StringToInt(KSE_GetData("ff_benched_npc"));
    if (nBenchedNPC != -1)
    {
        object oBenched = GetObjectByTag(KSE_GetData("ff_benched_tag"));
        if (GetIsObjectValid(oBenched))
        {
            AddPartyMember(nBenchedNPC, oBenched);
        }
    }

    KSE_SetData("ff_mission_staged", "0");
    KSE_Diag(163, "AP|SAFEGUARD|tar_forcefield_mission|reverted");
}

void main()
{
    // Click 2 (or later): we already staged Mission on an earlier click
    // and are just waiting for the player to come back and try the
    // console again now that she's settled. Run the real, unmodified
    // original -- its own gate now sees a genuinely available Mission --
    // then revert shortly after (long enough for ActionStartConversation,
    // which only queues rather than blocks, to actually play).
    if (KSE_GetData("ff_mission_staged") == "1")
    {
        KSE_Diag(163, "AP|SAFEGUARD|tar_forcefield_mission|click2|missionSeated="
                      + IntToString(IsNPCPartyMember(NPC_MISSION)));

        // CONFIRMED LIVE FIX: every layer of apo_startconv_orig's own
        // gating traced and confirmed passing at this point
        // (!GetIsOpen(forcefield) && IsNPCPartyMember(Mission)), yet the
        // dialogue never actually played when reached via
        // ExecuteScript("apo_startconv_orig", ...) -- something about
        // invoking the preserved original specifically via ExecuteScript
        // silently failed to queue the conversation. Calling the real
        // conversation directly instead is confirmed live to work. The
        // dialogue's own action-node logic (SetLocked/ActionOpenDoor on
        // tar05_forcefield) is unaffected either way, since that lives
        // in the .dlg itself, not in this script.
        ActionStartConversation(GetFirstPC(), "tar05_ff_dlg2");

        // 10s -- shortened back down from 30s per live feedback (the
        // real conversation turned out to be short). NOTE: confirmed
        // live this DelayCommand can be silently dropped if the player
        // transitions to a different module before it fires (it's
        // scheduled against this console's own object, in this
        // console's own module) -- a real, accepted limitation for now,
        // not fully closed. If Mission is ever left stuck afterward,
        // clicking the console again re-fires this same revert path
        // safely (idempotent via the ff_mission_staged flag check).
        DelayCommand(10.0, RevertForcefieldMission());
        return;
    }

    // Click 1 (or Mission/companion_mode already legitimate): if she's
    // already really available (normal recruit, or ap_gated after her
    // real item arrived), no staging needed -- but still replicate the
    // real gate directly rather than ExecuteScript("apo_startconv_orig",
    // ...), which is CONFIRMED LIVE to silently fail to queue the
    // conversation (see the click-2 path's own comment). This affects
    // EVERY player who reaches this console, including completely
    // vanilla companion_mode=normal ones -- not just the AP-gated case
    // this whole wrapper exists for.
    if (GetJournalEntry("tar_bastsearch") < 28 || IsAvailableCreature(NPC_MISSION))
    {
        object oFF = GetObjectByTag("tar05_forcefield");
        if (GetIsObjectValid(oFF) && !GetIsOpen(oFF) && IsNPCPartyMember(NPC_MISSION))
        {
            ActionStartConversation(GetFirstPC(), "tar05_ff_dlg2");
        }
        // else: door already open, or Mission recruited but not
        // currently in the active 3-person party -- matches vanilla's
        // own no-op behavior for either case, nothing to do.
        return;
    }

    // Real click 1: stage her, then stop. The player needs to click the
    // console again once they see she's available.
    object oPC = GetFirstPC();
    int nBenchedNPC = -1;
    object oBenched = OBJECT_INVALID;

    object oSlot2 = GetPartyMemberByIndex(2);
    if (GetIsObjectValid(oSlot2))
    {
        int nCandidate = GetCompanionNPCIndex(oSlot2);
        if (nCandidate != -1)
        {
            oBenched = oSlot2;
            nBenchedNPC = nCandidate;
            RemovePartyMember(nBenchedNPC);
        }
    }

    AddAvailableNPCByTemplate(NPC_MISSION, "p_mission");
    object oMission = CreateObject(OBJECT_TYPE_CREATURE, "p_mission", GetLocation(oPC));
    AddPartyMember(NPC_MISSION, oMission);

    KSE_SetData("ff_mission_staged", "1");
    KSE_SetData("ff_benched_npc", IntToString(nBenchedNPC));
    if (nBenchedNPC != -1)
    {
        KSE_SetData("ff_benched_tag", GetTag(oBenched));
    }

    KSE_Diag(163, "AP|SAFEGUARD|tar_forcefield_mission|click1_staged|benched=" + IntToString(nBenchedNPC));

    // Safety net only -- if the player never comes back for a second
    // click, don't leave Mission (and a benched companion) stuck
    // indefinitely. A real click 2 already reverts on its own 8s after
    // running the original; this just catches the "walked away" case.
    DelayCommand(60.0, RevertForcefieldMission());
}
