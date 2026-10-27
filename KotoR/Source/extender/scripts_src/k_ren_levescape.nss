// Leviathan escape turret sequence: skips the required turret mini-game, plays the cutscene and returns to the Ebon Hawk.
void main()
{
    PlayMovie("17a");
    StartNewModule("ebo_m40ad", "", "11b", "", "", "", "", "");
}
