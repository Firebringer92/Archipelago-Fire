// AP companion OnSpawn (generate_new_companion_assets.py): the real henchman spawn init, then the look as a permanent disguise. The appearance
// row is in the creature's tag, "apl<row>x<n>".
void main()
{
    ExecuteScript("k_hen_spawn01", OBJECT_SELF);
    string sTag = GetTag(OBJECT_SELF);
    int nX = FindSubString(sTag, "x");
    if (GetStringLeft(sTag, 3) != "apl" || nX < 4) return;
    int nRow = StringToInt(GetSubString(sTag, 3, nX - 3));
    if (nRow > 0) ApplyEffectToObject(DURATION_TYPE_PERMANENT, EffectDisguise(nRow), OBJECT_SELF);
}
