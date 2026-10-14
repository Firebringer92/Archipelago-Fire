// Uthar intro repair (Korriban): "Shaardan is in the academy". A new condition with no vanilla counterpart, placed by
// scripts/story_gate_dialogs_korriban.py on the link into Shaardan's spoken line of Uthar's welcome scene in
// kor35_utharwynn. TRUE when his academy copy (tag kor35_shaardan) exists and is alive. The module-enter script
// kor35_enter destroys that copy when KOR33_SHAARDAN is 4 or more, so the line is skipped instead of waiting on a
// speaker who is gone.
int StartingConditional()
{
    object oStudent = GetObjectByTag("kor35_shaardan");
    return GetIsObjectValid(oStudent) && !GetIsDead(oStudent);
}
