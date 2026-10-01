// Darth Malak companion OnSpawn -- runs the real henchman spawn init
// (k_hen_spawn01, unchanged) then self-applies a permanent EffectDisguise
// using his own real DISGUISE_TYPE_N_DARTHMALAK (appearance.2da row 21,
// his actual unmodified boss model). Replaces the earlier approach of
// building a custom appearance.2da row + a hand-spliced head model
// (Carth's proven head model with Malak's geometry grafted onto the
// head_g node) -- that route deployed without errors but never actually
// rendered in three separate attempts, and the last one is suspected of
// having caused a live crash (a brand-new CreateObject + never-live-
// tested custom model landing in the same trampoline batch as an
// unrelated correction). EffectDisguise is a real, standard KOTOR effect
// -- the exact mechanism the game's own Sith Armor disguise and several
// other vanilla disguises already use -- so this needs no custom model,
// no custom appearance/heads.2da row, and no new native extension work.
#include "kse"

void main()
{
    ExecuteScript("k_hen_spawn01", OBJECT_SELF);
    ApplyEffectToObject(DURATION_TYPE_PERMANENT, EffectDisguise(DISGUISE_TYPE_N_DARTHMALAK), OBJECT_SELF);
}
