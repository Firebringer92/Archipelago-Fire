// k2se_ap_enter.nss -- area OnEnter hook for areas that have no OnEnter script of their own (written into their area file by tools/build_area_hooks.py).
// Starts the delivery dispatcher loop for this area. Does nothing unless disp_enable=1 in config.txt.
#include "k2se_disp"

void main()
{
    if (!K2SE_IsPresent()) return;
    if (K2SE_ConfigInt("disp_enable", 0) == 0) return;
    K2SE_Diag("DISP", "area enter hook (empty-OnEnter area) ran in " + GetModuleName());
    DispStart();
}
