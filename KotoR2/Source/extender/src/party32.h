#pragma once

// 32-slot companion roster. The game keeps 12 companion slots in fixed arrays; slots 12-31 live in a table of our own and
// every place that reads or writes a slot is redirected (see party32.cpp). Config key party32=1 turns it on.
//
// The approach and the list of patch sites follow the Patch Manager mod PartyRosterLimit32K2 (MIT, by Vriff,
// github.com/LaneDibello/Kotor-Patch-Manager); this is our own implementation for the Steam build of swkotor2.exe.

namespace k2se {
namespace party32 {

// Applies the patches if config party32=1 and every address and byte checks out. Returns the number of patch sites applied (0 when off or refused).
int Apply();

}  // namespace party32
}  // namespace k2se
