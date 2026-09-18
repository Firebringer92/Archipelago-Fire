// Trampoline for danm13's k_pdan_addbast (the Jedi Council wrap-up
// script fired directly from dan13_vandar's dialogue tree, preserved
// byte-exact as apo_addbast_orig) -- see ap_companion_gate.nss's own
// header for the full root-cause story shared across this whole family.
#include "kse"
#include "ap_companion_gate"

void main()
{
    HandleBastilaCarthGate("apo_addbast_orig", "addbast");
}
