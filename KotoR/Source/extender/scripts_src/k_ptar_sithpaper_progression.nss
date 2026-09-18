// Progression System Sith Papers gate. Sith Papers has no
// findable vanilla acquisition script anywhere in the game -- searched
// every .ncs in both chitin and Override, every UTP/UTC/UTM container/
// store/creature inventory, and every per-instance GIT override for the
// literal resref "ptar_sithpapers"; nothing but this one checkpoint
// script ever references it. So unlike Sith Armor/Shield Codes/Enviro
// Suit, there's no upstream pickup point to suppress instead -- this IS
// the real checkpoint (a dialogue StartingConditional), gated directly.
//
// Can't use the gate-and-delegate pattern the other 3 wrappers use here:
// ExecuteScript can't relay a StartingConditional's return value back to
// the caller. Reimplemented faithfully instead -- the original is a
// single possession check (confirmed via full disassembly: GetFirstPC(),
// not GetPCSpeaker()), not a simplification of something more complex.
//
// No KSE_HasData("granted_exempt_ptar_sithpapers") gate: that in-DLL
// store doesn't survive a game restart (see kse.nss's own LIFETIME
// comment), so any restart between the AP grant and reaching this
// checkpoint left the physical item in inventory (saved fine) but the
// gate flag cleared, permanently failing this check even though the
// player was holding the papers. Since "ptar_sithpapers" has no other
// creation point anywhere in the game (see comment above), real
// possession is already sufficient proof the AP grant fired -- no
// separate gate needed.
#include "kse"

int StartingConditional()
{
    return GetIsObjectValid(GetItemPossessedBy(GetFirstPC(), "ptar_sithpapers"));
}
