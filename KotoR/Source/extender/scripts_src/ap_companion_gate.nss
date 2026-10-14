// Shared "brain" for the Bastila+Carth temporary-party-gate bug family --
// #include this (never compiled/run standalone) from each thin per-scene
// trampoline. Deliberately separate from ap_poll_shared.nss (the AP
// check/reconciliation "brain" every area trampoline calls) -- this is a
// narrower, unrelated concern: temporarily granting Bastila+Carth around
// a vanilla scene that expects them present, under companion_mode=
// ap_gated/none before their real AP items have arrived. Same "one
// brain, many trampolines" shape, just scoped to this one bug family and
// #include-level (compiled into each trampoline) rather than
// ExecuteScript-level, since each trampoline still needs to name its own
// preserved original (and, where a resref collides across modules with a
// different vanilla script of the same name, pick the right one via
// GetModuleFileName()).
//
// Originally built for the Dantooine Jedi Council wrap-up
// family alone (live-reported story stall: player left in a locked room
// with only a "cutstart" interactable instead of being returned to the
// courtyard) -- root cause confirmed via disassembly: the vanilla
// wrap-up scene(s) reposition Bastila+Carth to "dan13_WP_council" (the
// courtyard) as part of several different dialogue-branch variants
// (k_pdan_addbast, k_pdan_cut01-06 in danm13, k_pdan_cut01/02/03/06 in
// danm14ab all share the identical bastila/carth/dan13_WP_council/
// lightsaber-item signature). Folded in the same day to also cover the
// Taris Hideout escape-plan scene (k_ptar_carbas_en.nss), which turned
// out to be doing the exact same temp-grant/bench/revert logic as its
// own standalone copy -- same underlying bug shape (a vanilla scene
// expects both companions present, gets stuck under ap_gated/none if
// neither has actually been received yet), just a different trigger.
// The Hideout scene has since moved out of this brain: it starts a
// conversation, which cannot be done from a script run through
// ExecuteScript, so k_ptar_carbas_en.nss reproduces the scene itself.
// Only scenes that do not start a conversation from the original belong here.
// FLAGGED FOR FUTURE ATTENTION: Dantooine is large and this is the
// SECOND unrelated scene found needing this exact treatment -- watch for
// more of the same shape (any vanilla scene disassembly showing
// bastila+carth tags alongside a waypoint/repositioning call) as
// playtesting continues, rather than assuming these two are the only
// ones. Not exhaustively scanned beyond the Council module pair and the
// Hideout scene.
//
// Same party-cap protection as k_ptar_startconv.nss: AddPartyMember can
// silently fail to seat a temp-granted companion if the active party is
// already full (hard capped at 3). Benches whichever companions occupy
// slots 1/2 first (same object reference, no recreation) to make room,
// restores them afterward. Revert happens in the same script tick as
// ExecuteScript, immediately after it returns -- RemovePartyMember does
// not destroy the underlying creature object, so whatever the scene just
// staged remains in place, it's simply not kept as an active party
// member afterward. Only companions THIS call actually granted are
// reverted -- an already-legitimate recruit is left completely alone.
//
// Carth handling reuses an existing "Carth"-tagged placed object if one
// exists in the current module (confirmed present in the Taris Hideout,
// confirmed ABSENT in the Council modules) rather than always creating
// fresh -- carbas_en's own original design note: CreateObject-ing a
// SECOND "p_carth" in a module that already has one placed leaves a
// stray, tag-colliding clone standing around forever after (RemoveParty
// Member does not destroy the object). Bastila has no pre-placed stand-in
// in these modules, but a creature an earlier run left behind is reused the
// same way, and a creature this gate created is destroyed 45 seconds after
// the scene (PurgeGateStrays), so repeated runs no longer pile up copies.
#include "kse"

int GetCompanionGateNPCIndex(object oCompanion)
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

// Destroys every creature carrying sTag. RemovePartyMember/RemoveAvailableNPC only edit the roster: the creature a temporary grant
// created keeps standing in the area, and every later run of the gate added another one.
void PurgeCompanionByTag(string sTag)
{
    int n = 0;
    object oStray = GetObjectByTag(sTag, n);
    while (GetIsObjectValid(oStray))
    {
        DestroyObject(oStray);
        n++;
        oStray = GetObjectByTag(sTag, n);
    }
}

// Runs a while after the scene the temporary grant was made for. Only a creature the gate itself created is destroyed, and only while
// its companion is not available, so a real recruit that happened in the meantime is never touched.
void PurgeGateStrays(int bBastilaMade, int bCarthMade)
{
    if (bBastilaMade && !IsAvailableCreature(NPC_BASTILA)) PurgeCompanionByTag("bastila");
    if (bCarthMade && !IsAvailableCreature(NPC_CARTH)) PurgeCompanionByTag("Carth");
}

