#pragma once

// Research aid: a background thread that watches the party purse and the two bench counters stored next to it
// (the player's credits word, then Components, then Chemicals) and logs every change with a timestamp.
// It runs on its own clock, so it still sees changes while a full-screen GUI (the workbench) has stopped the game's
// script clock. Read-only. Off unless config.txt has craftwatch=1.
namespace k2se {
namespace craftwatch {

void Start();

}  // namespace craftwatch
}  // namespace k2se
