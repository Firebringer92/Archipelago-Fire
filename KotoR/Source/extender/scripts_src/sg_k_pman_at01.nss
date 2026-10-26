// Manaan: the Hrakert Rift never stays sealed. Wrapper for k_pman_at01, a core script (no module copy) read by the Rift's exit doors
// (sw_door_manaa001 and sw_door_manaa002, OnFailToOpen), the computer panel (comppnl003, OnUsed) and the two exit triggers
// (newgeneric001 and newgeneric002, OnEnter), all in manm28ad. Vanilla body: once the Manaan plot is at 3 or more and the star map has not
// been found (MAN_STARMAP_FOUND), the exit starts a conversation and stays shut; otherwise it clears the party's effects and moves the party out
// (StartNewModule). The star map placeable waits for the third Manaan progression item, so a player who reaches that stage with fewer would be
// shut in until the item arrives from outside, which in a solo game can be never.
//
// The original is kept as apo_sg_at01 and runs with MAN_STARMAP_FOUND forced true for the length of the call, so it always takes the leaving
// branch (including the effect clean-up and the module change); the flag is put back at once, so the star map still has to be found as before and
// the player can walk out and come back in. Everything runs in one script pass, so no other script sees the changed flag.
void main()
{
    int bFound = GetGlobalBoolean("MAN_STARMAP_FOUND");
    if (!bFound) SetGlobalBoolean("MAN_STARMAP_FOUND", TRUE);
    ExecuteScript("apo_sg_at01", OBJECT_SELF);
    if (!bFound) SetGlobalBoolean("MAN_STARMAP_FOUND", FALSE);
}
