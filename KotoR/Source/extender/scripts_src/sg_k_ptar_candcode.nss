// Story gate 3 (Taris): Canderous joins and the transfer to Davik's estate. Replaces the
// vanilla condition k_ptar_candcode, which is only used by the cantina dialogs and is the
// only condition on the links to the recruitment node and to the node that starts Davik's
// estate. Vanilla body: the player holds ptar_shieldcodes. The gate adds "holds three Taris
// progression items".
#include "ap_gate"

int StartingConditional()
{
    if (!GetIsObjectValid(GetItemPossessedBy(GetFirstPC(), "ptar_shieldcodes"))) return FALSE;
    if (!ApGateOpen("tar", 3))
    {
        ApGateMsg("Taris", 3);
        return FALSE;
    }
    return TRUE;
}
