// Wrapper for kas_m24aa's k_pkas_talkwall (the first node of the repulsor-field
// dialogue kas24_force_01, preserved byte-exact as apo_talkwall_orig). The field
// only opens with Jolee in the party. When he has been recruited the vanilla
// behaviour applies; when his recruit point has been reached but he is not
// available (the companion item has not arrived, or companions are off) he is
// seated for the conversation so the field can still be opened, see
// ap_jolee_field.nss.
//
// The field stays shut until Jolee's recruit point has been reached: his recruit
// script writes the journal marker ap_recruit_jolee (ap_recruit_marker.nss), and
// that happens only in his own join dialogue, which waits for the first Kashyyyk
// progression item. Before it nothing is seated and the field's dialogue is the
// vanilla dead end ("If he were here, he would allow you to pass"). A journal that
// does not declare the marker (an install without the recruit quests) reads -1;
// that keeps the older behaviour, so the planet cannot be left impossible.
#include "kse"
#include "ap_jolee_field"

void main()
{
    int nRecruit = GetJournalEntry("ap_recruit_jolee");
    if (nRecruit >= 1 || nRecruit < 0) StageJoleeForField();
    ExecuteScript("apo_talkwall_orig", OBJECT_SELF);
}
