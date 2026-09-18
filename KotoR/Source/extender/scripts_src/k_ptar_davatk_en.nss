// Wrapper for Davik's Estate hangar door's real OnOpen script
// (originally tar_m08aa's k_ptar_davatk_en, placeable tag
// tar08_hangardoor, preserved byte-exact as apo_davatk_en_orig).
//
// Real, confirmed problem this closes: Canderous Ordo's actual vanilla
// recruit trigger (k_ptar_candadd, also physically present in this same
// module's _s.rim) was traced extensively and never found to be wired
// to ANY reachable trigger/placeable/door/creature/module-IFO script
// field anywhere in the game (see docs/MODE_DEPENDENCIES.md's "Canderous
// AP check never fires" entry for the full archaeology) -- a whole-game
// raw-byte search found the literal resref in exactly one place, its own
// unused-looking resource entry. Live-confirmed the AP check for him
// (companion_idx=1) never fires even after boarding the Ebon Hawk.
//
// Rather than keep chasing the real vanilla hook (or risk touching
// Davik082/Calo082's own OnDeath, k_def_death01, which 192 of 205 chitin
// creatures share -- wrapping that for one specific creature would need
// a separate per-creature UTC field edit anyway, and risks the same
// ActionStartConversation-via-ExecuteScript indirection bug this project
// already found once tonight, for whatever post-death dialogue/explosion
// sequence Davik's own death may chain into), this hooks the hangar
// door's OnOpen instead -- the player physically cannot reach the
// Ebon Hawk without opening it, so it's a guaranteed, low-risk,
// idempotent point to run the same check-and-suppress logic
// k_ptar_candadd.nss already has, just from a hook that's actually
// reachable.
//
// Hard prerequisite: GetJournalEntry("tar_escape") >= 50 -- "You have
// the codes to disable the Ebon Hawk's security system. Now you just
// have to get to the hangar and board the ship" (confirmed directly
// against global.jrl) -- the real stage that's only reached after
// Davik's estate (and Davik himself) has already been dealt with, so
// this can't fire prematurely off some other reason the door happens to
// open.
//
// REAL BUG FOUND LIVE TESTING THIS FIX (2026-09-17): the first version of
// this file guarded on `!IsAvailableCreature(NPC_CANDEROUS)`, matching
// k_ptar_candadd.nss's own guard -- but live-tested on FireKnight's seed
// (companion_canderous confirmed via kotor_delivery_log.jsonl to have
// NEVER been legitimately delivered to this slot), the check fired but
// Canderous was NOT suppressed, because IsAvailableCreature() was
// already TRUE by the time this door opened. IsAvailableCreature() only
// answers "is he available right now", not "did AP actually grant this"
// -- it can't tell a real AP grant apart from whatever still-unidentified
// vanilla mechanism makes him available for free with zero gating (the
// original bug this whole fix exists for). A flag is needed instead:
// the companion_canderous arm itself (scripts/generate_trampoline_
// batch.py, arm 10) now sets KSE_SetData("ap_canderous_legit", "1")
// every time it actually runs (whether from a real received item under
// ap_gated, or the companion_mode=normal auto-grant -- both paths run
// this exact arm, see KotorClient.py's generic per-companion auto-grant
// handling around companion_mode==1). That flag, not IsAvailableCreature,
// is the only reliable "AP actually put him here" signal.
//
#include "kse"

void main()
{
    if (GetJournalEntry("tar_escape") >= 50)
    {
        if (KSE_GetData("ap_canderous_legit") != "1")
        {
            RemovePartyMember(NPC_CANDEROUS);
            RemoveAvailableNPC(NPC_CANDEROUS);
            KSE_Diag(27, "AP|SUPPRESSED|companion_candadd_davik_hangar");
        }
        KSE_Diag(22, "AP|CHECK|COMPANION|1");
    }

    ExecuteScript("apo_davatk_en_orig", OBJECT_SELF);
}
