// Uthar intro repair (Korriban): Lashowe's interjection against the player. A new condition that combines the vanilla
// k_pkor_lashhate (KOR_LASHOWE_HATE set) with "her academy copy, tag kor35_lashowe, exists and is alive", for the two
// links into her line E134 of kor35_utharwynn. k_pkor_lashhate itself stays untouched because the Lashowe dialog uses it too.
int StartingConditional()
{
    if (!GetGlobalBoolean("KOR_LASHOWE_HATE")) return FALSE;
    object oStudent = GetObjectByTag("kor35_lashowe");
    return GetIsObjectValid(oStudent) && !GetIsDead(oStudent);
}
