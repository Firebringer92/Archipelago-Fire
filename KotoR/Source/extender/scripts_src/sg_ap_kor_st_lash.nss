// Uthar intro repair (Korriban): "Lashowe is in the academy". A new condition with no vanilla counterpart, placed by
// scripts/story_gate_dialogs_korriban.py on the link into Lashowe's spoken line of Uthar's welcome scene in
// kor35_utharwynn. TRUE when her academy copy (tag kor35_lashowe) exists and is alive. The module-enter script
// kor35_enter destroys that copy once she is dead, so the line is skipped instead of waiting on a speaker who is gone.
int StartingConditional()
{
    object oStudent = GetObjectByTag("kor35_lashowe");
    return GetIsObjectValid(oStudent) && !GetIsDead(oStudent);
}
