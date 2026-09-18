// Trampoline for k_pdan_cut05 -- part of the Dantooine Jedi Council
// companion-gate family, see ap_companion_gate.nss's own header for
// the full root-cause story. This exact resref exists identically-
// named but with DIFFERENT real content in more than one module
// (Override resolves by name only, no per-module scoping), so this
// checks GetModuleFileName() to pick the right preserved original.
#include "kse"
#include "ap_companion_gate"

void main()
{
    string sModule = GetModuleFileName();
    if (sModule == "danm13")
    {
        HandleBastilaCarthGate("apo_danm13_cut05_orig", "k_pdan_cut05_danm13");
    }
    else if (sModule == "danm14ab")
    {
        ExecuteScript("apo_danm14ab_cut05_orig", OBJECT_SELF);
    }
    else
    {
        ExecuteScript("apo_danm13_cut05_orig", OBJECT_SELF);
    }
}
