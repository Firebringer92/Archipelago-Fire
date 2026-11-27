#pragma once

// 32-slot companion roster for KOTOR 1 (Steam 1.03). Slots 0-8 keep using the game's own party table; slots 9-31 live in a sidecar kept by this module.
// Design and hook table: Patch Manager mod PartyRosterLimit32K1 (MIT, Vriff and Patch Manager contributors); see PATCH_MANAGER_LICENSE.txt.

// Applies the roster patches if "ap_party32.txt" beside the game executable starts with 1/on/true and every patch site holds the expected original bytes
// (nothing is written otherwise). Called once from the worker thread after the game's code is decrypted. Returns the number of sites applied.
int Party32Install();
