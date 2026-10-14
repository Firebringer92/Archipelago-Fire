// Uthar intro repair (Korriban): Shaardan's interjection against the player. A new condition that combines the vanilla
// k35_sha_mercy (KOR33_SHAARDAN equals 3) with "his academy copy, tag kor35_shaardan, exists and is alive", for the link
// into his line E135 of kor35_utharwynn. k35_sha_mercy itself stays untouched because the Shaardan dialog uses it too.
int StartingConditional()
{
    if (GetGlobalNumber("KOR33_SHAARDAN") != 3) return FALSE;
    object oStudent = GetObjectByTag("kor35_shaardan");
    return GetIsObjectValid(oStudent) && !GetIsDead(oStudent);
}
