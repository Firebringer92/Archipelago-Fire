// Calo Nord companion OnSpawn (generate_new_companion_assets.py): the real henchman spawn init, then a
// permanent disguise as the character's own appearance row, the same mechanism as k_hmal_spawn01 (Darth Malak).
#include "kse"

void main()
{
    ExecuteScript("k_hen_spawn01", OBJECT_SELF);
    ApplyEffectToObject(DURATION_TYPE_PERMANENT, EffectDisguise(13), OBJECT_SELF);
}
