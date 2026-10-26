// RETIRED in 0.2.0: no longer deployed (scripts/patch_story_gates.py RETIRED_GATES). Kept only so an old copy in Override can be recognised and removed;
// the game's own k_pman_door08 is used again, and man26ac_door05 needs the card W_REPKEY2 from Roland's debrief.
// Manaan: the Republic submarine door stays open to everyone. Replaces the vanilla script k_pman_door08, the
// OnFailToOpen script shared by eighteen locked doors on Manaan and Dantooine. Vanilla body: start the door's own
// message conversation with the player. This keeps that behaviour for every door except man26ac_door05, the key door
// (key W_REPKEY2) behind the Republic kolto packing room that leads to the submarine for the Hrakert Rift. That door is
// unlocked and opened on the first attempt, so the Rift does not depend on Roland Wann handing over the key (which sits
// behind the M2 gate) and the star map gate in the Rift can be reached with progression items alone.
void main()
{
    if (GetTag(OBJECT_SELF) == "man26ac_door05")
    {
        object oDoor = OBJECT_SELF;
        SetLocked(oDoor, FALSE);
        AssignCommand(oDoor, ActionOpenDoor(oDoor));
        return;
    }
    ActionStartConversation(GetFirstPC());
}
