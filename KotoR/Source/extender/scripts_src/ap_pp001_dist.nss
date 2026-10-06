// TEMPORARY (loot-window memory-hunting research) -- wired
// onto partpile001.utp's OnInvDisturbed field. OnOpen/OnUsed were both
// confirmed DEAD in this engine build (zero vanilla placeable OR door
// templates in the whole base game use OnOpen at all -- matches this
// project's existing OnExit/CastSpell "confirmed dead" precedent).
// OnInvDisturbed is PROVEN REAL by BioWare's own shipped code
// (korr_m37aa's k_pkor_therangen, already reused for the Galactic Shop
// feature -- see ap_galtradebox.nss) -- fires when an item is actually
// added or removed from this container, not merely opened. Logs which
// disturb type fired, then resolves OBJECT_SELF via KSE_ResolveItemId so
// its struct can be dumped while the player is genuinely mid-interaction
// with this container's contents. Retire (delete this file, remove
// Override/partpile001.utp, remove the .ncs) once this research
// concludes.
#include "kse"

void main()
{
    int nType = GetInventoryDisturbType();
    string sType = (nType == INVENTORY_DISTURB_TYPE_ADDED) ? "ADDED" : "REMOVED";
    KSE_Diag(158, "AP|APPLIED|ap_pp001_dist|ONDISTURBED_FIRED|" + sType);
    KSE_ResolveItemId(OBJECT_SELF, 0, 0);
}
