// AP RESEARCH SPIKE: Void Trade / Galactic Trade (shipped as the Galactic
// Shop feature) feasibility -- confirms whether a custom spells.2da row's
// impactscript actually fires via an item's CastSpell (itempropdef.2da
// row 10) property in THIS real engine build, and which activation-context
// functions actually return usable values when triggered this way
// (GetItemActivated()/GetItemActivator() vs. the spell-cast-context
// functions like GetLastSpellCaster()/GetSpellId()/GetSpellCastItem() --
// unknown ahead of time which family is actually populated for an
// item-triggered "spell").
#include "kse"

void main()
{
    // FIRST LINE, unconditional, independent of KSE_Diag or anything below --
    // proves the impact script executed at all, visually, without needing to
    // check kse.log (a real attempt showed a
    // stim-style use animation/portrait icon but zero log output): need to
    // isolate "did this script run at all" from "did KSE_Diag log correctly
    // from a CastSpell context" as two separate questions.
    FloatingTextStringOnCreature("AP_CASTSPELL_DIAG_RAN", GetFirstPC(), FALSE);

    object oActivator = GetItemActivator();
    object oItemActivated = GetItemActivated();
    object oSpellCaster = GetLastSpellCaster();
    int nSpellId = GetSpellId();
    object oSpellCastItem = GetSpellCastItem();

    string sReport = "AP|TEST_CASTSPELL_FIRED"
        + "|activator=" + ObjectToString(oActivator)
        + "|activator_valid=" + IntToString(GetIsObjectValid(oActivator))
        + "|item_activated=" + ObjectToString(oItemActivated)
        + "|item_activated_valid=" + IntToString(GetIsObjectValid(oItemActivated))
        + "|spell_caster=" + ObjectToString(oSpellCaster)
        + "|spell_caster_valid=" + IntToString(GetIsObjectValid(oSpellCaster))
        + "|spell_id=" + IntToString(nSpellId)
        + "|spell_cast_item=" + ObjectToString(oSpellCastItem)
        + "|spell_cast_item_valid=" + IntToString(GetIsObjectValid(oSpellCastItem));

    KSE_Diag(140, sReport);
}