// bAllowTempGrant lets a caller with its own extra real-story prerequisite
// (e.g. k_ptar_carbas_en.nss's GetJournalEntry("tar_bastsearch") >= 99)
// suppress ONLY the temp-grant/bench/revert dance while still always
// running the real original -- matching that the original vanilla
// script's own internal availability gate is what actually decides
// whether anything happens, exactly as it did before this call existed.
// Defaults to TRUE (the Council family's own natural gate is just being
// inside the right dialogue node, so none of them need to pass FALSE).
void HandleBastilaCarthGate(string sOriginalResref, string sSceneName, int bAllowTempGrant = TRUE)
{
    // Reentrancy guard -- confirmed (Taris Hideout, carbas_en's old
    // standalone predecessor) that the same OnEnter trigger can fire
    // several times within single-digit milliseconds for one physical
    // visit. Two independent invocations of this function each running
    // their own temp-grant/revert against the same global party-slot
    // state race each other -- confirmed via disassembly that neither
    // sOriginalResref's script nor anything it calls ever touches party
    // membership itself, so this function is the ONLY thing that can
    // leave a companion stuck without their real AP item: a duplicate
    // invocation's grant landing after an earlier invocation's own
    // revert re-enables availability with nothing left to revert it
    // again. A duplicate fire still needs the real original to run (its
    // own internal gate is idempotent), just not a second temp-grant
    // dance layered on top of one already in flight.
    // K1's Local Boolean storage is index-based (int, not string-keyed --
    // confirmed via nwscript.nss, unlike newer NWN engines), so this is
    // one shared index rather than one per sSceneName. That's fine: these
    // scenes are all different physical locations, so two different
    // scenes racing each other here isn't the failure mode that actually
    // happened -- the SAME scene's own trigger re-firing rapidly is.
    object oModule = GetModule();
    int GATE_BUSY_INDEX = 50;
    if (GetLocalBoolean(oModule, GATE_BUSY_INDEX))
    {
        ExecuteScript(sOriginalResref, OBJECT_SELF);
        return;
    }
    SetLocalBoolean(oModule, GATE_BUSY_INDEX, TRUE);

    object oPC = GetFirstPC();
    int bBastilaTemp = FALSE;
    int bCarthTemp = FALSE;
    int bBastilaMade = FALSE;
    int bCarthMade = FALSE;
    int nBenchedA = -1; object oBenchedA = OBJECT_INVALID;
    int nBenchedB = -1; object oBenchedB = OBJECT_INVALID;

    int nNeeded = 0;
    if (bAllowTempGrant)
    {
        if (!IsAvailableCreature(NPC_BASTILA)) nNeeded++;
        if (!IsAvailableCreature(NPC_CARTH)) nNeeded++;
    }

    if (nNeeded >= 1)
    {
        object oSlot2 = GetPartyMemberByIndex(2);
        if (GetIsObjectValid(oSlot2))
        {
            int nIdx = GetCompanionGateNPCIndex(oSlot2);
            if (nIdx != -1)
            {
                oBenchedA = oSlot2;
                nBenchedA = nIdx;
                RemovePartyMember(nBenchedA);
            }
        }
    }
    if (nNeeded >= 2)
    {
        object oSlot1 = GetPartyMemberByIndex(1);
        if (GetIsObjectValid(oSlot1))
        {
            int nIdx2 = GetCompanionGateNPCIndex(oSlot1);
            if (nIdx2 != -1)
            {
                oBenchedB = oSlot1;
                nBenchedB = nIdx2;
                RemovePartyMember(nBenchedB);
            }
        }
    }

    if (bAllowTempGrant && !IsAvailableCreature(NPC_BASTILA))
    {
        AddAvailableNPCByTemplate(NPC_BASTILA, "p_bastilla");
        // Reuse a Bastila that is already standing (a placed one, or one an earlier run left behind) instead of adding another.
        object oBastila = GetObjectByTag("bastila");
        if (!GetIsObjectValid(oBastila))
        {
            oBastila = CreateObject(OBJECT_TYPE_CREATURE, "p_bastilla", GetLocation(oPC));
            bBastilaMade = TRUE;
        }
        AddPartyMember(NPC_BASTILA, oBastila);
        bBastilaTemp = TRUE;
    }
    if (bAllowTempGrant && !IsAvailableCreature(NPC_CARTH))
    {
        // Reuse an existing placed "Carth" object if this module has one
        // (e.g. the Taris Hideout) instead of always creating fresh --
        // see this file's own header for why a second CreateObject would
        // leave a stray clone behind in that case.
        object oCarth = GetObjectByTag("Carth");
        if (!GetIsObjectValid(oCarth))
        {
            oCarth = CreateObject(OBJECT_TYPE_CREATURE, "p_carth", GetLocation(oPC));
            bCarthMade = TRUE;
        }
        AddAvailableNPCByTemplate(NPC_CARTH, "p_carth");
        AddPartyMember(NPC_CARTH, oCarth);
        bCarthTemp = TRUE;
    }

    KSE_Diag(171, "AP|BASTILA_CARTH_GATE|" + sSceneName + "|temp_bastila=" + IntToString(bBastilaTemp)
                  + "|temp_carth=" + IntToString(bCarthTemp)
                  + "|benchedA=" + IntToString(nBenchedA) + "|benchedB=" + IntToString(nBenchedB));

    ExecuteScript(sOriginalResref, OBJECT_SELF);

    if (bBastilaTemp)
    {
        RemovePartyMember(NPC_BASTILA);
        RemoveAvailableNPC(NPC_BASTILA);
    }
    if (bCarthTemp)
    {
        RemovePartyMember(NPC_CARTH);
        RemoveAvailableNPC(NPC_CARTH);
    }

    if (nBenchedB != -1 && GetIsObjectValid(oBenchedB))
    {
        AddPartyMember(nBenchedB, oBenchedB);
    }
    if (nBenchedA != -1 && GetIsObjectValid(oBenchedA))
    {
        AddPartyMember(nBenchedA, oBenchedA);
    }

    if (bBastilaMade || bCarthMade) DelayCommand(45.0, PurgeGateStrays(bBastilaMade, bCarthMade));

    SetLocalBoolean(oModule, GATE_BUSY_INDEX, FALSE);
}
