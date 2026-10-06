// Shared item-pickup handler for modules with no existing
// vanilla Mod_OnAcquirItem script. See patch_item_suppression.py's module
// docstring for this seed's configured mode (destroy/bonus/replace).
#include "kse"

void HandleAcquiredItem()
{
    object oItem = GetModuleItemAcquired();
    string sTag = GetStringLowerCase(GetTag(oItem));
}

void main()
{
    HandleAcquiredItem();
}
