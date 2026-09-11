// Crash-prevention wrapper for Unknown World's finale "party showdown"
// area-enter script (originally unk_m41aa's k_punk_41aa_en, preserved as
// apo_unk41aa_en_orig).
//
// FOUND 2026-09-10: the real script unconditionally calls
// SpawnAvailableNPC on Carth/Canderous/Mission/T3-M4 -- no
// IsAvailableCreature guard at all, unlike HK-47/Zaalbar a few lines
// later in that same script, which DO check first and gracefully skip
// the spawn if unavailable -- the first time this area is entered
// (gated only by the one-time UNK_PARTYSHOWDOWN global). SpawnAvailableNPC
// assumes the NPC was already properly initialized via an earlier
// AddAvailableNPCByTemplate call; if that never happened, the result is a
// genuine engine-level crash, not a graceful NWScript no-op. Confirmed
// live via an Area Randomizer door that used to connect here early (that
// specific door is now excluded from the randomizer's shuffle pool), but
// the underlying gap is real independent of how this area gets reached --
// companion_mode=none never recruits anyone at all, and companion_mode=
// ap_gated could still be waiting on one of these 4 companions' items
// this late into the game.
//
// Fix: for exactly those 4 ungated companions, ensure they're a valid
// AddAvailableNPCByTemplate-initialized NPC before handing off to the
// real script. Unknown World is the very last area in the game -- a
// companion's vanilla recruit-story importance is long past by this
// point, so silently backfilling one that was never otherwise obtained
// changes nothing story-relevant, it only prevents the crash. HK-47 and
// Zaalbar already self-guard in the real script and are left untouched.
#include "kse"

void main()
{
    if (!IsAvailableCreature(NPC_CARTH))
    {
        AddAvailableNPCByTemplate(NPC_CARTH, "p_carth");
    }
    if (!IsAvailableCreature(NPC_CANDEROUS))
    {
        AddAvailableNPCByTemplate(NPC_CANDEROUS, "p_cand");
    }
    if (!IsAvailableCreature(NPC_MISSION))
    {
        AddAvailableNPCByTemplate(NPC_MISSION, "p_mission");
    }
    if (!IsAvailableCreature(NPC_T3_M4))
    {
        AddAvailableNPCByTemplate(NPC_T3_M4, "p_t3m4");
    }
    ExecuteScript("apo_unk41aa_en_orig", OBJECT_SELF);
    KSE_Diag(141, "AP|SAFEGUARD|unk41aa_partyshowdown");
}
