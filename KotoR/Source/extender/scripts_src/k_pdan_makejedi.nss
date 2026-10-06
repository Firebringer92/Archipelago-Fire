// Suppression wrapper for Dantooine's real "become a Jedi" trial-completion
// script (originally danm13's k_pdan_makejedi, preserved as apo_makejedi_orig).
//
// starting_class is "off" this seed -- runs the real vanilla script unchanged.
#include "kse"

void main()
{
    ExecuteScript("apo_makejedi_orig", OBJECT_SELF);
}
