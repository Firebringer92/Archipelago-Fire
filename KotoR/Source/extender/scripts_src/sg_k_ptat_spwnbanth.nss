// Tatooine dead-end repair: the bantha spawn. Replaces the node script k_ptat_spwnbanth (tat_m18ac only, run from
// Komad's bait briefing, node E59 of tat18_11komad_01). Vanilla creates the three banthas at their waypoints every time
// the briefing is heard, so hearing it again doubled the herd; this version creates only the banthas that are missing
// (see sg_tat_banthas) and keeps the conversation pause of the original.
#include "sg_tat_banthas"

void main()
{
    SgTatEnsureBanthas();
    ActionPauseConversation();
    DelayCommand(1.0, ActionResumeConversation());
}
