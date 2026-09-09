// Progression System Enviro Suit gate (2026-09-08). k_pman_suituse is
// the Manaan underwater-facility wardrobe/locker script -- its real job
// (confirmed via full disassembly) is looping the active party and
// CreateItemOnObject-ing an envirosuit for any member who doesn't
// already have one. This is the REAL creation point for
// man28_envirosuit, NOT a Mod_OnAcquirItem-style pickup at all, so the
// existing generic item-suppression system never touches it -- it needs
// its own dedicated gate.
//
// Blocking this from ever handing out the suit until the check has been
// received makes k_pman_airlock01's own live possession check
// (GetItemPossessedBy on the party) fail naturally on its own -- no
// separate change needed there, same principle already used for Sith
// Armor's k_ptar_sithdis checkpoint (gate the upstream creation point,
// not the downstream live check).
//
// Vanilla original preserved as apo_k_pman_suituse_orig; delegated to
// unchanged (including its party-loop and tail plot-flag/cleanup logic,
// none of which this wrapper needs to understand) once granted.
#include "kse"

void main()
{
    if (!KSE_HasData("granted_exempt_man28_envirosuit"))
    {
        KSE_Diag(132, "AP|PROGRESSION_BLOCKED|suituse");
        return;
    }
    ExecuteScript("apo_k_pman_suituse_orig", OBJECT_SELF);
}
