// new_companion=malak variant of the preserved vanilla Tatooine droid-shop
// recruit trigger (originally tat_m17ac_s.rim's k_ptat_hk47add, preserved
// verbatim as apo_hk47_vanilla.ncs). Same shape as apo_hk47_new.nss
// (mystery/Meetra variant) -- the ONLY change from vanilla is the
// template resref on the very first line, "p_hk47" -> "p_malak".
// Everything else (the fade transition, the delayed
// ShowPartySelectionGUI() letting the player pick their party lineup,
// the delayed self-destruct) is preserved exactly, since none of it is
// companion-specific.
//
// generate_new_companion_assets.py deploys this file (as apo_hk47_orig.ncs,
// the name the companion-suppression wrapper's ExecuteScript call expects)
// in place of apo_hk47_vanilla.ncs/apo_hk47_new.ncs whenever new_companion
// is 2 (malak), same restore-on-switch pattern already used for Loot Mode.
void main()
{
    AddAvailableNPCByTemplate(3, "p_malak");

    SetGlobalFadeOut(0.0, 1.0, 0.0, 0.0, 0.0);
    SetGlobalFadeIn(1.0, 2.0, 0.0, 0.0, 0.0);

    DelayCommand(1.0, ShowPartySelectionGUI());
    DelayCommand(1.5, DestroyObject(OBJECT_SELF, 0.0, TRUE, 0.0));
}
