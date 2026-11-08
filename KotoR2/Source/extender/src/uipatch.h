#pragma once

// Engine UI patches applied once when the extender loads.
namespace k2se {
namespace uipatch {

// Party selection screen: shows both members of each exclusive pair (Mira with Hanharr, Handmaiden with the Disciple)
// instead of one, so all twelve companion slots can be displayed. The screen's setup code (CSWGuiPartySelection, 0x8A0960) clears the
// visible bit of the partner's three controls with `xor reg,reg ; and reg,1`; six of those `and reg,1` become `or reg,1`.
// All-or-nothing: every site must hold the expected original byte or nothing is changed. config.txt key
// partyselect_all=0 turns it off. Returns the number of bytes changed (6 or 0).
int ApplyPartySelectAll();

}  // namespace uipatch
}  // namespace k2se
