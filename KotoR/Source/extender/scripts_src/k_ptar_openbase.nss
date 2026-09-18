// Wrapper for the Taris Sith Base entrance's real OnEnter script
// (originally tar_m02ab's k_ptar_openbase, trigger tag tar02_openbase,
// preserved byte-exact as apo_openbase_orig).
//
// Root cause, confirmed via disassembly: the ONLY door into the Sith
// Base (tar02_sithdoor, linking to tar_m09aa) has lockable=FALSE on its
// own UTD blueprint -- there is no Security-skill lockpick option in the
// UI at all, not just a high DC. The sole way it ever opens is this
// trigger's own script, which requires the ENTERING, PC-CONTROLLED
// character's tag to resolve to index 7 in its inline companion lookup
// (bastila=0, cand=1, carth=2, hk47=3, jolee=4, juhani=5, mission=6,
// t3m4=7, zaalbar=8) -- i.e. the player must be actively controlling
// T3-M4 specifically when walking up to this door. No other route, no
// skill check, no alternate script anywhere references this door
// (confirmed via a full-game audit this session). A second, simpler
// script with the same T3-M4 check (k_ptar_sthchk_en) exists as a
// compiled resource but its own trigger blueprint is never placed in
// any module's GIT -- dead content, not a real alternate path.
//
// Under companion_mode=ap_gated (T3-M4's own AP item not yet received)
// or companion_mode=none (T3-M4 never recruited at all), this is a
// permanent main-story soft-lock: there is no way to ever satisfy
// "currently controlling T3-M4" if T3-M4 was never made available to
// switch to in the first place. Live-reported, not hypothetical --
// confirmed by the user directly.
//
// Fix: if T3-M4 isn't currently available at all, unlock the door
// ourselves regardless of who's entering, then still delegate to the
// preserved original (its own GetIsPC+index==7 check simply won't match
// a non-T3-M4 entrant, so it harmlessly does nothing extra -- the
// conversation flavor tied to actually playing as T3-M4 is lost in this
// fallback case, but progress is what's actually broken, not the
// flavor). If T3-M4 IS available, this wrapper changes nothing --
// preserves the intended droid-disguise mechanic exactly as vanilla for
// every player who actually has T3-M4, including companion_mode=normal
// and ap_gated once the real item arrives. ActionUnlockObject is
// idempotent, so this firing on repeat entries or on non-PC party
// members trailing through is harmless.
//
// Hard prerequisite, same reasoning as the Hideout fix: only fire once
// GetJournalEntry("tar_escape") >= 20 -- the real stage where Canderous
// actually assigns this objective ("break into the Sith military base
// and recover the planetary departure codes... A T3 droid could get you
// past the security doors"), confirmed directly against global.jrl. Its
// own text confirms the T3-M4 requirement is intentional vanilla design,
// not a randomizer artifact -- this gate just stops the fallback from
// ever unlocking the door before the story has actually assigned this
// objective, on the same principle as the Hideout fix, even though the
// door isn't known to be reachable that early either way.
#include "kse"

void main()
{
    if (GetJournalEntry("tar_escape") >= 20 && !IsAvailableCreature(NPC_T3_M4))
    {
        object oDoor = GetObjectByTag("tar02_sithdoor");
        if (GetIsObjectValid(oDoor))
        {
            AssignCommand(oDoor, ActionUnlockObject(oDoor));
            KSE_Diag(162, "AP|SAFEGUARD|tar_sithbase_door_unlock");
        }
    }
    ExecuteScript("apo_openbase_orig", OBJECT_SELF);
}
