// Progression System Sith Papers gate (2026-09-08). Sith Papers has no
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
#include "kse"

int StartingConditional()
{
    if (!KSE_HasData("granted_exempt_ptar_sithpapers")) return FALSE;
    return GetIsObjectValid(GetItemPossessedBy(GetFirstPC(), "ptar_sithpapers"));
}
