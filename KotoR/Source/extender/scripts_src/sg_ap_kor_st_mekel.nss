// Uthar intro repair (Korriban): "Mekel is in the academy". A new condition with no vanilla counterpart, placed by
// scripts/story_gate_dialogs_korriban.py on the link into Mekel's spoken line of Uthar's welcome scene in
// kor35_utharwynn. TRUE when his academy copy (tag kor35_mekel) exists and is alive. The module-enter script
// kor35_enter destroys that copy once he is dead or has left, so the line is skipped instead of waiting on a speaker
// who is gone.
int StartingConditional()
{
    object oStudent = GetObjectByTag("kor35_mekel");
    return GetIsObjectValid(oStudent) && !GetIsDead(oStudent);
}
