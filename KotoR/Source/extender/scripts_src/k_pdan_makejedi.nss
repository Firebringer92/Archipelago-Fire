// Suppression wrapper for Dantooine's real "become a Jedi" trial-completion
// script (originally danm13's k_pdan_makejedi, preserved as apo_makejedi_orig).
//
// jedi_start is project-managed this seed (not "off") -- the vanilla
// AddMultiClass()/XP grant/cutscene-polish is skipped entirely here. The
// real class grant comes from this project's own class_guardian/
// class_consular/class_sentinel arms (or any future PC-class-randomize
// mechanism) instead -- see generate_makejedi_suppressor.py's module
// docstring for the full investigation into why skipping this wholesale
// is safe (every global it touches is either internal-only or read-only
// here, and the Bastila/Carth/lightsaber-resref/dan_wanderhound block is
// confirmed cosmetic cutscene setup, not an item grant).
#include "kse"

void main()
{
}
